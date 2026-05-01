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
    # Stage 2: 요약 + 브리핑 대본 동시 생성 (1회 AI 호출)
    # ═══════════════════════════════════════════════════

    def summarize_and_brief(self, news_list: list[dict], context_info: str = "") -> tuple[list[dict], str]:
        """
        크롤링 완료된 중요 기사에 대해:
        - 각 기사별 AI 요약 (2~3문장)
        - 오늘의 브리핑 대본 (라디오 스타일)
        을 한 번의 AI 호출로 생성.

        Args:
            news_list: 본문 크롤링이 완료된 중요 기사 목록
            context_info: 현재 날짜, 요일, 날씨 등 상황 정보

        Returns:
            (요약이 채워진 news_list, 브리핑 대본 문자열)
        """
        if not news_list:
            return news_list, "오늘은 주요 뉴스가 없습니다."

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["AI 요약"] = "(GEMINI_API_KEY 미설정)"
            return news_list, "API 키 미설정으로 대본 생성 불가"

        # 뉴스 텍스트 구성
        news_texts = []
        for idx, news in enumerate(news_list):
            is_high = news.get("중요도") == "상"
            body_preview = news.get("본문 전문", "")[:1500]
            naver_desc = news.get("네이버 요약", "")
            
            # 대본 생성을 위해 중요 뉴스만 골라서 힌트 제공
            relevance = "[대본 필수 포함]" if is_high else "[대본 제외/참고용]"
            
            news_texts.append(
                f"[뉴스 {idx + 1}] {relevance}\n"
                f"주제: {news.get('주제', '기타')}\n"
                f"제목: {news.get('제목', '')}\n"
                f"네이버 요약: {naver_desc}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 베테랑 뉴스 에디터이자 인기 아침 라디오 진행자입니다.
아래 제공된 [현재 상황 정보]와 [뉴스 목록]을 참고하여 작업을 수행해 주세요.

[현재 상황 정보]
{context_info}

[작업 1] 각 뉴스의 핵심 내용을 2~3문장으로 한국어 요약
- **[매우 중요]**: 힌트로 제공된 [대본 필수 포함] 여부나 중요도에 절대 관계없이, 아래 [뉴스 목록]에 있는 **모든 개별 기사(총 {len(news_list)}건)에 대해 단 하나도 빠짐없이** 요약을 생성해야 합니다.

[작업 2] 아침 브리핑 대본 작성
- **출처 기반**: 오직 제공된 [뉴스 목록]의 내용만을 근거로 대본을 작성하세요.
- **자연스러운 흐름(Thematic Grouping)**: 기사를 단순히 순서대로 나열하지 말고, 거시경제, 산업/기술, 민생/금융 등 관련 있는 뉴스끼리 묶어서 부드럽게 연결하세요. (예: "다음은 산업 소식입니다...", "한편, 민생 경제를 보면...")
- [현재 상황 정보](날짜, 요일, 날씨 등)를 대본 도입부인 인사말에만 자연스럽게 반영하여 생동감을 주십시오. 인사말이 끝난 뒤에는 오직 [뉴스 목록]의 내용에만 집중하세요.
- 매번 똑같은 인사 대신 오늘의 요일이나 날씨에 어울리는 적절한 인사를 사용하세요.
- 반드시 '[대본 필수 포함]' 표시가 된 핵심 뉴스들로만 대본을 구성해 주세요. '[대본 제외/참고용]' 표기가 된 뉴스들은 대본에서 과감히 제외해 주세요.
- 아나운서가 읽을 전문을 작성하되, 방송처럼 신뢰감 있고 친절한 분위기를 유지하세요.

대본 작성 규칙:
- 진행자 본인을 특정 이름으로 지칭하지 마십시오.
- 중요 기사들은 배경과 맥락을 포함해 깊이 있게 설명하고 뉴스 간의 전환을 자연스럽게 처리하세요.
- 마지막은 활기찬 인사로 마무리하세요.
- 음성 합성(TTS)을 위해 별표(**, *), 샵(#) 등 마크다운 기호는 절대 사용하지 말고 오직 자연스러운 순수 텍스트(평문)로만 작성하세요.

반드시 아래 JSON 형식으로만 응답:
{{
  "summaries": [
    {{"index": 1, "summary": "요약..."}},
    ...
  ],
  "briefing_script": "대본 전문..."
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

                # JSON 파싱 (중괄호 추출)
                start_idx = text.find('{')
                end_idx = text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    text = text[start_idx:end_idx + 1]

                result = json.loads(text)

                # 요약 채우기
                summaries = result.get("summaries", [])
                for item in summaries:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(news_list):
                        # 빈 문자열 처리 강화: 요약이 없으면 폴백 메시지 삽입
                        summary_text = item.get("summary", "").strip()
                        news_list[idx]["AI 요약"] = summary_text if summary_text else "(AI 요약 생성 누락: 제공된 본문을 기반으로 요약을 추출하지 못했습니다.)"

                briefing = result.get("briefing_script", "대본 생성 실패")
                
                # 마크다운 특수기호 제거 (TTS에서 '별표' 등을 소리내어 읽는 문제 방지)
                briefing = briefing.replace("**", "").replace("*", "").replace("#", "")

                # 누락 검증 (AI가 리스트의 일부만 응답했을 경우 대비)
                for news in news_list:
                    if not news.get("AI 요약"):
                        news["AI 요약"] = "(AI 요약 생성 누락: AI가 해당 기사의 요약 응답을 누락했습니다.)"

                logger.info(
                    f"AI 2차 완료: {len(summaries)}건 요약, "
                    f"대본 {len(briefing)}자"
                )
                return news_list, briefing

            except Exception as e:
                logger.error(f"AI 2차 처리 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)

        # 모든 재시도 실패
        for news in news_list:
            if not news.get("AI 요약"):
                news["AI 요약"] = "(AI 요약 생성 실패)"
        return news_list, "브리핑 대본 생성에 실패했습니다."

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
    # ═══════════════════════════════════════════════════
    # Stage 3: 서울신용보증재단 인사이트 리포트 생성
    # ═══════════════════════════════════════════════════

    def generate_insight_report(self, news_list: list[dict], date_str: str = "") -> str:
        """
        서울신용보증재단 업무와 연계된 인사이트 리포트를 생성합니다.
        - 주요 뉴스 중 3~5개를 선별하여 인사이트 도출
        - 이모지 배제, 전문적인 어조 사용
        """
        if not news_list:
            return "분석할 뉴스가 없습니다."

        news_texts = []
        for idx, news in enumerate(news_list):
            news_texts.append(
                f"[{idx + 1}] 주제: {news.get('주제')}, 제목: {news.get('제목')}\n"
                f"요약: {news.get('AI 요약')}\n"
                f"본문일부: {news.get('본문 전문', '')[:500]}\n"
            )

        prompt = f"""당신은 공공기관(서울신용보증재단)의 정책 분석가이자 전략 컨설턴트입니다.
오늘의 주요 뉴스들을 분석하여 서울신용보증재단의 업무(소상공인 지원, 보증, 컨설팅, 지역경제 활성화 등)에 실질적으로 적용하거나 참고해야 할 인사이트 리포트를 작성해 주세요.

[분석 대상 뉴스 목록]
{chr(10).join(news_texts)}

[작성 가이드라인]
1. **전문성 유지**: 가볍거나 감성적인 어조가 아닌, 공공기관 보고서 형식의 격식 있고 전문적인 문체를 사용하십시오.
2. **이모지/이모티콘 금지**: 텍스트 리포트의 신뢰도를 위해 이모지나 이모티콘을 절대 사용하지 마십시오.
3. **핵심 인사이트 선별**: 위 뉴스 중 재단 업무와 연관성이 높고 중요한 뉴스를 3~5개 선별하여 인사이트를 도출하십시오.
4. **구조적 작성**: 
   - [오늘의 주요 경제 흐름] (전체적인 거시 상황 요약)
   - [재단 업무 연계 및 시사점] (선별된 뉴스별 구체적인 재단 업무 연계 방안 제시)
   - [향후 대응 방향] (재단이 준비하거나 주의 깊게 살펴야 할 점)

[주의사항]
- 뉴스 내용을 단순히 나열하지 말고, '재단 업무와 어떻게 연결되는지'에 집중하여 분석하십시오.
- 마크다운 서식(#, ##, ###, -, ** 등)을 사용하여 구조화하되, 특수 기호는 최소화하십시오.

응답은 반드시 한국어로 작성하십시오.
"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"인사이트 리포트 생성 실패: {e}")
            return "인사이트 리포트 생성 중 오류가 발생했습니다."
