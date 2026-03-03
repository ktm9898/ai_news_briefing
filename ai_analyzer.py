"""
ai_analyzer.py - Gemini API 기반 뉴스 분석 모듈

기능:
  - 뉴스 중요도 판단 (상/중/하)
  - 핵심 내용 요약 (2~3문장)
  - 브리핑 대본 생성 (주제별 핵심 뉴스 큐레이션)
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
    """Gemini 기반 뉴스 분석기"""

    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def analyze_news(
        self,
        news_list: list[dict],
        topic_criteria: dict[str, str] = None,
    ) -> list[dict]:
        """
        수집된 뉴스에 대해 중요도·요약을 생성.
        topic_criteria: {"주제명": "상/중/하 판단 기준..."}
        """
        if not news_list:
            return news_list

        # API 키 확인
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY가 설정되지 않았습니다.")
            for news in news_list:
                news["AI 요약"] = "(GEMINI_API_KEY 미설정)"
                news["중요도"] = "중"
            return news_list

        # 뉴스를 배치로 처리 (한 번에 최대 30건)
        batch_size = 30
        analyzed = []
        total_batches = (len(news_list) + batch_size - 1) // batch_size
        
        logger.info(f"AI 분석 시작: 총 {len(news_list)}건, {total_batches}개 배치로 처리")

        for i in range(0, len(news_list), batch_size):
            batch_num = (i // batch_size) + 1
            batch = news_list[i:i + batch_size]
            try:
                result = self._analyze_batch(batch, topic_criteria)
                analyzed.extend(result)
                logger.info(f"배치 완료 ({batch_num}/{total_batches})")
            except Exception as e:
                logger.error(f"AI 분석 배치 실패 (배치 {batch_num}): {e}")
                for news in batch:
                    news["AI 요약"] = "(분석 실패)"
                    news["중요도"] = "하"
                analyzed.extend(batch)

        return analyzed

    def _analyze_batch(self, batch: list[dict], topic_criteria: dict[str, str] = None) -> list[dict]:
        """주제별로 그룹화하여 Gemini 분석 요청"""
        # 주제별 그룹화
        topic_groups = {}
        for news in batch:
            t = news.get("주제", "기타")
            topic_groups.setdefault(t, []).append(news)

        final_batch_results = []

        for topic, group in topic_groups.items():
            criteria = (topic_criteria or {}).get(topic, DEFAULT_CRITERIA)
            
            news_texts = []
            for idx, news in enumerate(group):
                body_preview = news.get("본문 전문", "")[:1000] # 토큰 및 출력 길이 제한 방지 (2000 -> 1000)
                news_texts.append(
                    f"[뉴스 {idx + 1}]\n"
                    f"제목: {news.get('제목', '')}\n"
                    f"본문(일부): {body_preview}\n"
                )

            prompt = f"""당신은 베테랑 뉴스 에디터이자 AI 분석가입니다. 
제공된 주제 '{topic}'에 대한 뉴스 목록을 읽고 분석해 주세요.

[중요도 판단 기준 - {topic}]
{criteria}

[분석 지침]
1. 각 뉴스의 핵심 내용을 1~2문장으로 한국어 요약해 주세요.
2. 위 기준에 따라 중요도를 '상', '중', '하' 중 하나로 판별해 주세요.
3. 결과는 반드시 다음과 같은 JSON 배열 형식으로만 응답해 주세요:
[
  {{"index": 1, "summary": "요약 내용...", "importance": "상"}},
  ...
]

[뉴스 목록]
{chr(10).join(news_texts)}
"""
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # JSON 모드 강제
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            response_mime_type="application/json",
                        )
                    )
                    text = response.text.strip()

                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()

                    # 가장 바깥쪽 대괄호를 찾아 추출 (안전한 파싱)
                    start_idx = text.find('[')
                    end_idx = text.rfind(']')
                    if start_idx != -1 and end_idx != -1:
                        text = text[start_idx:end_idx+1]
                        
                    import json
                    results = json.loads(text)

                    for item in results:
                        idx = item.get("index", 1) - 1
                        if 0 <= idx < len(group):
                            group[idx]["AI 요약"] = item.get("summary", "")
                            group[idx]["중요도"] = item.get("importance", "중")
                    
                    break # 성공 시 루프 탈출
                        
                except Exception as e:
                    logger.error(f"AI 주제 분석 (시도 {attempt+1}/{max_retries}) 실패 ({topic}): {e}")
                    if attempt == max_retries - 1:
                        for news in group:
                            news["AI 요약"] = "(분석 실패)"
                            news["중요도"] = "중" # 실패 시 배제하지 않도록 '중'으로 기본값 변경
                    else:
                        time.sleep(2) # 재시도 전 대기

            
            final_batch_results.extend(group)

        return final_batch_results

    def generate_briefing_script(self, news_list: list[dict]) -> str:
        """
        주제별 핵심 뉴스를 엮어 라디오 브리핑 대본 생성.

        Args:
            news_list: AI 분석이 완료된 뉴스 목록

        Returns:
            브리핑 대본 텍스트
        """
        if not news_list:
            return "오늘은 수집된 뉴스가 없습니다."

        # 중요도 '상' 우선, 주제별 그룹핑
        important_news = [n for n in news_list if n.get("중요도") == "상"]
        if not important_news:
            important_news = news_list[:10]  # 중요도 '상'이 없으면 상위 10개

        # 주제별 분류
        by_topic = {}
        for news in important_news:
            topic = news.get("주제", "기타")
            by_topic.setdefault(topic, []).append(news)

        news_summary_text = []
        for topic, items in by_topic.items():
            news_summary_text.append(f"\n## [{topic}] 주제")
            for n in items[:5]:  # 주제당 최대 5건
                news_summary_text.append(
                    f"- 제목: {n.get('제목', '')}\n"
                    f"  요약: {n.get('AI 요약', '')}"
                )

        prompt = f"""당신은 인기 있는 아침 뉴스 라디오의 진행자입니다.
아래 오늘의 핵심 뉴스들을 바탕으로 자연스럽고 친근한 아침 브리핑 대본을 작성해 주세요.

{chr(10).join(news_summary_text)}

대본 작성 규칙:
1. "좋은 아침입니다"로 시작하여 날씨나 간단한 인사 후 뉴스로 진입
2. 주제별로 자연스럽게 전환하며 핵심 내용 전달
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
