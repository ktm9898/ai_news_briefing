import os
import json
from config import GEMINI_API_KEY
import google.generativeai as genai
from ai_analyzer import AIAnalyzer

def test_gemini():
    print(f"API Key present: {bool(GEMINI_API_KEY)}")
    analyzer = AIAnalyzer()
    
    mock_news = [
        {
            "주제": "상권활성화",
            "제목": "테스트 뉴스 제목",
            "본문": "이것은 기사 본문입니다. 상권이 아주 활성화되고 있습니다.",
        }
    ]
    
    try:
        results = analyzer._analyze_batch(mock_news, {"상권활성화": "상권 관련 내용"})
        print(json.dumps(results, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_gemini()
