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
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import SCHEDULE_HOUR, SCHEDULE_MINUTE, DEFAULT_CRITERIA
from sheets_manager import SheetsManager
from news_collector import NewsCollector
from ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


def run_pipeline():
    """2단계 AI 파이프라인 실행"""
    start_time = datetime.now()
    logger.info(f"=== 파이프라인 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")

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

        elapsed_1 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 1 완료: {len(all_collected)}건 ({elapsed_1:.1f}초)")

        # ── 2단계: AI 1차 선별 (제목+설명만으로 중요도 판별) ──
        logger.info("STEP 2/5: AI 1차 중요도 선별")
        topic_criteria = sheets.get_all_topic_criteria()
        all_collected = analyzer.screen_importance(all_collected, topic_criteria)

        # 중요 기사(상) 선별 + 주제별 최대 5건 제한
        important_news = [n for n in all_collected if n.get("중요도") == "상"]
        other_news = [n for n in all_collected if n.get("중요도") != "상"]

        # 주제별 '상' 기사 수 제한 (주제당 최대 5건)
        by_topic = {}
        for news in important_news:
            t = news.get("주제", "기타")
            by_topic.setdefault(t, []).append(news)

        selected_for_crawl = []
        for topic, group in by_topic.items():
            selected = group[:5]
            selected_for_crawl.extend(selected)
            logger.info(f"선별 [{topic}]: {len(group)}건 중 {len(selected)}건")

        result["screened"] = len(selected_for_crawl)

        elapsed_2 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 2 완료: {len(selected_for_crawl)}건 선별 ({elapsed_2:.1f}초)")

        if not selected_for_crawl:
            logger.info("중요도 '상' 기사가 없습니다. 전체를 '중'으로 저장합니다.")
            # 중요 기사가 없으면 주제별 상위 3건씩 선별
            for news in all_collected:
                t = news.get("주제", "기타")
                by_topic.setdefault(t, [])
            by_topic_all = {}
            for news in all_collected:
                t = news.get("주제", "기타")
                by_topic_all.setdefault(t, []).append(news)
            for topic, group in by_topic_all.items():
                selected_for_crawl.extend(group[:3])
            result["screened"] = len(selected_for_crawl)

        # ── 3단계: 선별된 기사만 본문 크롤링 (병렬) ──
        logger.info(f"STEP 3/5: 선별된 {len(selected_for_crawl)}건 본문 크롤링 (병렬)")
        selected_for_crawl = collector.crawl_selected_articles(selected_for_crawl)
        result["crawled"] = len(selected_for_crawl)

        elapsed_3 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 3 완료: 크롤링 완료 ({elapsed_3:.1f}초)")

        # ── 4단계: AI 2차 — 요약 + 브리핑 대본 동시 생성 ──
        logger.info("STEP 4/5: AI 2차 요약 + 브리핑 대본 생성")
        selected_for_crawl, briefing_script = analyzer.summarize_and_brief(selected_for_crawl)
        result["analyzed"] = len(selected_for_crawl)

        elapsed_4 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 4 완료: 요약 + 대본 생성 ({elapsed_4:.1f}초)")

        # ── 5단계: 시트 저장 ──
        logger.info("STEP 5/5: Google Sheets 저장")

        # 저장할 데이터 준비 (선별된 중요 기사 + 비선별 기사 요약 없이)
        # 중요 기사만 저장
        if selected_for_crawl:
            # 네이버링크 필드 제거 (시트에 불필요)
            for news in selected_for_crawl:
                news.pop("네이버링크", None)
            sheets.append_news(selected_for_crawl)
            logger.info(f"최종 {len(selected_for_crawl)}건 시트 저장 완료")

            # 브리핑 대본 저장
            sheets.save_briefing(briefing_script)
            logger.info("브리핑 대본 저장 완료")
        else:
            logger.info("저장할 뉴스가 없습니다.")

        result["status"] = "완료"
        elapsed = (datetime.now() - start_time).total_seconds()
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
