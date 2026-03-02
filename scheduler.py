"""
scheduler.py - APScheduler 기반 자동 실행 스케줄러

매일 지정 시각에 전체 파이프라인을 실행:
  Settings 로드 → 뉴스 수집 → AI 분석 → 음성 합성
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import SCHEDULE_HOUR, SCHEDULE_MINUTE
from sheets_manager import SheetsManager
from news_collector import NewsCollector
from ai_analyzer import AIAnalyzer
from tts_engine import TTSEngine

logger = logging.getLogger(__name__)


def run_pipeline():
    """
    전체 뉴스 수집·분석·브리핑 파이프라인 실행.

    Returns:
        dict: 실행 결과 요약
    """
    start_time = datetime.now()
    logger.info(f"=== 파이프라인 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")

    result = {
        "status": "실행 중",
        "collected": 0,
        "analyzed": 0,
        "audio_path": None,
        "error": None,
    }

    try:
        # 1. 초기화
        sheets = SheetsManager()
        collector = NewsCollector(sheets)
        analyzer = AIAnalyzer()
        tts = TTSEngine()

        # 2. 뉴스 수집
        logger.info("📰 뉴스 수집 시작...")
        news_list = collector.collect_all()
        result["collected"] = len(news_list)
        logger.info(f"✅ {len(news_list)}건 수집 완료")

        if not news_list:
            result["status"] = "완료 (수집 결과 없음)"
            return result

        # 3. AI 분석 (요약 + 중요도)
        logger.info("🤖 AI 분석 시작...")
        analyzed_news = analyzer.analyze_news(news_list)
        result["analyzed"] = len(analyzed_news)
        logger.info(f"✅ {len(analyzed_news)}건 분석 완료")

        # 분석 결과를 시트에 업데이트
        sheets.append_news([])  # 이미 collect_all에서 저장됨
        # 분석 결과(AI 요약, 중요도)를 시트에 업데이트하기 위해
        # 새로 수집된 뉴스의 분석 결과만 반영
        _update_analysis_to_sheet(sheets, analyzed_news)

        # 4. 브리핑 대본 생성
        logger.info("📝 브리핑 대본 생성 중...")
        script = analyzer.generate_briefing_script(analyzed_news)

        # 5. 음성 합성
        logger.info("🎙️ 음성 합성 시작...")
        audio_path = tts.generate(script)
        result["audio_path"] = str(audio_path) if audio_path else None

        if audio_path:
            logger.info(f"✅ 오디오 생성 완료: {audio_path}")
        else:
            logger.warning("⚠️ 오디오 생성 실패")

        result["status"] = "완료"
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"=== 파이프라인 완료 ({elapsed:.1f}초 소요) ===")

    except Exception as e:
        result["status"] = "오류"
        result["error"] = str(e)
        logger.error(f"파이프라인 실행 오류: {e}", exc_info=True)

    return result


def _update_analysis_to_sheet(sheets: SheetsManager, news_list: list[dict]):
    """분석 결과를 Google Sheets에 업데이트"""
    try:
        ws = sheets.spreadsheet.worksheet("News_Data")
        all_data = ws.get_all_records()

        for news in news_list:
            link = news.get("링크", "")
            summary = news.get("AI 요약", "")
            importance = news.get("중요도", "")
            if not link or not summary:
                continue

            # 링크로 행 찾기
            for idx, row in enumerate(all_data):
                if row.get("링크") == link:
                    row_num = idx + 2  # 헤더 + 0-indexed → 1-indexed
                    sheets.update_news_analysis(row_num, summary, importance)
                    break
    except Exception as e:
        logger.error(f"분석 결과 시트 업데이트 실패: {e}")


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
