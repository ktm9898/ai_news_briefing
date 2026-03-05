"""
scheduler.py - APScheduler 기반 자동 실행 스케줄러

2단계 AI 파이프라인:
  1. 네이버 API 검색 (크롤링 없이 제목+설명만)
  2. AI 1차: 중요도 선별
  3. 중요 기사만 본문 크롤링 (병렬)
  4. AI 2차: 요약 + 브리핑 대본 동시 생성
  5. 시트 저장
"""

import logging
from datetime import datetime, timedelta, timezone

# KST (UTC+9) 타임존 정의
KST = timezone(timedelta(hours=9))

from apscheduler.schedulers.background import BackgroundScheduler

from config import SCHEDULE_HOUR, SCHEDULE_MINUTE, DEFAULT_CRITERIA, MAX_PER_TOPIC
from sheets_manager import SheetsManager
from news_collector import NewsCollector
from ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


def run_pipeline():
    """2단계 AI 파이프라인 실행"""
    start_time = datetime.now(KST)
    logger.info(f"=== 파이프라인 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')} (KST) ===")

    result = {
        "status": "실행 중",
        "collected": 0,
        "screened": 0,
        "crawled": 0,
        "analyzed": 0,
        "error": None,
    }

    try:
        sheets = SheetsManager()
        collector = NewsCollector(sheets)
        analyzer = AIAnalyzer()

        # ── 1단계: 네이버 API 검색 (크롤링 없음, 빠름) ──
        logger.info("STEP 1/5: 네이버 API 뉴스 검색 (크롤링 없음)")
        all_collected = collector.collect_all()
        result["collected"] = len(all_collected)

        if not all_collected:
            logger.info("수집된 새로운 뉴스가 없습니다.")
            result["status"] = "완료 (수집 없음)"
            return result

        elapsed_1 = (datetime.now(KST) - start_time).total_seconds()
        logger.info(f"STEP 1 완료: {len(all_collected)}건 ({elapsed_1:.1f}초)")

        # ── 2단계: AI 1차 선별 (중요도 판별 + Top6 선정) ──
        logger.info("STEP 2/6: AI 1차 중요도 선별 + 주요뉴스 Top6 선정")
        topic_criteria = sheets.get_all_topic_criteria()
        active_settings = sheets.get_active_settings()
        exclusion_keywords = list(set(s.get("키워드", "") for s in active_settings if s.get("키워드")))
        
        all_collected, top6_results = analyzer.screen_importance(
            all_collected, 
            topic_criteria, 
            exclusion_keywords=exclusion_keywords
        )


        # Top6 주요뉴스 인덱스 및 링크 추출
        top6_indices = []
        top6_links = set()
        if top6_results:
            for item in top6_results:
                idx = item.get("index", 1) - 1
                top6_indices.append(idx)
                if 0 <= idx < len(all_collected):
                    link = all_collected[idx].get("링크", "")
                    if link:
                        top6_links.add(link)
            logger.info(f"Top6 주요뉴스 {len(top6_indices)}건 선정 (인덱스: {top6_indices})")

        # 주제별 그룹화 및 중요도 순 정렬
        topic_groups = {}
        for news in all_collected:
            t = news.get("주제", "기타")
            # '경제헤드라인'은 Top 6 선정을 위한 내부 풀이므로 일반 주제 목록에 포함하지 않음
            if t == "경제헤드라인":
                continue
            topic_groups.setdefault(t, []).append(news)

        importance_map = {"상": 0, "중": 1, "하": 2, "": 3}
        final_selection_for_save = [] # 최종적으로 시트에 저장될 기사들 (Top6 제외)

        for topic, group in topic_groups.items():
            # 중요도 순으로 정렬 (상 -> 중 -> 하)
            sorted_group = sorted(group, key=lambda x: importance_map.get(x.get("중요도", ""), 3))
            
            # Top6에 선정된 기사는 일반 주제 목록에서 제외 (링크 기반 중복 방지)
            filtered_group = [item for item in sorted_group 
                              if item.get("링크", "") not in top6_links]

            # 기사가 있다면 무조건 5건을 채움 (모자라면 있는 만큼만)
            selected = filtered_group[:5]
            final_selection_for_save.extend(selected)
            
            logger.info(f"[{topic}] 총 {len(group)}건 중 {len(selected)}건 최종 선별 완료 (5건 목표)")
            
        # ── 3단계: 기사 본문 크롤링 (Top6 + 선별된 5건씩) ──
        logger.info("STEP 3/6: 주요 기사 본문 크롤링")
        
        # 크롤링 대상: Top6에 속한 기사 원본들 + 각 주제별로 선별된 5건씩
        top6_source_news = [n for n in all_collected if n.get("링크") in top6_links]
        selected_for_crawl = top6_source_news + final_selection_for_save
        
        # 중복 제거 (혹시 모를 경우대비 링크 기준)
        seen_links = set()
        unique_crawl_list = []
        for n in selected_for_crawl:
            link = n.get("링크")
            if link not in seen_links:
                unique_crawl_list.append(n)
                seen_links.add(link)

        if not unique_crawl_list:
            logger.info("분석/저장할 기사가 없습니다.")
            result["status"] = "완료 (기사 없음)"
            return result
        
        # 본문 크롤링 수행
        selected_for_crawl = collector.crawl_selected_articles(unique_crawl_list)
        result["crawled"] = len(selected_for_crawl)

        elapsed_3 = (datetime.now(KST) - start_time).total_seconds()
        logger.info(f"STEP 3 완료: {len(selected_for_crawl)}건 크롤링 완료 ({elapsed_3:.1f}초)")

        # ── 4단계: AI 2차 — 요약 + 브리핑 대본 동시 생성 ──
        logger.info("STEP 4/6: AI 2차 요약 + 브리핑 대본 생성")
        # 크롤링된 모든 기사(Top6 포함)에 대해 요약 수행
        selected_for_crawl, briefing_script = analyzer.summarize_and_brief(selected_for_crawl)
        result["analyzed"] = len(selected_for_crawl)

        elapsed_4 = (datetime.now(KST) - start_time).total_seconds()
        logger.info(f"STEP 4 완료: 요약 + 대본 생성 ({elapsed_4:.1f}초)")

        # ── 5단계: 시트 저장 ──
        logger.info("STEP 5/6: Google Sheets 저장")

        # 최종 저장용 주요뉴스 리스트 생성 (Top6)
        top6_news = []
        if top6_results:
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            # 본문 내용을 크롤링 결과에서 가져옴
            crawled_bodies = {n.get("링크"): n.get("본문 전문", "") for n in selected_for_crawl}
            
            for item in top6_results:
                link = item.get("링크", "")
                region_label = "국내" if item.get("region") == "국내" else "해외"
                top6_entry = {
                    "날짜": today_str,
                    "주제": f"📌 주요뉴스({region_label})",
                    "언론사": item.get("언론사", ""),
                    "제목": item.get("제목", ""),
                    "네이버 요약": item.get("네이버 요약", ""),
                    "본문 전문": crawled_bodies.get(link, item.get("본문 전문", "")),
                    "링크": link,
                    "AI 요약": item.get("AI 요약") or item.get("summary", ""),
                    "중요도": "상",
                }
                top6_news.append(top6_entry)

        # 저장할 데이터 준비: Top6 기사는 일반 목록에서 제외하고, 주요뉴스로만 저장
        if selected_for_crawl:
            import copy
            
            # 1. 선정된 Top6 기사 제외 및 내부 마커(경제헤드라인, 기타...) 기사 제외
            # 2. 주제별로 최대 건수(MAX_PER_TOPIC) 재조정 (AI 선별 후 과다 발생 방지)
            topic_counts = {}
            regular_news = []
            
            for n in selected_for_crawl:
                link = n.get("링크", "")
                topic = n.get("주제", "기타")
                
                # 주요뉴스(Top6)에 포함된 건은 이미 별도로 처리함
                if link in top6_links:
                    continue
                    
                # 내부 분류용 마커 기사들은 주요뉴스 탈락 시 폐기함
                if topic in ["경제헤드라인", "기타(세부관심사)", "기타"]:
                    continue
                
                # 주제별 최대 건수 초과 시 제외
                if topic_counts.get(topic, 0) >= MAX_PER_TOPIC:
                    continue
                
                regular_news.append(n)
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
            
            # 네이버링크 필드 제거 (시트에 불필요)
            save_list = copy.deepcopy(regular_news)
            for news in save_list:
                news.pop("네이버링크", None)
            
            # Top6 주요뉴스 + 일반 기사를 합쳐서 저장 (Top6가 먼저)
            final_save = top6_news + save_list
            sheets.append_news(final_save)
            logger.info(f"최종 저장: Top6 {len(top6_news)}건 + 일반 {len(save_list)}건 = 총 {len(final_save)}건")

            # 브리핑 대본 저장
            sheets.save_briefing(briefing_script)
            logger.info("브리핑 대본 저장 완료")
        else:
            logger.info("저장할 뉴스가 없습니다.")

        # ── 6단계: TTS 음성 생성 ──
        logger.info("STEP 6/6: TTS 음성 파일 생성")
        try:
            from tts_engine import TTSEngine
            tts = TTSEngine()
            audio_path = tts.generate(briefing_script)
            if audio_path:
                logger.info(f"음성 파일 생성 완료: {audio_path}")
            else:
                logger.warning("음성 파일 생성 실패 (대본은 저장됨)")
        except Exception as e:
            logger.error(f"TTS 생성 중 오류 (무시): {e}")

        result["status"] = "완료"
        elapsed = (datetime.now(KST) - start_time).total_seconds()
        logger.info(f"=== 파이프라인 완료 ({elapsed:.1f}초) ===")

    except Exception as e:
        result["status"] = "오류"
        result["error"] = str(e)
        logger.error(f"파이프라인 실행 중 오류: {e}", exc_info=True)

    return result


class NewsScheduler:
    """APScheduler 기반 뉴스 수집 스케줄러"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self._is_running = False

    def start(self):
        """매일 지정 시각에 파이프라인 실행 스케줄 등록"""
        if self._is_running:
            logger.info("스케줄러가 이미 실행 중입니다.")
            return

        self.scheduler.add_job(
            run_pipeline,
            "cron",
            hour=SCHEDULE_HOUR,
            minute=SCHEDULE_MINUTE,
            id="daily_news_pipeline",
            replace_existing=True,
        )
        self.scheduler.start()
        self._is_running = True
        logger.info(
            f"스케줄러 시작: 매일 {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}에 실행"
        )

    def stop(self):
        """스케줄러 중지"""
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("스케줄러 중지됨")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_next_run(self) -> str:
        """다음 실행 예정 시각"""
        jobs = self.scheduler.get_jobs()
        if jobs:
            next_run = jobs[0].next_run_time
            return next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "미정"
        return "미정"
