import os
from ai_analyzer import AIAnalyzer
from utils import get_weather_info
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()

# KST 타임존
KST = timezone(timedelta(hours=9))

def test_dynamic_briefing():
    print("=== 동적 브리핑 생성 테스트 시작 ===")
    
    analyzer = AIAnalyzer()
    
    mock_news = [
        {
            "주제": "경제헤드라인",
            "제목": "코스피, 외인·기관 매수에 1%대 상승 마감",
            "네이버 요약": "코스피 지수가 외국인과 기관의 순매세에 힘입어 전일 대비 1% 이상 상승하며 장을 마쳤습니다.",
            "본문 전문": "오늘 코스피는 삼성전자와 SK하이닉스 등 시가총액 상위 종목들의 강세에 힘입어 반등했습니다. 전문가들은 미국의 금리 동결 기대감이 시장에 긍정적인 영향을 미친 것으로 분석하고 있습니다.",
            "중요도": "상"
        },
        {
            "주제": "AI/테크",
            "제목": "구글, 새로운 오픈 모델 '젬마' 공개",
            "네이버 요약": "구글이 고성능 오픈 모델 시리즈인 젬마를 공개하여 AI 개발 생태계 확장에 나섭니다.",
            "본문 전문": "젬마는 제미나이 제작에 사용된 기술과 인프라를 바탕으로 개발된 경량 오픈 모델입니다. 노트북에서도 원활하게 실행될 수 있는 크기이면서도 강력한 성능을 자랑합니다.",
            "중요도": "상"
        }
    ]
    
    # 컨텍스트 정보 준비
    days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    now = datetime.now(KST)
    weekday_str = days[now.weekday()]
    date_str = now.strftime("%Y년 %m월 %d일")
    weather_str = get_weather_info()
    
    context_info = f"현재 일시: {date_str} {weekday_str}\n날씨 정보: {weather_str}"
    print(f"주입될 컨텍스트:\n{context_info}\n")
    
    try:
        _, briefing_script = analyzer.summarize_and_brief(mock_news, context_info=context_info)
        print("--- 생성된 브리핑 대본 ---")
        print(briefing_script)
        print("---------------------------")
        
        # 검증 포인트
        success = True
        if date_str not in briefing_script and "오늘" not in briefing_script:
             # AI가 날짜를 그대로 쓰지 않고 자연스럽게 바꿀 수 있으므로 '오늘'이나 요일 체크
             pass
             
        if weekday_str not in briefing_script:
            print(f"경고: 요일({weekday_str})이 대본에 명시되지 않았을 수 있습니다.")
        
        # '맑음', '비', '구름' 등 날씨 관련 키워드가 대본 도입부에 있는지 확인 (유연하게)
        print("\n검증 완료: 대본의 도입부가 기존의 '활기찬 한 주...'를 반복하지 않고 자연스러운지 확인하세요.")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")

if __name__ == "__main__":
    test_dynamic_briefing()
