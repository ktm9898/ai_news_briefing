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
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
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
                # 간혹 모델이 마크다운 코드 블록을 포함할 경우 제거
                if text.startswith("```json"): text = text[7:]
                elif text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                text = text.strip()
                
                try:
                    result = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 에러 (Stage 1). 일부 텍스트: {text[:200]} ... {text[-200:]}")
                    raise e

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
        context_info: str = "",
        generate_insight: bool = True
    ) -> dict:
        """
        [Stage 2] 통합 분석: 요약, 브리핑 대본, 재단 인사이트 리포트를 선택적으로 생성
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

        insight_instruction = ""
        insight_schema = '"insight_report": null'
        
        if generate_insight:
            insight_instruction = """
[작업 3: 재단 업무 인사이트 리포트 (정책 분석가)]
당신은 공공기관(서울신용보증재단)의 전문 정책 분석가입니다.
오늘의 주요 뉴스들을 분석하여 재단 업무(소상공인 지원, 보증, 컨설팅 등)에 깊이 있는 통찰을 제공할 핵심 데이터를 추출해 주세요.

[작업 지침]
1. 뉴스 전체를 관통하는 핵심적인 거시 경제 상황을 'economic_trend'에 500자 이내로 요약하십시오.
2. 재단 업무와 직간접적으로 연계성이 가장 높고 시사하는 바가 큰 뉴스 **2~3개**를 신중하게 선정하여 'news_insights' 리스트에 담으십시오. 너무 많이 선정하지 말고 깊이 있는 분석에 집중하십시오.
3. 각 인사이트 항목은 'title'(뉴스 제목, 원문 그대로 생략 없이 전체 작성), 'summary'(주요내용), 'implication'(시사점)으로 구성하십시오.
   - **implication 작성 가이드**: 단순히 표면적인 대응("지원해야 함", "모니터링해야 함")을 넘어, 해당 뉴스의 이면과 배경을 통찰하십시오. 타 지역 뉴스라면 서울시 환경에 비추어 유추하고, 국내외 거시 뉴스라면 국내 소상공인 생태계나 재단 정책에 미칠 파급 효과를 구체적으로 짚어주십시오. 억지로 연결할 필요는 없으나, 정책적으로 참고할 만한 밀도 높은 통찰을 제공해야 합니다. 특히, 실질적인 도움이 될 수 있도록 관련된 국내외 유사 사례나 성공/실패 레퍼런스를 1~2개 이상 구체적으로 포함하여 통찰을 제공하되, **[할루시네이션(거짓 정보) 엄격 금지]** 반드시 대중적으로 널리 알려지고 교차 검증된 실제 팩트(Fact) 사례만 인용하십시오. 만약 완전히 확신할 수 있는 실제 사례가 없다면, 억지로 꾸며내지 말고 논리적으로 예상되는 가상의 시나리오(예: "만약 이 제도가 도입된다면~") 형태로 명확히 구분하여 서술하십시오.
4. 모든 내용은 정중하고 전문적인 문체로 작성하며, 이모지는 절대 사용하지 마십시오.
"""
            insight_schema = """\"insight_report\": {{
    \"economic_trend\": \"거시 경제 흐름 요약 내용 (500자 이내)\",
    \"news_insights\": [
      {{
        \"title\": \"기사 제목\",
        \"summary\": \"주요내용\",
        \"implication\": \"시사점 및 깊이 있는 통찰\"
      }}
    ]
  }}"""

        prompt = f"""당신은 베테랑 뉴스 에디터, 인기 아침 라디오 진행자, 그리고 공공기관(서울신용보증재단) 전문 정책 분석가입니다.
제공된 [현재 상황 정보]와 [뉴스 목록]을 참고하여 다음 작업을 완벽하게 수행해 주세요.

[현재 상황 정보]
{context_info}

[작업 1: 뉴스 요약 (에디터)]
- 각 뉴스의 핵심 내용을 2~3문장으로 한국어 요약 (JSON의 'summaries' 필드)
- **[매우 중요]**: 힌트로 제공된 [대본 필수 포함] 여부나 중요도에 절대 관계없이, 아래 [뉴스 목록]에 있는 **모든 개별 기사(총 {len(news_list)}건)에 대해 단 하나도 빠짐없이** 요약을 생성해야 합니다.

[작업 2: 라디오 브리핑 대본 (진행자)]
- **출처 기반**: 오직 제공된 [뉴스 목록]의 내용만을 근거로 대본을 작성하세요.
- **자연스러운 흐름(Thematic Grouping)**: 제공된 모든 뉴스 항목들을 거시경제, 소상공인 지원, 상권 활성화 등 카테고리별로 부드럽게 연결하여 대본을 구성해 주세요. 기사를 단순히 나열하지 말고 뉴스 간의 인과관계나 흐름을 고려하여 자연스럽게 전환하십시오.
- 제공된 모든 뉴스 리스트의 내용을 단 하나도 빠짐없이 대본에 녹여내십시오. (중요도가 낮은 뉴스는 짧게 언급하고 넘어가는 방식으로 조절 가능)
- [현재 상황 정보](날짜, 요일, 날씨 등)를 도입부에 자연스럽게 반영하여 생동감을 주십시오.
- 아나운서가 읽을 전문을 작성하되, 방송처럼 신뢰감 있고 친절한 분위기를 유지하세요.

대본 작성 규칙:
- 전체 대본은 6~7분 분량 (약 1800~2500자)으로 넉넉하게 작성하십시오.
- 중요 기사들은 배경과 맥락을 포함해 깊이 있게 설명하고 뉴스 간의 전환을 자연스럽게 처리하세요.
- 마무리 인사로 끝맺음
- 음성 합성(TTS)을 위해 별표(**, *), 샵(#) 등 마크다운 기호는 절대 사용하지 말고 오직 자연스러운 순수 텍스트(평문)로만 작성하세요. (JSON의 'briefing_script' 필드)
{insight_instruction}

반드시 아래 JSON 형식을 엄수하여 응답하십시오:
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
{{
  "summaries": [
    {{"index": 1, "summary": "요약 내용..."}},
    ...
  ],
  "briefing_script": "라디오 대본 전문...",
  {insight_schema}
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
                
                text = response.text.strip()
                # 간혹 모델이 마크다운 코드 블록을 포함할 경우 제거
                if text.startswith("```json"): text = text[7:]
                elif text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                text = text.strip()
                
                try:
                    result = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 에러 (Stage 2). 일부 텍스트: {text[:200]} ... {text[-200:]}")
                    raise e
                
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
