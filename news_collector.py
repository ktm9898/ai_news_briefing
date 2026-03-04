"""
news_collector.py - 네이버 뉴스 API + newspaper4k 기반 뉴스 수집 엔진

기능:
  - 네이버 뉴스 검색 API로 키워드별 최신 뉴스 수집 (본문 크롤링 없이 빠르게)
  - 선별된 기사만 newspaper4k로 본문 크롤링 (병렬 처리)
  - 개별 기사 실패 시 해당 건만 스킵 (에러 격리)
  - 이미 저장된 링크 중복 방지
"""

import re
import html
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests
import nltk

# newspaper4k가 필요로 하는 NLTK 데이터 자동 설치 (클라우드 환경 대응)
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)

from newspaper import Article

from config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_SEARCH_URL,
    NAVER_NEWS_DISPLAY,
    MAX_PER_TOPIC,
    SIMILARITY_THRESHOLD,
)
from sheets_manager import SheetsManager

logger = logging.getLogger(__name__)

# 공신력 있는 주요 언론사 도메인 화이트리스트
TRUSTED_MEDIA_DOMAINS = {
    # 방송사
    'kbs.co.kr', 'mbc.co.kr', 'sbs.co.kr', 'jtbc.co.kr',
    'ytn.co.kr', 'mbn.co.kr', 'tvchosun.com', 'ichannela.com',
    'yonhapnewstv.co.kr', 'ebs.co.kr',
    # 주요 일간지
    'chosun.com', 'joongang.co.kr', 'donga.com',
    'hankookilbo.com', 'khan.co.kr', 'hani.co.kr',
    'seoul.co.kr', 'segye.com', 'kmib.co.kr', 'munhwa.com',
    # 통신사
    'yna.co.kr', 'newsis.com', 'news1.kr',
    # 경제지
    'hankyung.com', 'mk.co.kr', 'mt.co.kr', 'edaily.co.kr',
    'sedaily.com', 'fnnews.com', 'heraldcorp.com',
    'asiae.co.kr', 'ajunews.com',
    # IT/전문
    'dt.co.kr', 'etnews.com', 'zdnet.co.kr', 'bloter.net',
    # 온라인 매체
    'newspim.com', 'kukinews.com', 'biz.chosun.com',
    'news.jtbc.co.kr', 'imnews.imbc.com',
}


