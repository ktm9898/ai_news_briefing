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
        exclusion_keywords: list[str] | None = None,
        topic_max_counts: dict[str, int] | None = None
    ) -> tuple[list[dict], list[dict]]:
        """
        AI를 사용하여 각 뉴스의 중요도를 판별하고, 주요뉴스 및 각 주제별 지정 개수를 선정.
        """
        if not news_list:
            return [], []

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["중요도"] = "중"
            return news_list, []

        topic_max_counts = topic_max_counts or {}
        main_news_count = topic_max_counts.get("주요뉴스") or topic_max_counts.get("경제헤드라인") or 6
        half_main = max(1, main_news_count // 2)
        overseas_main = main_news_count - half_main

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
        topic_count_desc = []
        for topic in all_topics:
            criteria = (topic_criteria or {}).get(topic, DEFAULT_CRITERIA)
            max_c = topic_max_counts.get(topic, 5)
            criteria_text += f"\n[{topic}] (목표 선정 개수: 최대 {max_c}개)\n{criteria}\n"
            topic_count_desc.append(f"'{topic}': 최대 {max_c}개")

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
- **[핵심: 동일/유사 사건 중복 제거]**: 각 주제 내에서 매우 유사한 기사가 여러 개 있다면, 가장 정보량이 많은 1개만 '상'으로 분류하고 나머지는 낮추십시오.

[작업 2] 오늘의 핵심 주요뉴스 **국내 {half_main}건 + 해외 {overseas_main}건 = 총 {main_news_count}건** 선정
- **반드시 '주제: 경제헤드라인'으로 표시된 기사들(번호: {headline_indices}) 중에서만 선정하십시오.**

[작업 3] 각 일반 주제별로 지정된 갯수만큼 뉴스 직접 선정
- 대상 주제별 수량 기준: {', '.join(topic_count_desc)}
- 각 주제별로 목적에 부합하고 독자에게 유익한 기사를 지정된 수량 이하로 골라내십시오.
- 기사가 부족하다면 기준 미만으로 선정해도 됩니다.

주제별 상세 기준:
{criteria_text}

반드시 아래 JSON 형식으로만 응답:
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
{{
  "importance": [{{"index": 1, "importance": "상"}}, ...],
  "main_news": [
    {{"index": ..., "region": "국내", "summary": "..."}},
    ... (총 {main_news_count}개)
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

                # 3. 주요뉴스 결과 구성 (main_news 혹은 top6 하위 호환)
                main_news_list = result.get("main_news") or result.get("top6") or []
                main_news_results = []
                for item in main_news_list:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(final_list_for_ai):
                        news_item = final_list_for_ai[idx].copy()
                        news_item["summary"] = item.get("summary", "")
                        news_item["region"] = item.get("region", "국내")
                        main_news_results.append(news_item)

                return final_list_for_ai, main_news_results

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
            return {"article_summaries": [], "briefing_script": "", "insight_report": None}

        news_texts = []
        for idx, news in enumerate(news_list):
            naver_desc = news.get("네이버 요약", "") or news.get("description", "")
            body_preview = (news.get("본문 전문", "") or "")[:1500]
            is_essential = news.get("is_essential", False)
            relevance = "[대본 필수 포함]" if is_essential else "[대본 제외/참고용]"
            
            news_texts.append(
                f"[뉴스 {idx + 1}] {relevance}\n"
                f"날짜: {news.get('날짜', '')}\n"
                f"언론사: {news.get('언론사', '')}\n"
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
3. 각 인사이트 항목은 'title'(뉴스 제목), 'summary'(주요내용), 'implication'(인사이트), 'references'(외부 출처 배열)로 구성하십시오.
   - **summary 작성 가이드**: 단순 요약을 넘어 기사의 배경, 구체적인 수치, 핵심 쟁점 등을 상세하고 구체적으로 설명하십시오.
   - **implication 작성 가이드**: 단순히 표면적인 대응을 넘어, 해당 뉴스의 이면과 배경을 통찰하십시오. 타 지역 뉴스라면 서울시 환경에 비추어 유추하고, 파급 효과를 구체적으로 짚어주십시오. 관련된 국내외 유사 사례나 성공/실패 레퍼런스를 1~2개 이상 구체적으로 포함하여 통찰을 제공하되, **[할루시네이션(거짓 정보) 엄격 금지]** 반드시 대중적으로 널리 알려지고 교차 검증된 실제 팩트(Fact) 사례만 인용하십시오.
   - **[외부 사례 출처 표기 (필수)]**: 인사이트를 작성할 때 반드시 1~2개의 적절한 외부 유사 사례 등을 인용하십시오. 인용한 외부 레퍼런스의 정확한 명칭을 'references' 배열에 개별 항목으로 기재하십시오. 현재 요약 중인 기사의 출처는 적지 마십시오.

   - 가독성을 극대화하기 위해 내용이 길어질 경우 논리적 흐름에 따라 2~3개의 문단으로 구분하고, 문단 사이에는 반드시 빈 줄(엔터 키 두 번, \n\n)을 삽입하십시오.
4. 모든 내용은 정중하고 전문적인 문체로 작성하며, 이모지는 절대 사용하지 마십시오.

"""
            insight_schema = """\"insight_report\": {{
    \"economic_trend\": \"거시 경제 흐름 요약 내용 (500자 이내)\",
    \"news_insights\": [
      {{
        \"title\": \"기사 제목\",
        \"date\": \"해당 기사가 나온 날짜\",
        \"publisher\": \"해당 기사의 언론사\",
        \"summary\": \"주요내용\",
        \"implication\": \"인사이트 및 깊이 있는 통찰\",
        \"references\": [
          \"첫 번째 외부 사례 출처의 정확한 명칭 (예: 한국은행 '2024 경제전망 보고서')\",
          \"두 번째 외부 사례 출처의 정확한 명칭 (있는 경우)\"
        ]
      }}
    ]
  }}"""

        prompt = f"""당신은 베테랑 뉴스 에디터, 인기 아침 라디오 진행자, 그리고 공공기관(서울신용보증재단) 전문 정책 분석가입니다.
제공된 [현재 상황 정보]와 [뉴스 목록]을 참고하여 다음 작업을 완벽하게 수행해 주세요.

[현재 상황 정보]
{context_info}

[작업 1: 뉴스 요약 (에디터)]
- 각 뉴스의 핵심 내용을 2~3문장으로 한국어 요약 (JSON의 'article_summaries' 필드)
- **[매우 중요]**: 힌트로 제공된 [대본 필수 포함] 여부나 중요도에 절대 관계없이, 아래 [뉴스 목록]에 있는 **모든 개별 기사(총 {len(news_list)}건)에 대해 단 하나도 빠짐없이** 요약을 생성해야 합니다.

[작업 2: 라디오 브리핑 대본 (진행자)]
- **출처 기반**: 오직 제공된 [뉴스 목록]의 내용만을 근거로 대본을 작성하세요.
- **프로그램명 및 오프닝 고정 규칙 [매우 중요]**:
  - 프로그램 명칭은 반드시 **"오늘의 주요 뉴스"**로 고정하고, 어떠한 가상의 라디오 프로그램 이름이나 진행자/아나운서 이름(예: '진행자 OOO입니다')도 언급하지 마십시오.
  - 대본의 도입부 오프닝은 항상 아래와 같은 정갈한 고정 패턴으로 시작하십시오:
    "안녕하십니까. [날짜 및 요일] 오늘의 주요 뉴스 시간입니다. [날씨 정보]. 그럼 오늘 첫 번째 소식부터 전해드리겠습니다."
- **자연스러운 흐름(Thematic Grouping)**: 제공된 모든 뉴스 항목들을 거시경제, 소상공인 지원, 상권 활성화 등 카테고리별로 부드럽게 연결하여 대본을 구성해 주세요. 기사를 단순히 나열하지 말고 뉴스 간의 인과관계나 흐름을 고려하여 자연스럽게 전환하십시오.
- 제공된 모든 뉴스 리스트의 내용을 단 하나도 빠짐없이 대본에 녹여내십시오. (중요도가 낮은 뉴스는 짧게 언급하고 넘어가는 방식으로 조절 가능)
- 방송처럼 신뢰감 있고 친절한 분위기를 유지하세요.

대본 작성 규칙:
- 전체 대본은 6~7분 분량 (약 1800~2500자)으로 넉넉하게 작성하십시오.
- 중요 기사들은 배경과 맥락을 포함해 깊이 있게 설명하고 뉴스 간의 전환을 자연스럽게 처리하세요.
- 마무리 인사로 끝맺음
- 음성 합성(TTS)을 위해 별표(**, *), 샵(#) 등 마크다운 기호는 절대 사용하지 말고 오직 자연스러운 순수 텍스트(평문)로만 작성하세요. (JSON의 'briefing_script' 필드)
{insight_instruction}

반드시 아래 JSON 형식을 엄수하여 응답하십시오:
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
{{
  "article_summaries": [
    {{"index": 1, "article_summary": "요약 내용..."}},
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
                summary_map = {item.get('index'): item.get('article_summary') for item in result.get('article_summaries', [])}
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
            naver_desc = news.get("네이버 요약", "") or news.get("description", "") or news.get("본문 전문", "")[:400]
            body_preview = (news.get("본문 전문", "") or "")[:1500]
            news_texts.append(
                f"[뉴스 {idx + 1}]\n"
                f"날짜: {news.get('날짜', '')}\n"
                f"언론사: {news.get('언론사', '')}\n"
                f"주제: {news.get('주제', '기타')}\n"
                f"제목: {news.get('제목', '')}\n"
                f"요약: {naver_desc}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 공공기관 및 소상공인 비즈니스 컨설팅 최고 전문가입니다.
제공된 지난 일주일간({date_range_str})의 뉴스 목록 전체를 심층 분석하여, 바쁜 서울시 소기업 및 소상공인 사장님들의 실질적 사업 운영과 의사결정에 도움되는 주간 인사이트 리포트를 작성해 주세요.
피상적인 조언이나 단순 기사 나열을 지양하고, 깊이 있는 시장 팩트 분석과 현업에 즉시 적용 가능한 실천 솔루션 및 벤치마킹 사례를 풍부하게 담아내야 합니다.

[작업 지침]
1. [주간 거시 경제 흐름 (economic_trend)]:
   - 한 주간의 거시 경제 지표(금리, 물가, 환율 등), 소비 트렌드 및 골목상권 체감 경기, 주요 정책 동향을 입체적으로 종합 진단하십시오.
   - 단편적인 요약에 그치지 말고, 거시경제 흐름 / 상권 체감 경기 및 소비 트렌드 / 정책 및 대응 방향 등 **2~3개의 논리적 문단(문단 구분: 반드시 \\n\\n)**으로 600~800자 내외의 풍부하고 정돈된 분량으로 작성하십시오.

2. [소기업·소상공인 3대 핵심 사안 선정 및 심층 분석 (news_insights)]:
   - 일주일간의 뉴스 중 소상공인의 생존과 경쟁력에 가장 파급력이 큰 핵심 사안 **3개**를 도출하십시오.
   - **issue_title (이슈 제목)**: 한눈에 사안의 본질을 파악할 수 있는 명확하고 임팩트 있는 1줄 헤드라인으로 작성하십시오. (특정 기사 제목 복제 금지)
   - **summary (주요 팩트 및 배경)**:
     - 단순 1~2줄 요약이 아니라, 관련 보도들의 핵심 팩트, 구체적인 통계 수치, 발생 배경 및 업계 파급 효과를 5~7문장(약 400~500자)으로 깊이 있게 종합 서술하십시오.
   - **implication (인사이트 및 실전 대응 전략)**:
     - 일반론적 훈계나 피상적인 조언(예: '비용을 줄이세요')을 철저히 배제하고, 소상공인이 현장에서 즉시 실천할 수 있는 구체적인 비즈니스 솔루션을 입체적으로 제시하십시오.
     - **[서술 구조 다양화 - 기계적 템플릿 반복 금지]**:
       * '단기적으로는~, 중장기적으로는~' 같은 도식적 구분이나, 3개 이슈 모두의 마지막 문단을 매번 '실제 사례로, ~', '해외 사례로, ~', '벤치마킹 사례로, ~'처럼 판에 박힌 동일한 공식으로 기계적으로 끝맺지 마십시오.
       * 벤치마킹 사례나 실천 팁은 매우 유용한 정보이므로 적극 담아내되, 3개 이슈가 각 사안의 고유한 성격에 맞게 서로 다른 다채로운 전개 방식을 갖도록 자연스럽게 분산·융합하십시오:
         - 금융/원가/부채 사안: 정부·지자체 정책금융/채무조정 신청 요령, 고정비 방어 및 원가 구조 개선 등 **구체적인 실무 대응 절차와 팁** 중심으로 전개
         - 상권/소비트렌드/마케팅 사안: 타깃 고객 공략법, 매장 공간/메뉴 차별화, 로컬 브랜딩 및 온라인 판로 지원 연계 방안에 **검증된 성공 벤치마킹 사례**를 문맥 속에 자연스럽게 녹여냄
         - 제도/노무/디지털 사안: 노무 리스크 예방 체크포인트, 스마트 기술(키오스크, 주문/재고 자동화 등) 도입 가이드 및 지자체 교육/지원사업 연계 방안 제시
       * 세 이슈의 문단 구조와 서술 어조를 다채롭게 구성하여, 기계적으로 생성된 글이 아닌 현장 전문가가 직접 작성한 생생한 비즈니스 컨설팅 리포트의 완성도를 갖추십시오.
     - 가독성을 극대화하기 위해 논리적 흐름에 따라 2~3개의 문단으로 구분하고, 문단 사이에는 반드시 빈 줄(\\n\\n)을 삽입하여 약 600~800자 분량으로 풍부하게 작성하십시오.
   - **references (참고 출처 배열)**:
     - 인사이트 및 벤치마킹 사례에서 인용한 공공기관 보고서, 정책 자료, 연구기관 등의 정확한 명칭을 1~2개 배열 형태로 반드시 기재하십시오. (현재 요약 중인 원본 뉴스 출처는 적지 마십시오.)

3. [문체 및 절대 금지 규칙]:
   - **[내부 뉴스 번호 인용 절대 금지]**:
     * `(뉴스 1)`, `(뉴스 120)`과 같은 프롬프트 내부 뉴스 번호는 본문(`economic_trend`, `summary`, `implication`) 어디에도 절대 기재하지 마십시오.
     * 소상공인 독자는 개별 원본 뉴스 목록을 알지 못하므로, 특정 통계나 사실을 인용할 때는 "한국은행 발표에 따르면", "서울시 통계에 따르면", "최근 언론 보도에 따르면"처럼 독자가 신뢰할 수 있는 기관명이나 주체를 명시하여 자연스럽게 서술하십시오.
   - 모든 내용은 정중하고 전문적인 격식체 경어(예: "~하시기 바랍니다", "~할 필요가 있습니다")로 작성하며, 이모지는 절대 사용하지 마십시오.

반드시 아래 JSON 형식을 엄수하여 응답하십시오:
(주의: JSON 문자열 내부에 큰따옴표(")를 사용할 경우 반드시 백슬래시(\\)로 이스케이프 처리하세요.)
{{
  "economic_trend": "주간 거시 경제 흐름 종합 진단 내용 (600~800자, 문단 간 \\n\\n 포함)",
  "news_insights": [
    {{
      "issue_title": "핵심 사안 제목 (1줄 헤드라인)",
      "summary": "주요 시장 팩트 및 배경 분석 (5~7문장, 약 400~500자)",
      "implication": "소상공인 실전 대응 전략 및 다채로운 벤치마킹/실행 가이드 (2~3개 문단, 약 600~800자, 문단 간 \\n\\n 포함)",
      "references": [
        "첫 번째 외부 사례/보고서 출처의 정확한 명칭 (예: 한국은행 '2024년 자영업 금융안정 보고서')",
        "두 번째 외부 사례/정책 출처의 정확한 명칭 (있는 경우)"
      ]
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

    def enrich_references_with_urls(self, insight_data: dict) -> dict:
        """
        인사이트 리포트의 references 배열을 순회하며 Google Search Grounding을 통해 실제 URL로 보강합니다.
        (할당량 최적화를 위해 모든 출처를 모아서 단 1회의 API만 호출하여 일괄 처리합니다.)
        """
        if not insight_data or "news_insights" not in insight_data:
            return insight_data

        insights = insight_data.get("news_insights", [])
        if not insights:
            return insight_data

        logger.info(f"🔍 참고출처 URL 검색 (Grounding) 시작: 총 {len(insights)}개 기사")
        import re
        import json
        
        # 1. 문서 전체의 고유한 출처(reference) 목록 추출
        all_refs = []
        for item in insights:
            raw_refs = item.get("references", [])
            if not raw_refs and item.get("reference"):
                raw_refs = [r.strip() for r in item.get("reference").split(",") if r.strip()]
            
            for ref_text in raw_refs:
                ref_text = str(ref_text).strip()
                if ref_text and ref_text not in all_refs:
                    all_refs.append(ref_text)
                    
        if not all_refs:
            return insight_data
            
        logger.info(f"  - 검색 대상 고유 출처: 총 {len(all_refs)}개 (단 1회 일괄 호출 진행)")
        
        # 2. 한 번의 호출로 모든 URL 검색 수행
        prompt = f"""다음 목록에 있는 각 출처(보고서, 기사, 발표자료 등)에 해당하는 공식적이고 정확한 원문 URL을 찾아주세요.
목록:
{chr(10).join(f'- {ref}' for ref in all_refs)}

반드시 아래 JSON 형식으로만 응답하세요. 검색되지 않으면 빈 문자열("")을 넣으세요.
{{
  "urls": {{
    "출처명1": "https://...",
    "출처명2": "https://..."
  }}
}}"""
        url_map = {}
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                )
            )
            text = response.text.strip()
            if text.startswith("```json"): text = text[7:]
            elif text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            
            result = json.loads(text.strip())
            url_map = result.get("urls", {})
            logger.info("  - 일괄 URL 검색(Grounding) API 호출 성공")
        except Exception as e:
            logger.error(f"  - 일괄 URL 검색 API 호출 중 오류 (스킵됨): {e}")

        # 3. URL 유효성 검증 (HTTP HEAD 요청으로 실제 접근 가능한지 확인)
        import requests as http_requests
        validated_url_map = {}
        for ref_name, raw_url in url_map.items():
            clean_url = ""
            if raw_url:
                url_match = re.search(r'(https?://[^\s"\'<>]+)', str(raw_url))
                if url_match:
                    clean_url = url_match.group(1).rstrip(')"]')
            
            if clean_url:
                try:
                    resp = http_requests.head(clean_url, timeout=5, allow_redirects=True,
                                              headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code < 400:
                        validated_url_map[ref_name] = clean_url
                        logger.info(f"  ✅ [{ref_name}] -> {clean_url} (HTTP {resp.status_code})")
                    else:
                        # HEAD가 실패하면 GET으로 한 번 더 시도 (일부 서버는 HEAD를 거부)
                        resp2 = http_requests.get(clean_url, timeout=5, allow_redirects=True,
                                                  headers={"User-Agent": "Mozilla/5.0"}, stream=True)
                        resp2.close()
                        if resp2.status_code < 400:
                            validated_url_map[ref_name] = clean_url
                            logger.info(f"  ✅ [{ref_name}] -> {clean_url} (GET 재시도 HTTP {resp2.status_code})")
                        else:
                            logger.warning(f"  ❌ [{ref_name}] -> {clean_url} (HTTP {resp.status_code}/{resp2.status_code}, 링크 제거)")
                except Exception as ve:
                    logger.warning(f"  ❌ [{ref_name}] -> {clean_url} (접속 불가: {ve}, 링크 제거)")
            else:
                logger.warning(f"  - [{ref_name}] -> URL 검색 실패")

        # 4. 검증된 URL을 원본 구조에 매핑하여 반환
        for item in insights:
            raw_refs = item.get("references", [])
            if not raw_refs and item.get("reference"):
                raw_refs = [r.strip() for r in item.get("reference").split(",") if r.strip()]
            
            enriched_refs = []
            for ref_text in raw_refs:
                ref_text = str(ref_text).strip()
                if not ref_text:
                    continue
                
                verified_url = validated_url_map.get(ref_text, "")
                enriched_refs.append({"name": ref_text, "url": verified_url})
                    
            item["references"] = enriched_refs

        return insight_data
