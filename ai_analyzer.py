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
        topic_criteria: dict[str, str] = None,
    ) -> list[dict]:
        """
        제목과 네이버 요약만으로 중요도를 판별.
        크롤링 전에 불필요한 기사를 걸러내기 위한 1차 필터링.

        Args:
            news_list: [{"제목": ..., "네이버 요약": ..., "주제": ..., ...}]
            topic_criteria: {"주제명": "판단 기준..."}

        Returns:
            중요도가 채워진 news_list
        """
        if not news_list:
            return news_list

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["중요도"] = "중"
            return news_list

        # 주제별 그룹화
        topic_groups = {}
        for news in news_list:
            t = news.get("주제", "기타")
            topic_groups.setdefault(t, []).append(news)

        logger.info(f"AI 1차 선별 시작: {len(news_list)}건, {len(topic_groups)}개 주제")

        for topic, group in topic_groups.items():
            criteria = (topic_criteria or {}).get(topic, DEFAULT_CRITERIA)

            news_texts = []
            for idx, news in enumerate(group):
                news_texts.append(
                    f"[{idx + 1}] 제목: {news.get('제목', '')}\n"
                    f"    설명: {news.get('네이버 요약', '')}"
                )

            prompt = f"""당신은 베테랑 뉴스 에디터입니다.
아래 '{topic}' 주제의 뉴스 목록에서 제목과 설명만 보고 중요도를 판별해 주세요.

[중요도 판단 기준 - {topic}]
{criteria}

[규칙]
1. 각 뉴스의 중요도를 '상', '중', '하' 중 하나로 판별
2. 결과는 반드시 JSON 배열로만 응답:
[{{"index": 1, "importance": "상"}}, ...]

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
                    start_idx = text.find('[')
                    end_idx = text.rfind(']')
                    if start_idx != -1 and end_idx != -1:
                        text = text[start_idx:end_idx + 1]

                    results = json.loads(text)

                    for item in results:
                        idx = item.get("index", 1) - 1
                        if 0 <= idx < len(group):
                            group[idx]["중요도"] = item.get("importance", "중")

                    logger.info(
                        f"[{topic}] 1차 선별 완료: "
                        f"상={sum(1 for n in group if n.get('중요도') == '상')}건, "
                        f"중={sum(1 for n in group if n.get('중요도') == '중')}건, "
                        f"하={sum(1 for n in group if n.get('중요도') == '하')}건"
                    )
                    break

                except Exception as e:
                    logger.error(f"AI 1차 선별 실패 ({topic}, 시도 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        for news in group:
                            news["중요도"] = "중"  # 실패 시 기본값
                    else:
                        time.sleep(2)

        return news_list

    # ═══════════════════════════════════════════════════
    # Stage 2: 요약 + 브리핑 대본 동시 생성 (1회 AI 호출)
    # ═══════════════════════════════════════════════════

    def summarize_and_brief(self, news_list: list[dict]) -> tuple[list[dict], str]:
        """
        크롤링 완료된 중요 기사에 대해:
        - 각 기사별 AI 요약 (2~3문장)
        - 오늘의 브리핑 대본 (라디오 스타일)
        을 한 번의 AI 호출로 생성.

        Args:
            news_list: 본문 크롤링이 완료된 중요 기사 목록

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
            body_preview = news.get("본문 전문", "")[:1500]
            naver_desc = news.get("네이버 요약", "")
            news_texts.append(
                f"[뉴스 {idx + 1}]\n"
                f"주제: {news.get('주제', '기타')}\n"
                f"제목: {news.get('제목', '')}\n"
                f"네이버 요약: {naver_desc}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 베테랑 뉴스 에디터이자 인기 아침 라디오 진행자입니다.
아래 오늘의 주요 뉴스를 읽고 두 가지 작업을 수행해 주세요.

[작업 1] 각 뉴스의 핵심 내용을 1~2문장으로 한국어 요약
[작업 2] 뉴스를 엮어 자연스럽고 친근한 아침 브리핑 대본 작성

대본 규칙:
- "좋은 아침입니다"로 시작
- 주제별로 자연스럽게 전환하며 핵심 전달
- 각 뉴스 2~3문장으로 간결하게
- 전체 약 800~1200자
- 마무리 인사로 끝맺음
- 한국어로 작성

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
        """레거시 호환 — screen_importance로 래핑"""
        return self.screen_importance(news_list, topic_criteria)

    def generate_briefing_script(self, news_list):
        """레거시 호환 — 사용되지 않음"""
        _, briefing = self.summarize_and_brief(news_list)
        return briefing