class NewsCollector:
    """네이버 뉴스 수집기"""

    def __init__(self, sheets: SheetsManager | None = None):
        self.sheets = sheets or SheetsManager()
        self.headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }

    def _clean_html(self, text: str) -> str:
        """HTML 태그 및 엔티티 제거"""
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return ""

    def _extract_source(self, original_link: str, naver_link: str) -> str:
        """언론사명 추출 시도"""
        domain = self._extract_domain(original_link or naver_link)
        return domain.replace(".co.kr", "").replace(".com", "") or "알 수 없음"

    def _is_trusted_media(self, url: str) -> bool:
        """공신력 있는 주요 언론사인지 확인"""
        domain = self._extract_domain(url)
        if not domain:
            return False
        # 정확히 일치하거나 서브도메인 매칭
        for trusted in TRUSTED_MEDIA_DOMAINS:
            if domain == trusted or domain.endswith('.' + trusted):
                return True
        return False

    def search_naver_news(self, keyword: str) -> list[dict]:
        """
        네이버 뉴스 검색 API 호출.
        Returns:
            [{"title": ..., "link": ..., "originallink": ..., "description": ..., "pubDate": ...}, ...]
        """
        params = {
            "query": keyword,
            "display": NAVER_NEWS_DISPLAY,
            "start": 1,
            "sort": "date",
        }

        try:
            resp = requests.get(
                NAVER_SEARCH_URL,
                headers=self.headers,
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except requests.RequestException as e:
            logger.error(f"네이버 API 호출 실패 (키워드: {keyword}): {e}")
            return []

    def extract_article_body(self, url: str, timeout: int = 5) -> str:
        """
        newspaper4k를 사용하여 뉴스 원문 본문 추출.
        실패 시 빈 문자열 반환.
        """
        try:
            article = Article(url, language="ko", request_timeout=timeout)
            article.download()
            article.parse()
            return article.text or ""
        except Exception as e:
            logger.warning(f"본문 추출 실패 ({url}): {e}")
            return ""

    def collect_by_keyword(
        self,
        keyword: str,
        topic: str,
        existing_links: set[str],
    ) -> list[dict]:
        """
        단일 키워드에 대해 뉴스 검색 결과 수집 (본문 크롤링 없음).
        제목 + 네이버 요약만 포함하여 빠르게 반환.
        """
        items = self.search_naver_news(keyword)
        results = []
        today = datetime.now().strftime("%Y-%m-%d")

        skipped_media = 0
        for item in items:
            link = item.get("originallink") or item.get("link", "")

            # 주요 언론사 필터
            if not self._is_trusted_media(link):
                # 네이버 링크로 재확인
                naver_link = item.get("link", "")
                if not self._is_trusted_media(item.get("originallink", "")):
                    skipped_media += 1
                    continue

            # 중복 검사
            if link in existing_links:
                continue

            title = self._clean_html(item.get("title", ""))
            description = self._clean_html(item.get("description", ""))
            source = self._extract_source(
                item.get("originallink", ""),
                item.get("link", ""),
            )

            results.append({
                "날짜": today,
                "주제": topic,
                "언론사": source,
                "제목": title,
                "본문 전문": "",  # 1차에서는 크롤링하지 않음
                "링크": link,
                "네이버링크": item.get("link", ""),  # 크롤링 시 폴백용
                "AI 요약": "",
                "중요도": "",
                "네이버 요약": description,
            })

            existing_links.add(link)

        logger.info(
            f"[{topic}] '{keyword}' → {len(results)}건 수집 "
            f"({len(items)}건 검색, {skipped_media}건 비주요언론 제외, "
            f"{len(items) - len(results) - skipped_media}건 중복)"
        )
        return results

    def crawl_selected_articles(self, news_list: list[dict], max_workers: int = 5) -> list[dict]:
        """
        선별된 기사만 병렬로 본문 크롤링.
        Args:
            news_list: 크롤링 대상 기사 목록
            max_workers: 병렬 크롤링 스레드 수
        Returns:
            본문이 채워진 기사 목록
        """
        if not news_list:
            return news_list

        logger.info(f"선별된 {len(news_list)}건 기사 본문 크롤링 시작 (병렬 {max_workers})")

        def _crawl_one(news: dict) -> dict:
            link = news.get("링크", "")
            naver_link = news.get("네이버링크", "")
            body = self.extract_article_body(link)
            # 원문 실패 시 네이버 링크로 재시도
            if not body and naver_link and naver_link != link:
                body = self.extract_article_body(naver_link)
                if body:
                    news["링크"] = naver_link
            news["본문 전문"] = body[:40000] if body else "(본문 추출 실패)"
            return news

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_crawl_one, news): i for i, news in enumerate(news_list)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"크롤링 실패 (인덱스 {idx}): {e}")
                    news_list[idx]["본문 전문"] = "(크롤링 실패)"

        logger.info(f"크롤링 완료: {len(news_list)}건")
        return news_list

    def deduplicate_by_similarity(self, news_list: list[dict]) -> list[dict]:
        """
        제목 유사도를 기반으로 중복 기사 제거.
        유사도가 SIMILARITY_THRESHOLD 이상인 경우 하나만 남김.
        """
        if not news_list:
            return news_list

        unique_news = []
        for news in news_list:
            is_duplicate = False
            title = news.get("제목", "")
            
            for existing in unique_news:
                existing_title = existing.get("제목", "")
                # 유사도 계산
                similarity = SequenceMatcher(None, title, existing_title).ratio()
                if similarity >= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    logger.info(f"뉴스 중복 판정 (유사도 {similarity:.2f}): '{title}' vs '{existing_title}'")
                    break
            
            if not is_duplicate:
                unique_news.append(news)
        
        return unique_news

    def collect_all(self) -> list[dict]:
        """
        Settings에 등록된 모든 활성 키워드에 대해 뉴스 수집 실행.
        본문 크롤링 없이 제목+설명만 빠르게 수집.
        주제당 최대 MAX_PER_TOPIC건으로 제한.
        """
        settings = self.sheets.get_active_settings()
        if not settings:
            logger.warning("활성화된 키워드가 없습니다.")
            return []

        existing_links = self.sheets.get_existing_links()
        topic_news: dict[str, list[dict]] = {}  # 주제별 수집 결과

        for setting in settings:
            topic = setting.get("주제", "기타")
            keyword = setting.get("키워드", "")
            if not keyword:
                continue

            # 이미 주제별 최대 건수에 도달했으면 스킵
            if len(topic_news.get(topic, [])) >= MAX_PER_TOPIC:
                logger.info(f"[{topic}] 주제 최대 {MAX_PER_TOPIC}건 도달, 키워드 '{keyword}' 스킵")
                continue

            try:
                news = self.collect_by_keyword(keyword, topic, existing_links)
                topic_news.setdefault(topic, []).extend(news)
            except Exception as e:
                logger.error(f"주제 '{topic}' (키워드: '{keyword}') 수집 중 오류: {e}")
                continue

        # 주제별 중복 및 건수 제한 처리
        all_news = []
        for topic, news_list in topic_news.items():
            # 1. 유사도 기반 중복 기사 제거
            dedup_list = self.deduplicate_by_similarity(news_list)
            
            # 2. MAX_PER_TOPIC으로 제한
            capped = dedup_list[:MAX_PER_TOPIC]
            all_news.extend(capped)
            
            if len(news_list) > len(dedup_list):
                logger.info(f"[{topic}] 유사도 중복 {len(news_list) - len(dedup_list)}건 제거")
            if len(dedup_list) > MAX_PER_TOPIC:
                logger.info(f"[{topic}] {len(dedup_list)}건 → {MAX_PER_TOPIC}건으로 제한")

        logger.info(f"총 수집: {len(all_news)}건 ({len(topic_news)}개 주제)")
        return all_news
