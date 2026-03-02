"""
ai_analyzer.py - Gemini API 기반 뉴스 분석 모듈

기능:
  - 뉴스 중요도 판단 (상/중/하)
  - 핵심 내용 요약 (2~3문장)
  - 브리핑 대본 생성 (카테고리별 핵심 뉴스 큐레이션)
"""

import json
import logging

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# Gemini API 초기화
genai.configure(api_key=GEMINI_API_KEY)


class AIAnalyzer:
    """Gemini 기반 뉴스 분석기"""

    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def analyze_news(self, news_list: list[dict]) -> list[dict]:
        """
        수집된 뉴스에 대해 중요도·요약을 생성.
        각 뉴스 항목에 'AI 요약'과 '중요도' 필드를 채워 반환.
        """
        if not news_list:
            return news_list

        # 뉴스를 배치로 처리 (API 호출 절약)
        batch_size = 5
        analyzed = []

        for i in range(0, len(news_list), batch_size):
            batch = news_list[i:i + batch_size]
            try:
                result = self._analyze_batch(batch)
                analyzed.extend(result)
            except Exception as e:
                logger.error(f"AI 분석 배치 실패 (인덱스 {i}~{i+len(batch)}): {e}")
                # 실패 시 원본 유지
                for news in batch:
                    news["AI 요약"] = "(분석 실패)"
                    news["중요도"] = "중"
                analyzed.extend(batch)

        return analyzed

    def _analyze_batch(self, batch: list[dict]) -> list[dict]:
        """뉴스 배치에 대해 Gemini로 중요도·요약 생성"""
        news_texts = []
        for idx, news in enumerate(batch):
            body_preview = news.get("본문 전문", "")[:2000]  # 토큰 절약
            news_texts.append(
                f"[뉴스 {idx + 1}]\n"
                f"제목: {news.get('제목', '')}\n"
                f"카테고리: {news.get('카테고리', '')}\n"
                f"본문(일부): {body_preview}\n"
            )

        prompt = f"""당신은 전문 뉴스 분석가입니다. 아래 뉴스들을 분석해 주세요.

{chr(10).join(news_texts)}

각 뉴스에 대해 다음을 JSON 배열로 반환하세요:
- "index": 뉴스 번호 (1부터)
- "summary": 핵심 내용 2~3문장 요약 (한국어)
- "importance": 중요도 ("상", "중", "하" 중 택1)

판단 기준:
- 상: 경제·정책적 파급력이 크거나, 다수에게 직접 영향을 미치는 뉴스
- 중: 관련 분야 종사자에게 유의미한 뉴스
- 하: 일반 정보성 뉴스

반드시 유효한 JSON 배열만 반환하세요. 다른 텍스트는 포함하지 마세요.
"""

        response = self.model.generate_content(prompt)
        text = response.text.strip()

        # JSON 블록 추출
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        results = json.loads(text)

        for item in results:
            idx = item.get("index", 1) - 1
            if 0 <= idx < len(batch):
                batch[idx]["AI 요약"] = item.get("summary", "")
                batch[idx]["중요도"] = item.get("importance", "중")

        return batch

    def generate_briefing_script(self, news_list: list[dict]) -> str:
        """
        카테고리별 핵심 뉴스를 엮어 라디오 브리핑 대본 생성.

        Args:
            news_list: AI 분석이 완료된 뉴스 목록

        Returns:
            브리핑 대본 텍스트
        """
        if not news_list:
            return "오늘은 수집된 뉴스가 없습니다."

        # 중요도 '상' 우선, 카테고리별 그룹핑
        important_news = [n for n in news_list if n.get("중요도") == "상"]
        if not important_news:
            important_news = news_list[:10]  # 중요도 '상'이 없으면 상위 10개

        # 카테고리별 분류
        by_category = {}
        for news in important_news:
            cat = news.get("카테고리", "기타")
            by_category.setdefault(cat, []).append(news)

        news_summary_text = []
        for cat, items in by_category.items():
            news_summary_text.append(f"\n## [{cat}] 카테고리")
            for n in items[:5]:  # 카테고리당 최대 5건
                news_summary_text.append(
                    f"- 제목: {n.get('제목', '')}\n"
                    f"  요약: {n.get('AI 요약', '')}"
                )

        prompt = f"""당신은 인기 있는 아침 뉴스 라디오의 진행자입니다.
아래 오늘의 핵심 뉴스들을 바탕으로 자연스럽고 친근한 아침 브리핑 대본을 작성해 주세요.

{chr(10).join(news_summary_text)}

대본 작성 규칙:
1. "좋은 아침입니다"로 시작하여 날씨나 간단한 인사 후 뉴스로 진입
2. 카테고리별로 자연스럽게 전환하며 핵심 내용 전달
3. 각 뉴스는 2~3문장으로 간결하게 설명
4. 전체 대본은 3~5분 분량 (약 800~1200자)
5. 마무리 인사로 끝맺음
6. 한국어로 작성

대본만 반환해 주세요. 다른 설명은 포함하지 마세요.
"""

        try:
            response = self.model.generate_content(prompt)
            script = response.text.strip()
            logger.info(f"브리핑 대본 생성 완료 ({len(script)}자)")
            return script
        except Exception as e:
            logger.error(f"브리핑 대본 생성 실패: {e}")
            return "브리핑 대본 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
