import requests
import logging

logger = logging.getLogger(__name__)

def get_weather_info():
    """
    Open-Meteo API를 사용하여 서울의 당일 전체 일기예보(최고/최저기온, 날씨상태)를 가져옵니다.
    """
    try:
        # 서울 좌표: 위도 37.5665, 경도 126.9780
        url = "https://api.open-meteo.com/v1/forecast?latitude=37.5665&longitude=126.9780&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FSeoul"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        daily = data.get("daily", {})
        weather_codes = daily.get("weathercode", [])
        temp_maxs = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        
        code = weather_codes[0] if weather_codes else 0
        temp_max = round(temp_maxs[0]) if temp_maxs else 0
        temp_min = round(temp_mins[0]) if temp_mins else 0
        
        # WMO Weather interpretation codes (WW)
        weather_map = {
            0: "맑음",
            1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
            45: "안개", 48: "이슬섞인 안개",
            51: "가벼운 이슬비", 53: "이슬비", 55: "강한 이슬비",
            61: "약한 비", 63: "보통 비", 65: "강한 비",
            71: "약한 눈", 73: "보통 눈", 75: "강한 눈",
            77: "눈발",
            80: "약한 소나기", 81: "보통 소나기", 82: "강한 소나기",
            85: "약한 눈소나기", 86: "강한 눈소나기",
            95: "뇌우", 96: "뇌우와 약한 우박", 99: "뇌우와 강한 우박"
        }
        
        weather_desc = weather_map.get(code, "알 수 없음")
        return f"서울 지역 오늘 날씨는 대체로 {weather_desc} 수준이며, 낮 최고 기온은 {temp_max}도, 최저 기온은 {temp_min}도가 될 것으로 예상됩니다."
        
    except Exception as e:
        logger.error(f"날씨 정보 가져오기 실패: {e}")
        return "오늘 서울 날씨는 무난한 날씨가 이어질 것으로 예상됩니다."

if __name__ == "__main__":
    print(get_weather_info())
