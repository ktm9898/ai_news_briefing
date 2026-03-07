import requests
import logging

logger = logging.getLogger(__name__)

def get_weather_info():
    """
    Open-Meteo API를 사용하여 서울의 현재 날씨 정보를 가져옵니다.
    별도의 API 키가 필요 없는 공개 API를 사용합니다.
    """
    try:
        # 서울 좌표: 위도 37.5665, 경도 126.9780
        url = "https://api.open-meteo.com/v1/forecast?latitude=37.5665&longitude=126.9780&current_weather=true&timezone=Asia%2FSeoul"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get("current_weather", {})
        temp = current.get("temperature")
        code = current.get("weathercode")
        
        # WMO Weather interpretation codes (WW)
        # https://open-meteo.com/en/docs
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
        return f"서울 현재 날씨는 {weather_desc}, 기온은 영상 {temp}도입니다." if temp > 0 else f"서울 현재 날씨는 {weather_desc}, 기온은 영하 {abs(temp)}도입니다."
        
    except Exception as e:
        logger.error(f"날씨 정보 가져오기 실패: {e}")
        return "날씨 정보를 불러오지 못했습니다."

if __name__ == "__main__":
    print(get_weather_info())
