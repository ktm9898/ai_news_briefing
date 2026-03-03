"""
scheduler.py - APScheduler 기반 자동 실행 스케줄러

매일 지정 시각에 전체 파이프라인을 실행:
  Settings 로드 → 뉴스 수집 → AI 분석 → 음성 합성
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
    """뉴스 수집, 분석, 필터링 및 시트 저장 파이프라인 실행"""
    start_time = datetime.now()
    logger.info(f"=== 파이프라인 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    result = {
        "status": "실행 중",
        "collected": 0,
        "analyzed": 0,
        "filtered": 0,
        "error": None,
    }
    
    try:
        sheets = SheetsManager()
        collector = NewsCollector(sheets)
        analyzer = AIAnalyzer()
        
        # 1. 뉴스 수집 (주제별 최대 20건)
        all_collected = collector.collect_all()
        result["collected"] = len(all_collected)
        if not all_collected:
            logger.info("수집된 새로운 뉴스가 없습니다.")
            result["status"] = "완료 (수집 없음)"
            return result

        # 2. 주제별 AI 판단 기준 로드
        topic_criteria = sheets.get_all_topic_criteria()

        # 3. AI 분석 (주제별 기준 적용)
        analyzed_news = analyzer.analyze_news(all_collected, topic_criteria)
        result["analyzed"] = len(analyzed_news)

        # 4. 필터링 및 제한 (상/중 중요도만, 주제별 최대 5건)
        by_topic = {}
        for news in analyzed_news:
            if news.get("중요도") in ["상", "중"]:
                t = news.get("주제", "기타")
                by_topic.setdefault(t, []).append(news)
        
        final_news_to_save = []
        for topic, group in by_topic.items():
            # 중요도 '상'을 우선순위로 정렬
            group.sort(key=lambda x: 0 if x.get("중요도") == "상" else 1)
            selected = group[:5]
            final_news_to_save.extend(selected)
            logger.info(f"주제 '{topic}': {len(group)}건 중 {len(selected)}건 선별")

        result["filtered"] = len(final_news_to_save)

        # 5. 시트에 저장 (Batch)
        if final_news_to_save:
            sheets.append_news(final_news_to_save)
            logger.info(f"최종 {len(final_news_to_save)}건 시트 저장 완료")
            
            # 6. 브리핑 대본 생성 및 저장
            script = analyzer.generate_briefing_script(final_news_to_save)
            sheets.save_briefing(script)
            logger.info("브리핑 대본 저장 및 파이프라인 완료")
        else:
            logger.info("조건을 만족하는 뉴스가 없어 저장하지 않았습니다.")

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
