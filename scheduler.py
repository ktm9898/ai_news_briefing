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

        # ── 2단계: AI 1차 선별 (중요도 판별 + Top5 선정) ──
        logger.info("STEP 2/6: AI 1차 중요도 선별 + Top5 선정")
        topic_criteria = sheets.get_all_topic_criteria()
        all_collected, top5_results = analyzer.screen_importance(all_collected, topic_criteria)

        # Top5 주요뉴스 인덱스 추출 및 크롤링 대상 강제 포함 (크롤링 이후에 최종 생성)
        top5_indices = []
        if top5_results:
            top5_indices = [item.get("index", 1) - 1 for item in top5_results]
            logger.info(f"Top5 주요뉴스 인덱스: {top5_indices}")

        # 주제별 그룹화 및 중요도 순 정렬
        topic_groups = {}
        for news in all_collected:
            t = news.get("주제", "기타")
            topic_groups.setdefault(t, []).append(news)

        selected_for_crawl = []
        importance_map = {"상": 0, "중": 1, "하": 2, "": 3}

        for topic, group in topic_groups.items():
            # 중요도 순으로 정렬 (상 -> 중 -> 하)
            sorted_group = sorted(group, key=lambda x: importance_map.get(x.get("중요도", ""), 3))
            selected = sorted_group[:5]  # 주제별 최대 5건
            selected_for_crawl.extend(selected)
            
        # Top5 주요뉴스는 주제별 순위와 관계없이 크롤링 대상에 무조건 포함
        for idx in top5_indices:
            if 0 <= idx < len(all_collected):
                news_item = all_collected[idx]
                if news_item not in selected_for_crawl:
                    selected_for_crawl.append(news_item)
                    logger.info(f"Top5 기사 크롤링 대상 추가: {news_item.get('제목')[:20]}...")
            
            logger.info(
                f"[{topic}] 총 {len(group)}건 중 상위 {len(selected)}건 선별 "
                f"(상:{sum(1 for n in selected if n.get('중요도') == '상')}, "
                f"중:{sum(1 for n in selected if n.get('중요도') == '중')}, "
                f"하:{sum(1 for n in selected if n.get('중요도') == '하')})"
            )

        result["screened"] = len(selected_for_crawl)

        elapsed_2 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 2 완료: 총 {len(selected_for_crawl)}건 선별 ({elapsed_2:.1f}초)")

        if not selected_for_crawl:
            logger.info("선별된 기사가 없습니다.")
            result["status"] = "완료 (기사 없음)"
            return result

        # ── 3단계: 선별된 기사만 본문 크롤링 (병렬) ──
        logger.info(f"STEP 3/6: 선별된 {len(selected_for_crawl)}건 본문 크롤링 (병렬)")
        selected_for_crawl = collector.crawl_selected_articles(selected_for_crawl)
        result["crawled"] = len(selected_for_crawl)

        elapsed_3 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 3 완료: 크롤링 완료 ({elapsed_3:.1f}초)")

        # ── 4단계: AI 2차 — 요약 + 브리핑 대본 동시 생성 ──
        logger.info("STEP 4/6: AI 2차 요약 + 브리핑 대본 생성")
        selected_for_crawl, briefing_script = analyzer.summarize_and_brief(selected_for_crawl)
        result["analyzed"] = len(selected_for_crawl)

        elapsed_4 = (datetime.now() - start_time).total_seconds()
        logger.info(f"STEP 4 완료: 요약 + 대본 생성 ({elapsed_4:.1f}초)")

        # ── 5단계: 시트 저장 ──
        logger.info("STEP 5/6: Google Sheets 저장")

        # 크롤링 완료된 결과에서 Top5 주요뉴스 리스트 최종 생성 (본문 포함)
        top5_news = []
        if top5_results:
            today = datetime.now().strftime("%Y-%m-%d")
            for item in top5_results:
                idx = item.get("index", 1) - 1
                if 0 <= idx < len(all_collected):
                    source_news = all_collected[idx]
                    top5_entry = {
                        "날짜": today,
                        "주제": "📌 주요뉴스",
                        "언론사": source_news.get("언론사", ""),
                        "제목": source_news.get("제목", ""),
                        "네이버 요약": source_news.get("네이버 요약", ""),
                        "본문 전문": source_news.get("본문 전문", ""),
                        "링크": source_news.get("링크", ""),
                        "AI 요약": item.get("summary", ""),
                        "중요도": "상",
                    }
                    top5_news.append(top5_entry)

        # 저장할 데이터 준비 (선별된 중요 기사 + 비선별 기사 요약 없이)
        # 중요 기사만 저장
        if selected_for_crawl:
            # 네이버링크 필드 제거 (시트에 불필요)
            import copy
            save_list = copy.deepcopy(selected_for_crawl)
            for news in save_list:
                news.pop("네이버링크", None)
            sheets.append_news(save_list)
            logger.info(f"최종 {len(save_list)}건 시트 저장 완료")

            # Top5 주요뉴스도 시트에 저장
            if top5_news:
                sheets.append_news(top5_news)
                logger.info(f"Top5 주요뉴스 {len(top5_news)}건 시트 저장 완료")

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
