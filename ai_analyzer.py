"""
ai_analyzer.py - Gemini API 기반 뉴스 분석 모듈

2단계 AI 파이프라인:
  Stage 1: 제목+설명만으로 중요도 선별 (크롤링 전)
  Stage 2: 선별된 기사의 요약 + 브리핑 대본 동시 생성 (1회 호출)
"""

import json
import logging
import time

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_CRITERIA

logger = logging.getLogger(__name__)

# Gemini API 초기화
genai.configure(api_key=GEMINI_API_KEY)


class AIAnalyzer:
    """Gemini 기반 뉴스 분석기 (2단계 파이프라인)"""

    def __init__(self):
        # 사용자 요청에 따라 2.5 Flash 모델 사용
        self.model = genai.GenerativeModel('gemini-2.5-flash')


    # ═══════════════════════════════════════════════════
    # Stage 1: 중요도 선별 (크롤링 전, 제목+설명만 사용)
    # ═══════════════════════════════════════════════════

    def screen_importance(
        self,
        news_list: list[dict],
        topic_criteria: dict[str, str] | None = None,
        exclusion_keywords: list[str] | None = None
    ) -> tuple[list[dict], list[dict]]:
        """
        AI를 사용하여 각 뉴스의 중요도를 판별하고, 전체 중 주요뉴스 6개 및 각 주제별 5개를 선정.
        """
        if not news_list:
            return [], []

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["중요도"] = "중"
            return news_list, []

        # ── 1단계: 주요뉴스 후보군(헤드라인) 필터링 ──
        headline_candidates = []
        topic_news_pool = []
        
        exclusion_set = set(k.strip().lower() for k in (exclusion_keywords or []) if k.strip())
        
        for news in news_list:
            is_headline = (news.get("주제") == "경제헤드라인")
            
            if is_headline:
                title_desc = (news.get("제목", "") + " " + news.get("네이버 요약", "")).lower()
                found_exclusion = False
                for kw in exclusion_set:
                    if kw in title_desc:
                        found_exclusion = True
                        break
                
                if found_exclusion:
                    logger.info(f"주요뉴스 후보 배제 (키워드 매칭): {news.get('제목')}")
                    news["주제"] = "기타(세부관심사)" 
                    topic_news_pool.append(news)
                else:
                    headline_candidates.append(news)
            else:
                topic_news_pool.append(news)

        final_list_for_ai = headline_candidates + topic_news_pool
        
        criteria_text = ""
        if headline_candidates:
            criteria_text += "\n[경제헤드라인]\n주요 경제지의 메인 뉴스입니다. 거시 경제 핵심 지표나 대형 산업 소식이 포함되어 있습니다.\n"
            
        all_topics = sorted(list(set(n.get("주제", "기타") for n in final_list_for_ai if n.get("주제") != "경제헤드라인")))
        for topic in all_topics:
            criteria = (topic_criteria or {}).get(topic, DEFAULT_CRITERIA)
            criteria_text += f"\n[{topic}]\n{criteria}\n"

        news_texts = []
        headline_indices = []
        for idx, news in enumerate(final_list_for_ai):
            is_h = (news.get("주제") == "경제헤드라인")
            if is_h:
                headline_indices.append(idx + 1)
            
            news_texts.append(
                f"[{idx + 1}] 주제: {news.get('주제', '기타')} | "
                f"제목: {news.get('제목', '')}\n"
                f"    설명: {news.get('네이버 요약', '')}"
            )

        prompt = f"""당신은 베테랑 뉴스 에디터입니다.
아래 뉴스 목록({len(final_list_for_ai)}건)을 보고 3가지 작업을 수행해 주세요.

[작업 1] 모든 뉴스의 중요도를 '상', '중', '하' 중 하나로 판별
- 중요: **주제 적합성(Relevance)**을 최우선으로 고려하십시오.
- **[핵심: 동일/유사 사건 중역 제거]**: 각 주제 내에서 매우 유사한 기사가 여러 개 있다면, 가장 정보량이 많은 1개만 '상'으로 분류하고 나머지는 낮추십시오.

[작업 2] 오늘의 핵심 주요뉴스 **국내 3건 + 해외 3건 = 총 6건** 선정
- **반드시 '주제: 경제헤드라인'으로 표시된 기사들(번호: {headline_indices}) 중에서만 선정하십시오.**
- 수량 엄수: 국내 3건, 해외 3건 총 6건을 선정하고 각각 1~2문장으로 요약하십시오.

[작업 3] 각 일반 주제별로 가장 가치 있는 뉴스 **최대 5건씩** 직접 선정
- 대상 주제: {all_topics}
- 각 주제별로 해당 분야의 목적에 가장 부합하고 독자에게 유익한 기사를 **최대 5개** 골라내십시오.
- 기사가 부족하다면 5개 미만으로 선정해도 됩니다.

주제별 상세 기준:
{criteria_text}

반드시 아래 JSON 형식으로만 응답:
{{
  "importance": [{{"index": 1, "importance": "상"}}, ...],
  "top6": [
    {{"index": ..., "region": "국내", "summary": "..."}},
    ... (총 6개)
  ],
  "topic_tops": {{
    "주제명1": [인덱스1, 인덱스2, ...],
    "주제명2": [...]
  }}
}}

[뉴스 목록]
{chr(10).join(news_texts)}
"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                    )
                )
                text = response.text.strip()
                result = json.loads(text)

                # 1. 중요도 반영
                importance_list = result.get("importance", [])
                for item in importance_list:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(final_list_for_ai):
                        final_list_for_ai[idx]["중요도"] = item.get("importance", "하")

                # 2. 주제별 선정 마킹 (핵심 추가)
                topic_tops = result.get("topic_tops", {})
                for topic, indices in topic_tops.items():
                    logger.info(f"[{topic}] AI가 직접 {len(indices)}건 선정 완료")
                    for idx_val in indices:
                        idx = idx_val - 1
                        if 0 <= idx < len(final_list_for_ai):
                            # AI가 선정한 기사임을 표시하는 플래그
                            final_list_for_ai[idx]["ai_selected"] = True

                # 3. Top6 결과 구성
                top6_list = result.get("top6", [])
                top6_results = []
                for item in top6_list:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(final_list_for_ai):
                        news_item = final_list_for_ai[idx].copy()
                        news_item["summary"] = item.get("summary", "")
                        news_item["region"] = item.get("region", "국내")
                        top6_results.append(news_item)

                return final_list_for_ai, top6_results

            except Exception as e:
                logger.error(f"AI 1차 선별 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    for news in news_list:
                        news["중요도"] = "중"
                else:
                    time.sleep(2)

        return news_list, []


    # ═══════════════════════════════════════════════════
    # Stage 2: 요약 + 브리핑 대본 + 인사이트 리포트 동시 생성
    # ═══════════════════════════════════════════════════

    def analyze_all_in_one(
        self,
        news_list: list[dict],
        context_info: str = ""
    ) -> dict:
        """
        [Stage 2] 통합 분석: 요약, 브리핑 대본, 재단 인사이트 리포트를 한 번에 생성
        """
        if not news_list:
            return {"summaries": [], "briefing_script": "", "insight_report": None}

        news_texts = []
        for idx, news in enumerate(news_list):
            naver_desc = news.get("네이버 요약", "") or news.get("description", "")
            body_preview = (news.get("본문 전문", "") or "")[:1500]
            is_essential = news.get("is_essential", False)
            relevance = "[대본 필수 포함]" if is_essential else "[대본 제외/참고용]"
            
            news_texts.append(
                f"[뉴스 {idx + 1}] {relevance}\n"
                f"주제: {news.get('주제', '기타')}\n"
                f"제목: {news.get('제목', '')}\n"
                f"네이버 요약: {naver_desc}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 베테랑 뉴스 에디터, 인기 아침 라디오 진행자, 그리고 공공기관(서울신용보증재단) 전문 정책 분석가입니다.
제공된 [현재 상황 정보]와 [뉴스 목록]을 참고하여 다음 3가지 작업을 완벽하게 수행해 주세요.

[현재 상황 정보]
{context_info}

[작업 1: 뉴스 요약 (에디터)]
- **모든 개별 기사(총 {len(news_list)}건)**에 대해 각각 2~3문장의 한국어 요약을 작성하십시오. (JSON의 'summaries' 필드)

[작업 2: 라디오 브리핑 대본 (진행자)]
- '[대본 필수 포함]' 표시가 된 뉴스들을 중심으로 친절하고 전문적인 아침 라디오 브리핑 대본을 작성하십시오. (JSON의 'briefing_script' 필드)
- 인트로에 날씨, 요일 등 상황 정보를 자연스럽게 반영하고, 음성 합성(TTS)을 위해 특수 기호 없이 작성하십시오.

[작업 3: 재단 업무 인사이트 리포트 (정책 분석가)]
- **오늘의 주요 경제 흐름**: 전체 뉴스에서 도출되는 핵심 거시 경제 상황을 **500자 이내**로 요약하십시오.
- **재단 업무 인사이트**: 가장 중요한 뉴스 3~5개를 선정하여 제목(1. 제목 형식), 요약, 업무 시사점을 추출하십시오.
- 공공기관 보고서 수준의 정중한 문체를 사용하고 이모지는 금지합니다.

반드시 아래 JSON 형식을 엄수하여 응답하십시오:
{{
  "summaries": [
    {{"index": 1, "summary": "요약 내용..."}},
    ...
  ],
  "briefing_script": "라디오 대본 전문...",
  "insight_report": {{
    "economic_trend": "거시 경제 흐름 요약 내용 (500자 이내)",
    "news_insights": [
      {{
        "title": "1. 뉴스 제목",
        "summary": "핵심 요약",
        "implication": "재단 업무 시사점 및 대응 방안"
      }}
    ]
  }}
}}

[뉴스 목록]
{chr(10).join(news_texts)}
"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                    )
                )
                import json
                result = json.loads(response.text.strip())
                
                # 요약 매칭 및 누락 방지
                summary_map = {item.get('index'): item.get('summary') for item in result.get('summaries', [])}
                for i, news in enumerate(news_list):
                    news['AI 요약'] = summary_map.get(i + 1, "(요약 누락)")
                
                return result
            except Exception as e:
                logger.error(f"통합 분석 시도 {attempt+1} 실패: {e}")
                if attempt == max_retries - 1:
                    return {"summaries": [], "briefing_script": "오류 발생", "insight_report": None}
                time.sleep(2)

    def summarize_and_brief(self, news_list: list[dict], context_info: str = "") -> tuple[list[dict], str]:
        """기존 코드와 호환성을 유지하기 위한 래퍼 메서드"""
        result = self.analyze_all_in_one(news_list, context_info)
        return news_list, result.get("briefing_script", "")

    # ═══════════════════════════════════════════════════
    # (레거시 호환) 기존 메서드 유지
    # ═══════════════════════════════════════════════════

    def analyze_news(self, news_list, topic_criteria=None):
        """레거시 호환 — screen_importance로 래핑 (중요도만 반환)"""
        result, _ = self.screen_importance(news_list, topic_criteria)
        return result

    def generate_briefing_script(self, news_list):
        """레거시 호환 — 사용되지 않음"""
        _, briefing = self.summarize_and_brief(news_list)
        return briefing
