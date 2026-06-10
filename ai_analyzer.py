"""
ai_analyzer.py - Gemini API 기반 뉴스 분석 모듈

2단계 AI 파이프라인:
  Stage 1: 제목+설명만으로 중요도 선별 (크롤링 전)
  Stage 2: 선별된 기사의 요약 + 브리핑 대본 동시 생성 (1회 호출)
"""

import json
import logging
import time
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_CRITERIA

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Gemini 기반 뉴스 분석기 (2단계 파이프라인)"""

    def __init__(self):
        # google-genai Client 초기화 (API key가 빈 값이면 환경변수에서 자동 참조)
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
        else:
            self.client = genai.Client()

    @staticmethod
    def _extract_retry_delay(error) -> float:
        """429 에러에서 API가 권장하는 retry_delay(초)를 추출. 없으면 30초 반환."""
        import re
        error_str = str(error)
        # "Please retry in 14.126154886s" 패턴에서 초 추출
        match = re.search(r'retry in ([\d.]+)s', error_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 2  # 여유 2초 추가
        # retry_delay { seconds: 14 } 패턴
        match = re.search(r'retry_delay.*?seconds:\s*([\d.]+)', error_str, re.DOTALL)
        if match:
            return float(match.group(1)) + 2
        return 30.0  # 기본 대기 시간

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
                    logger.info(f"주요뉴스 후보 배제 (키워드 매칭) 및 완전히 제외: {news.get('제목')}")
                    # 이 기사는 주요뉴스 후보에서 배제되고, 일반 주제에도 속하지 않으므로 완전히 제외합니다.
                    continue
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

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
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
                    raise e
                else:
                    if '429' in str(e):
                        wait_sec = self._extract_retry_delay(e)
                    else:
                        wait_sec = 10 * (attempt + 1)
                    logger.info(f"⏳ {wait_sec:.1f}초 대기 후 재시도...")
                    time.sleep(wait_sec)

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
오늘의 주요 뉴스들을 분석하여 재단 업무(소상공인 지원, 보증, 컨설팅, 상권활성화 등)에 깊이 있는 통찰을 제공할 핵심 데이터를 추출해 주세요.

[작업 지침]
1. 뉴스 전체를 관통하는 핵심적인 거시 경제 상황을 'economic_trend'에 500자 이내로 요약하십시오.
2. 재단 업무와 직간접적으로 연계성이 가장 높고 시사하는 바가 큰 뉴스 **2~3개**를 신중하게 선정하여 'news_insights' 리스트에 담으십시오. 너무 많이 선정하지 말고 깊이 있는 분석에 집중하십시오.
3. 각 인사이트 항목은 'title'(뉴스 제목, 원문 그대로 생략 없이 전체 작성), 'summary'(주요내용), 'implication'(시사점)으로 구성하십시오.
   - **summary(주요내용) 작성 가이드**: 단순 요약을 넘어 기사의 배경, 구체적인 수치, 핵심 쟁점 등을 기존보다 1~2줄 더 상세하고 구체적으로 설명하십시오.
   - **implication(시사점) 작성 가이드**: 표면적인 대응을 넘어 뉴스의 이면을 통찰하고 재단 정책이나 소상공인 생태계에 미칠 파급 효과를 구체적으로 짚어주십시오. 통찰의 깊이를 더하기 위해 관련된 국내외 유사 사례나 성공/실패 레퍼런스를 구체적으로 포함하십시오.
   - **[사례 출처 표기]**: 사례를 언급할 때는 신뢰할 수 있는 출처(주요 언론사, 공공기관 등)의 실제 팩트만 인용하십시오(할루시네이션 절대 금지). 또한 사례 끝에는 반드시 [참고 출처: OO일보 "기사 제목" 등] 형태로 출처를 명시하십시오(존재하지 않는 가짜 웹 링크(URL)는 작성하지 마시고 출처명과 제목/키워드로 표기). 확실한 사례가 없다면 가상의 시나리오임을 명확히 서술하십시오.
   - 가독성을 극대화하기 위해 내용이 길어질 경우 논리적 흐름에 따라 2~3개의 문단으로 구분하고, 문단 사이에는 반드시 빈 줄(\n\n)을 삽입하십시오.
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

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
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
                    logger.warning(f"JSON 파싱 1차 에러 (복구 시도 중): {e}")
                    import re
                    
                    # 1. 제어 문자 이스케이프 복구
                    text_repaired = re.sub(r'[\x00-\x1f]', lambda m: '\\u{:04x}'.format(ord(m.group(0))), text)
                    
                    try:
                        # 2. raw_decode: JSON 뒤에 붙은 Extra data를 무시하고 첫 번째 유효한 JSON만 파싱
                        result, _ = json.JSONDecoder().raw_decode(text_repaired)
                        logger.info("JSON 복구 파싱 성공! (raw_decode)")
                    except json.JSONDecodeError as e2:
                        logger.error(f"JSON 파싱 2차 복구 에러. 원본 에러: {e}. 일부 텍스트: {text_repaired[:200]} ... {text_repaired[-200:]}")
                        raise e2
                
                # 요약 매칭 및 누락 방지
                summary_map = {item.get('index'): item.get('summary') for item in result.get('summaries', [])}
                for i, news in enumerate(news_list):
                    news['AI 요약'] = summary_map.get(i + 1, "(요약 누락)")
                
                return result
            except Exception as e:
                logger.error(f"통합 분석 시도 {attempt+1} 실패: {e}")
                if attempt == max_retries - 1:
                    raise e
                else:
                    if '429' in str(e):
                        wait_sec = self._extract_retry_delay(e)
                    else:
                        wait_sec = 10 * (attempt + 1)
                    logger.info(f"⏳ {wait_sec:.1f}초 대기 후 재시도...")
                    time.sleep(wait_sec)

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

    def analyze_weekly_insight(self, news_list: list[dict], date_range_str: str) -> dict:
        """
        주간 소상공인 인사이트 리포트 생성
        """
        if not news_list:
            return {"economic_trend": "수집된 뉴스가 없습니다.", "news_insights": []}

        news_texts = []
        for idx, news in enumerate(news_list):
            naver_desc = news.get("네이버 요약", "") or news.get("description", "") or news.get("본문 전문", "")[:300]
            body_preview = (news.get("본문 전문", "") or "")[:1000]
            news_texts.append(
                f"[뉴스 {idx + 1}]\n"
                f"날짜: {news.get('날짜', '')}\n"
                f"주제: {news.get('주제', '기타')}\n"
                f"제목: {news.get('제목', '')}\n"
                f"요약: {naver_desc}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 공공기관 및 소상공인 비즈니스 컨설팅 전문가입니다.
제공된 지난 일주일간({date_range_str})의 뉴스 목록을 바탕으로, 바쁜 서울시 소기업 및 소상공인 사장님들을 위한 주간 인사이트 리포트를 작성해 주세요.
리포트는 소상공인 사장님들이 세상 돌아가는 경제 흐름을 파악하고, 실제 사업운영에 유용한 인사이트를 얻을 수 있도록 돕는 목적입니다.

[작업 지침]
1. 일주일간의 주요 경제 상황과 흐름을 'economic_trend'에 500자 이내로 핵심만 요약하십시오.
2. 수집된 뉴스 중 서울시 소기업, 소상공인의 사업운영에 가장 큰 영향이나 실질적인 팁, 아이디어를 제공할 수 있는 중요 뉴스 **3개**를 신중하게 선정하여 'news_insights' 리스트에 담으십시오.
3. 각 인사이트 항목은 'title'(뉴스 제목, 원문 그대로 생략 없이 전체 작성), 'summary'(주요내용 요약), 'implication'(사업운영 인사이트)으로 구성하십시오.
   - **implication(사업운영 인사이트) 작성 가이드**: 단순히 기사를 해설하는 것을 넘어, 소상공인 사장님이 실질적으로 어떻게 대비하거나 활용해야 하는지 구체적인 비즈니스 팁, 대응 방안, 아이디어를 제공해야 합니다.
   - 가독성을 극대화하기 위해 내용이 길어질 경우 논리적 흐름에 따라 2~3개의 문단으로 구분하고, 문단 사이에는 반드시 빈 줄(\\n\\n)을 삽입하십시오.
4. 모든 내용은 친절하고 전문적인 구어체 혹은 격식체 경어(예: "~시기 바랍니다", "~할 필요가 있습니다")로 작성하며, 이모지는 절대 사용하지 마십시오.

반드시 아래 JSON 형식을 엄수하여 응답하십시오:
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
{{
  "economic_trend": "주간 거시 경제 흐름 요약 내용 (500자 이내)",
  "news_insights": [
    {{
      "title": "기사 제목",
      "summary": "주요내용 요약",
      "implication": "사업운영을 위한 구체적인 시사점 및 대응 방향"
    }},
    ... (총 3개)
  ]
}}

[일주일간의 뉴스 목록]
{"".join(news_texts)}
"""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                )
                text = response.text.strip()
                if text.startswith("```json"): text = text[7:]
                elif text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                text = text.strip()
                
                try:
                    result = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.warning(f"주간 JSON 파싱 1차 에러 (복구 시도 중): {e}")
                    import re
                    text_repaired = re.sub(r'[\x00-\x1f]', lambda m: '\\u{:04x}'.format(ord(m.group(0))), text)
                    try:
                        # raw_decode: JSON 뒤에 붙은 Extra data를 무시하고 첫 번째 유효한 JSON만 파싱
                        result, _ = json.JSONDecoder().raw_decode(text_repaired)
                        logger.info("주간 JSON 복구 파싱 성공! (raw_decode)")
                    except json.JSONDecodeError as e2:
                        logger.error(f"주간 JSON 2차 복구 에러. 원본: {e}. 텍스트: {text_repaired[:200]}")
                        raise e2
                
                return result
            except Exception as e:
                logger.error(f"주간 인사이트 분석 시도 {attempt+1} 실패: {e}")
                if attempt == max_retries - 1:
                    raise e
                else:
                    if '429' in str(e):
                        wait_sec = self._extract_retry_delay(e)
                    else:
                        wait_sec = 10 * (attempt + 1)
                    logger.info(f"⏳ {wait_sec:.1f}초 대기 후 재시도...")
                    time.sleep(wait_sec)
