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
        AI를 사용하여 각 뉴스의 중요도를 판별하고, 전체 중 주요뉴스 6개를 선정.
        
        Args:
            news_list: 뉴스 목록
            topic_criteria: 주제별 중요도 판단 기준 (Sheets에서 로드)
            exclusion_keywords: 주요뉴스(Top6) 선정 시 배제할 키워드 목록
            
        Returns:
            (중요도가 채워진 전체 뉴스 목록, 선정된 Top6 뉴스 목록)
        """
        if not news_list:
            return [], []

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["중요도"] = "중"
            return news_list, []

        # ── 1단계: 주요뉴스 후보군(헤드라인) 필터링 ──
        # 사용자가 설정한 세부 주제 키워드가 포함된 경우 주요뉴스 후보에서 즉시 탈락시킴
        headline_candidates = []
        topic_news_pool = []
        
        exclusion_set = set(k.strip().lower() for k in (exclusion_keywords or []) if k.strip())
        
        for news in news_list:
            is_headline = (news.get("주제") == "경제헤드라인")
            
            if is_headline:
                title_desc = (news.get("제목", "") + " " + news.get("네이버 요약", "")).lower()
                # 배제 키워드 포함여부 체크
                found_exclusion = False
                for kw in exclusion_set:
                    if kw in title_desc:
                        found_exclusion = True
                        break
                
                if found_exclusion:
                    # 헤드라인으로 수집되었으나 지엽적 키워드가 포함된 경우 일반 뉴스로 격하
                    logger.info(f"주요뉴스 후보 배제 (키워드 매칭): {news.get('제목')}")
                    news["주제"] = "기타(세부관심사)" 
                    topic_news_pool.append(news)
                else:
                    headline_candidates.append(news)
            else:
                topic_news_pool.append(news)

        # AI에게 전달할 전체 리스트 (인덱스 유지를 위해 다시 합침)
        final_list_for_ai = headline_candidates + topic_news_pool
        
        # 주제별 기준 텍스트 생성
        criteria_text = ""
        # '경제헤드라인' 주제는 특별 취급 (가장 높은 우선순위)
        if headline_candidates: # 필터링 후에도 헤드라인이 남아있다면
            criteria_text += "\n[경제헤드라인]\n주요 경제지의 메인 뉴스입니다. 거시 경제 핵심 지표나 대형 산업 소식이 포함되어 있습니다. 매우 엄격한 기준으로 중요도를 판별하세요.\n"
            
        all_topics = set(n.get("주제", "기타") for n in final_list_for_ai if n.get("주제") != "경제헤드라인")
        for topic in sorted(all_topics):
            criteria = (topic_criteria or {}).get(topic, DEFAULT_CRITERIA)
            criteria_text += f"\n[{topic}]\n{criteria}\n"

        # 전체 뉴스 목록 텍스트 생성 (AI 프롬프트용)
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
아래 뉴스 목록({len(final_list_for_ai)}건)을 보고 2가지 작업을 수행해 주세요.

[작업 1] 모든 뉴스의 중요도를 '상', '중', '하' 중 하나로 판별
- 중요: **주제 적합성(Relevance)**을 최우선으로 고려하십시오.
- [{all_topics}]와 같이 구체적인 주제가 지정된 뉴스는 해당 주제의 목적(로컬 상권, 소상공인 정책 등)에 충실한 뉴스만 '상'으로 분류합니다.
- 아무리 전 세계적인 대사건(트럼프, 전쟁 등)이라도 해당 주제 섹션에 포함되어 있다면, 그 주제 고유의 관점(예: 상권 영향 분석 등)이 중심이 아닌 '단순 국제 정세' 뉴스는 '중' 또는 '하'로 과감히 낮춰야 합니다.
- '경제헤드라인' 주제는 거시 경제적 관점에서 중요도를 평가합니다.

주제별 상세 기준:
{criteria_text}

[작업 2] 오늘의 핵심 주요뉴스 **국내 3건 + 해외 3건 = 총 6건** 선정
- **중요: 선정 대상 제한**: 반드시 '주제: 경제헤드라인'으로 표시된 기사들(번호: {headline_indices}) 중에서만 선정하십시오.
- **국내 뉴스 (3건 필수)**: 대한민국 거시경제, 정부 정책, 코스피/환율, 대기업 중대 발표 등 국가 단위 파급력이 있는 뉴스.
- **해외 뉴스 (3건 필수)**: 글로벌 금융(Fed 등), 해외 빅테크(Nvidia, Apple 등), 국제 정세, 미증시 등 세계 경제 지형 관련 뉴스. 
- **절대 불가**: '상권활성화', '소상공인' 등 특정 세부 주제용으로 수집된 기사는 주요뉴스(Top6)가 될 수 없습니다. 오직 매크로(Macro) 관점의 '경제헤드라인' 기사만 선정하세요.
- **수량 엄수**: 해당 영역(국내/해외)에 가장 적합한 기사를 골라 **반드시 각각 3건씩** 채우십시오. (총 6건)
- 각 주요뉴스에 대해 핵심 내용을 1~2문장으로 품격 있게 요약하십시오.

반드시 아래 JSON 형식으로만 응답:
{{
  "importance": [{{"index": 1, "importance": "상"}}, ...],
  "top6": [
    {{"index": ..., "region": "국내", "summary": "..."}},
    ... (국내 3개, 해외 3개 총 6개)
  ]
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

                # JSON 파싱
                start_idx = text.find('{')
                end_idx = text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    text = text[start_idx:end_idx + 1]

                result = json.loads(text)

                # 중요도 채우기
                importance_list = result.get("importance", [])
                for item in importance_list:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(final_list_for_ai):
                        final_list_for_ai[idx]["중요도"] = item.get("importance", "하")

                # Top6 결과 (국내 3 + 해외 3)
                top6_list = result.get("top6", [])
                top6_results = []
                for item in top6_list:
                    idx = item.get("index", 1) - 1
                    if 0 <= idx < len(final_list_for_ai):
                        news_item = final_list_for_ai[idx].copy()
                        news_item["summary"] = item.get("summary", "")
                        news_item["region"] = item.get("region", "국내")
                        top6_results.append(news_item)

                # 중요도 통계 로깅
                imp_counts = {"상": 0, "중": 0, "하": 0}
                for n in final_list_for_ai:
                    imp = n.get("중요도", "중")
                    imp_counts[imp] = imp_counts.get(imp, 0) + 1

                domestic = len([t for t in top6_results if t.get('region') == '국내'])
                foreign = len([t for t in top6_results if t.get('region') == '해외'])
                logger.info(
                    f"AI 1차 완료: 상={imp_counts['상']}건, "
                    f"중={imp_counts['중']}건, 하={imp_counts['하']}건, "
                    f"주요뉴스={len(top6_results)}건 (국내 {domestic} + 해외 {foreign})"
                )
                return final_list_for_ai, top6_results

            except Exception as e:
                logger.error(f"AI 1차 선별 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    for news in news_list:
                        news["중요도"] = "중"  # 실패 시 기본값
                else:
                    time.sleep(2)

        return news_list, top6_results

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

[작업 1] 각 뉴스의 핵심 내용을 2~3문장으로 한국어 요약 (모든 뉴스 대상)
[작업 2] 아침 브리핑 대본 작성
- 반드시 '[대본 필수 포함]' 표시가 된 핵심 뉴스들로만 대본을 구성해 주세요.
- [현재 상황 정보](날짜, 요일, 날씨 등)를 대본 도입부에 자연스럽게 녹여내어 실제 생방송 같은 생동감을 주십시오.
- 매번 똑같은 인사(예: "활기찬 한 주 시작하셨나요?")를 반복하지 말고, 오늘의 요일이나 날씨에 어울리는 적절한 인사를 건네주세요. (예: 월요일이면 한 주의 시작을, 토요일이면 주말의 여유를 언급)
- 국내와 해외 소식을 자연스럽게 엮어 전체적인 경제 흐름을 조망할 수 있게 작성해 주세요.
- '[대본 제외/참고용]' 표기가 된 뉴스들은 대본에서 과감히 제외해 주세요.
- 방송처럼 자연스럽고 친절한 분위기로 작성해 주세요.

대본 작성 규칙:
- 진행자 본인을 특정 이름(예: 김민준 등)으로 지칭하지 마십시오.
- 중요 기사들은 배경과 맥락을 포함해 깊이 있게 설명
- 뉴스 간의 연결고리를 찾아 자연스럽게 전환
- 마지막은 활기찬 인사로 마무리
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
                        news_list[idx]["AI 요약"] = item.get("summary", "")

                briefing = result.get("briefing_script", "대본 생성 실패")
                
                # 마크다운 특수기호 제거 (TTS에서 '별표' 등을 소리내어 읽는 문제 방지)
                briefing = briefing.replace("**", "").replace("*", "").replace("#", "")

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
