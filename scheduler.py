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
import requests
import re
from datetime import datetime, timedelta, timezone

# KST (UTC+9) 타임존 정의
KST = timezone(timedelta(hours=9))

from apscheduler.schedulers.background import BackgroundScheduler

from config import SCHEDULE_HOUR, SCHEDULE_MINUTE, DEFAULT_CRITERIA, MAX_DISPLAY_PER_TOPIC, GWS_ENABLED, GAS_SCRIPT_URL
from sheets_manager import SheetsManager
from news_collector import NewsCollector
from ai_analyzer import AIAnalyzer
from utils import get_weather_info
from gws_manager import GWSManager


logger = logging.getLogger(__name__)


def run_pipeline():
    """2단계 AI 파이프라인 실행"""
    start_time = datetime.now(KST)
    logger.info(f"=== 파이프라인 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')} (KST) ===")

    result = {
        "status": "실행 중",
        "processed_users": [],
        "errors": {},
        "collected": 0,
        "analyzed": 0,
    }

    try:
        sheets = SheetsManager()
        collector = NewsCollector(sheets)
        analyzer = AIAnalyzer()

        logger.info("--- 뉴스 브리핑 생성 시작 ---")
        # ── 1단계: 네이버 API 검색 (크롤링 없음, 빠름) ──
        logger.info("STEP 1/7: 네이버 API 뉴스 검색")
        all_collected = collector.collect_all()
        result["collected"] += len(all_collected)

        if not all_collected:
            logger.info("수집된 새로운 뉴스가 없습니다.")
            result["status"] = "완료"
            return result

        # ── 2단계: AI 1차 선별 (중요도 판별 + 주요뉴스 선정) ──
        logger.info("STEP 2/7: AI 중요도 선별 + 주요뉴스 선정")
        topic_criteria = sheets.get_all_topic_criteria()
        topic_max_counts = sheets.get_topic_max_counts()
        user_active_settings = sheets.get_active_settings()
        exclusion_keywords = list(set(s.get("키워드", "") for s in user_active_settings if s.get("키워드")))

        all_collected, main_news_results = analyzer.screen_importance(
            all_collected,
            topic_criteria,
            exclusion_keywords=exclusion_keywords,
            topic_max_counts=topic_max_counts
        )

        # 주요뉴스 링크 추출
        main_news_links = set()
        if main_news_results:
            for item in main_news_results:
                link = item.get("original_link") or item.get("링크", "")
                if link:
                    main_news_links.add(link)
            logger.info(f"주요뉴스 {len(main_news_links)}건 선정 완료")

        # 주제별 그룹화 및 중요도 순 정렬
        topic_groups = {}
        for news in all_collected:
            t = news.get("주제", "기타")
            if t == "경제헤드라인":
                continue
            topic_groups.setdefault(t, []).append(news)

        importance_map = {"상": 0, "중": 1, "하": 2, "": 3}
        final_selection_for_save = []

        for topic, group in topic_groups.items():
            selected = [item for item in group if item.get("ai_selected") is True]
            max_c = topic_max_counts.get(topic, 5)

            if not selected:
                sorted_group = sorted(group, key=lambda x: importance_map.get(x.get("중요도", ""), 3))
                filtered_group = [item for item in sorted_group if item.get("링크", "") not in main_news_links]
                selected = filtered_group[:max_c]
                logger.info(f"[{topic}] AI 직접 선정 결과 없음 -> 중요도 순 {len(selected)}건 자동 선정")
            else:
                selected = [item for item in selected if item.get("링크", "") not in main_news_links]
                selected = selected[:max_c]

            final_selection_for_save.extend(selected)

        # ── 3단계: 기사 본문 크롤링 ──
        logger.info("STEP 3/7: 주요 기사 본문 크롤링")
        main_news_source_news = [n for n in all_collected if n.get("링크") in main_news_links]
        selected_for_crawl = main_news_source_news + final_selection_for_save

        for n in selected_for_crawl:
            n["is_essential"] = True

        seen_links = set()
        unique_crawl_list = []
        for n in selected_for_crawl:
            link = n.get("링크")
            if link not in seen_links:
                unique_crawl_list.append(n)
                seen_links.add(link)

        if not unique_crawl_list:
            logger.info("분석할 기사가 없습니다.")
            result["status"] = "완료"
            return result

        selected_for_crawl = collector.crawl_selected_articles(unique_crawl_list)
        result["analyzed"] += len(selected_for_crawl)

        # ── 4단계: AI 통합 분석 (요약 + 대본 + 인사이트 리포트) ──
        logger.info("STEP 4/7: AI 통합 분석 수행")
        days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        now = datetime.now(KST)
        weekday_str = days[now.weekday()]
        date_str = now.strftime("%Y년 %m월 %d일")
        weather_str = get_weather_info()

        context_info = f"현재 일시: {date_str} {weekday_str}\n날씨 정보: {weather_str}"
        analysis_result = analyzer.analyze_all_in_one(
            selected_for_crawl, 
            context_info=context_info, 
            generate_insight=True
        )

        briefing_script = analysis_result.get("briefing_script", "")
        insight_data = analysis_result.get("insight_report")
        
        # 인사이트 리포트 참고출처 URL 보강 (Google Search Grounding)
        if insight_data:
            insight_data = analyzer.enrich_references_with_urls(insight_data)

        # ── 5단계: 시트 저장 ──
        logger.info("STEP 5/7: 데이터 시트 저장")
        main_news_save_list = []
        if main_news_results:
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            crawled_lookup = {}
            for n in selected_for_crawl:
                key = n.get("original_link") or n.get("링크")
                if key:
                    crawled_lookup[key] = n
                if n.get("네이버링크"):
                    crawled_lookup.setdefault(n["네이버링크"], n)

            for item in main_news_results:
                link = item.get("original_link") or item.get("링크", "")
                article_info = crawled_lookup.get(link)
                if not article_info:
                    for n in selected_for_crawl:
                        if n.get("original_link") == link or n.get("링크") == link or n.get("네이버링크") == link:
                            article_info = n
                            break

                region_label = "국내" if item.get("region") == "국내" else "해외"
                final_body = article_info.get("본문 전문", "") if article_info else item.get("본문 전문", "")
                final_summary = (article_info.get("AI 요약") if article_info else "") or item.get("summary", "")

                main_news_save_list.append({
                    "날짜": today_str,
                    "주제": f"📌 주요뉴스({region_label})",
                    "언론사": item.get("언론사", ""),
                    "제목": article_info.get("제목", item.get("제목", "")) if article_info else item.get("제목", ""),
                    "네이버 요약": item.get("네이버 요약", ""),
                    "본문 전문": final_body,
                    "링크": item.get("링크", ""),
                    "AI 요약": final_summary,
                    "중요도": "상",
                })

            main_news_save_list.sort(key=lambda x: 0 if "해외" in x.get("주제", "") else 1)

        import copy
        topic_counts = {}
        regular_news = []

        for n in selected_for_crawl:
            link = n.get("링크", "")
            topic = n.get("주제", "기타")
            if link in main_news_links:
                continue
            if topic in ["경제헤드라인", "기타(세부관심사)", "기타"]:
                continue
            if topic_counts.get(topic, 0) >= MAX_DISPLAY_PER_TOPIC:
                continue
            regular_news.append(n)
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        save_list = copy.deepcopy(regular_news)
        for news in save_list:
            news.pop("네이버링크", None)

        final_save = main_news_save_list + save_list
        sheets.append_news(final_save)

        if briefing_script:
            sheets.save_briefing(briefing_script)

        # ── 6단계: TTS 음성 생성 ──
        logger.info("STEP 6/7: TTS 음성 생성")
        try:
            from tts_engine import TTSEngine
            tts = TTSEngine()
            audio_path = tts.generate(briefing_script, prefix="briefing_daily")
            if audio_path:
                logger.info(f"음성 파일 생성 완료: {audio_path}")
        except Exception as e:
            logger.error(f"TTS 생성 오류 (무시): {e}")

        # ── 7단계: AI 인사이트 리포트 저장 ──
        logger.info("STEP 7/7: 인사이트 리포트 저장")
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        doc_title = f"서울신용보증재단 인사이트 리포트 ({today_str})"
        
        import json
        if insight_data:
            doc_content = json.dumps(insight_data, ensure_ascii=False)
            sheets.save_briefing_doc(today_str, doc_title, doc_content)
            # 전체 등록된 이메일 구독자 대상 일일 인사이트 리포트 자동 발송
            try:
                sheets.trigger_email_dispatch("daily")
            except Exception as mail_err:
                logger.error(f"일일 메일 발송 중 오류 (파이프라인 결과에 영향 없음): {mail_err}")

        # ── 일요일인 경우 주간 소기업·소상공인 인사이트 리포트 생성 ──
        if now.weekday() == 6:  # 6=일요일
            logger.info("📅 일요일 주간 소상공인 인사이트 리포트 생성 프로세스 시작")
            try:
                end_date_str = now.strftime("%Y-%m-%d")
                start_date_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")
                weekly_date_range = f"{start_date_str} ~ {end_date_str}"
                
                logger.info(f"주간 날짜 범위: {weekly_date_range}")
                weekly_news = sheets.get_news_by_date_range(start_date_str, end_date_str)
                logger.info(f"지난 7일간 뉴스 수집 건수: {len(weekly_news)}건")
                
                if weekly_news:
                    weekly_insight_data = analyzer.analyze_weekly_insight(weekly_news, weekly_date_range)
                    if weekly_insight_data:
                        weekly_insight_data = analyzer.enrich_references_with_urls(weekly_insight_data)
                        weekly_title = f"소기업·소상공인 주간 인사이트 리포트 ({weekly_date_range})"
                        sheets.save_weekly_briefing_doc(
                            weekly_title, 
                            json.dumps(weekly_insight_data, ensure_ascii=False), 
                            weekly_date_range
                        )
                        logger.info("Weekly_Briefing_Docs 저장 성공")
                        # 전체 등록된 이메일 구독자 대상 주간 인사이트 리포트 자동 발송
                        try:
                            sheets.trigger_email_dispatch("weekly")
                        except Exception as wmail_err:
                            logger.error(f"주간 메일 발송 중 오류: {wmail_err}")
                else:
                    logger.warning("지난 7일간 기사 데이터가 존재하지 않아 주간 리포트를 생성할 수 없습니다.")
            except Exception as weekly_err:
                logger.error(f"주간 리포트 생성 중 오류 발생: {weekly_err}", exc_info=True)


        result["status"] = "완료"
        elapsed = (datetime.now(KST) - start_time).total_seconds()
        logger.info(f"=== 파이프라인 전체 완료 ({elapsed:.1f}초) ===")

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
