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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# KST (UTC+9) 타임존 정의
KST = timezone(timedelta(hours=9))
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

    def _is_within_24h(self, pub_date_str: str) -> bool:
        """
        pubDate(RFC 822 형식)를 파싱하여 최근 24시간 이내 기사인지 확인.
        예: 'Thu, 05 Mar 2026 10:30:00 +0900'
        파싱 실패 시 False 반환 (오래된 기사로 간주하여 제외).
        """
        if not pub_date_str:
            return False
        try:
            pub_dt = parsedate_to_datetime(pub_date_str)
            now = datetime.now(KST)
            return now - pub_dt.astimezone(KST) <= timedelta(hours=24)
        except Exception:
            logger.warning(f"pubDate 파싱 실패: '{pub_date_str}'")
            return False

    def _extract_date_from_pubdate(self, pub_date_str: str) -> str:
        """
        조회된 기사의 실제 날짜와 무관하게, 항상 오늘 날짜 반환.
        나중에 시트나 화면에서 필터링 시 기사들이 흩어지지 않도록 조치.
        """
        return datetime.now(KST).strftime("%Y-%m-%d")

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

        skipped_media = 0
        skipped_old = 0
        for item in items:
            # 최근 24시간 기사만 수집
            if not self._is_within_24h(item.get("pubDate", "")):
                skipped_old += 1
                continue

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
            article_date = self._extract_date_from_pubdate(item.get("pubDate", ""))

            results.append({
                "날짜": article_date,
                "주제": topic,
                "언론사": source,
                "제목": title,
                "본문 전문": "",  # 1차에서는 크롤링하지 않음
                "링크": link,
                "original_link": link,  # AI 선정용 변하지 않는 고유 링크 (매핑용)
                "네이버링크": item.get("link", ""),  # 크롤링 시 폴백용
                "AI 요약": "",
                "중요도": "",
                "네이버 요약": description,
            })

            existing_links.add(link)

        logger.info(
            f"[{topic}] '{keyword}' → {len(results)}건 수집 "
            f"({len(items)}건 검색, {skipped_old}건 24시간 경과, "
            f"{skipped_media}건 비주요언론 제외, "
            f"{len(items) - len(results) - skipped_media - skipped_old}건 중복)"
        )
        return results

    def collect_headlines(self, existing_links: set[str]) -> list[dict]:
        """
        주요 경제지(매경, 한경 등)의 최신/헤드라인 뉴스를 직접 검색하여 수집.
        네이버 검색 API의 언론사 필터링 기능을 활용 (정확한 기계적 필터는 아니지만 높은 확률로 타겟팅).
        """
        target_press = ["매일경제", "한국경제", "서울경제", "머니투데이", "연합뉴스"]
        headline_news = []
        
        # '경제', '경영', '산업', '반도체', '증시' 키워드로 주요 경제지 필터링 검색
        # 네이버 API 팁: "query (언론사명)" 형태로 검색하면 해당 언론사가 포함된 결과 위주로 나옴
        skipped_old = 0
        # 1. 주요 경제지의 경제 메인 섹션 검색 (기존)
        search_targets = []
        for press in target_press:
            search_targets.append(f"{press} 경제 메인")
            
        # 2. 글로벌 경제/증시 핵심 키워드 추가 (해외 주요뉴스 확보용)
        search_targets.extend(["글로벌 경제", "뉴욕증시", "나스닥", "세계 경제", "미국 증시"])

        skipped_old = 0
        for target in search_targets:
            items = self.search_naver_news(target)
            
            for item in items:
                # 최근 24시간 기사만 수집
                if not self._is_within_24h(item.get("pubDate", "")):
                    skipped_old += 1
                    continue

                link = item.get("originallink") or item.get("link", "")
                if link in existing_links:
                    continue
                    
                title = self._clean_html(item.get("title", ""))
                description = self._clean_html(item.get("description", ""))
                source = self._extract_source(item.get("originallink", ""), item.get("link", ""))
                article_date = self._extract_date_from_pubdate(item.get("pubDate", ""))
                
                # 명시된 언론사 도메인 화이트리스트 재검색 (퀄리티 보장)
                if not self._is_trusted_media(link):
                    continue
                
                headline_news.append({
                    "날짜": article_date,
                    "주제": "경제헤드라인", # 내부 처리용 주제명
                    "언론사": source,
                    "제목": title,
                    "본문 전문": "",
                    "링크": link,
                    "original_link": link,
                    "네이버링크": item.get("link", ""),
                    "AI 요약": "",
                    "중요도": "",
                    "네이버 요약": description,
                })
                existing_links.add(link)
                
        logger.info(f"경제지 헤드라인 직접 수집 완료: {len(headline_news)}건 ({skipped_old}건 24시간 경과 제외)")
        return headline_news

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
            title = news.get("제목", "")[:20]
            link = news.get("링크", "")
            naver_link = news.get("네이버링크", "")
            body = self.extract_article_body(link)
            
            # 원문 실패 시 네이버 링크로 재시도
            if not body and naver_link and naver_link != link:
                logger.info(f"원문 크롤링 실패, 네이버 링크 재시도: {title}...")
                body = self.extract_article_body(naver_link)
                if body:
                    news["링크"] = naver_link
                    logger.info(f"네이버 링크로 크롤링 성공: {title}")
            
            if not body:
                logger.warning(f"본문 추출 최종 실패: {title} ({link})")

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
        1. 주요 경제지 헤드라인 수집
        2. Settings에 등록된 모든 활성 키워드 수집
        3. 전체 기사 전역 중복 제거 적용
        """
        settings = self.sheets.get_active_settings()
        existing_links = self.sheets.get_existing_links()
        
        # ── 1단계: 주요 경제 매체 헤드라인 수집 (Top 5 후보군 확보) ──
        headline_news = self.collect_headlines(existing_links)
        
        # ── 2단계: 주제별 키워드 수집 ──
        topic_news: dict[str, list[dict]] = {}
        for setting in settings:
            topic = setting.get("주제", "기타")
            keyword = setting.get("키워드", "")
            if not keyword or len(topic_news.get(topic, [])) >= MAX_PER_TOPIC:
                continue

            try:
                news = self.collect_by_keyword(keyword, topic, existing_links)
                topic_news.setdefault(topic, []).extend(news)
            except Exception as e:
                logger.error(f"주제 '{topic}' (키워드: '{keyword}') 수집 중 오류: {e}")

        # 전체 수집 결과 통합 (헤드라인 + 키워드 뉴스)
        all_collected_raw = headline_news[:]
        for news_list in topic_news.values():
            all_collected_raw.extend(news_list)

        # ── 3단계: 전역 중복 제거 (유사도 기준 강화) ──
        dedup_list = self.deduplicate_by_similarity(all_collected_raw)
        
        # ── 4단계: 주제별 건수 재조정 및 최종 리스트화 ──
        # 헤드라인 뉴스는 그대로 유지하고, 주제별 뉴스는 다시 캡핑 적용
        final_topic_news = {"경제헤드라인": []}
        for news in dedup_list:
            t = news.get("주제", "기타")
            if t == "경제헤드라인":
                final_topic_news["경제헤드라인"].append(news)
            elif len(final_topic_news.get(t, [])) < MAX_PER_TOPIC:
                final_topic_news.setdefault(t, []).append(news)
        
        all_news = []
        for t, news_list in final_topic_news.items():
            all_news.extend(news_list)

        if len(all_collected_raw) > len(dedup_list):
            logger.info(f"전역 중복 {len(all_collected_raw) - len(dedup_list)}건 제거 완료")
        
        logger.info(f"최종 수집 완료: 총 {len(all_news)}건 (헤드라인 {len(final_topic_news['경제헤드라인'])}건 포함)")
        return all_news
