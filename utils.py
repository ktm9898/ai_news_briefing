import requests
import re
import logging

logger = logging.getLogger(__name__)

def get_weather_info():
    """
    네이버 검색을 활용하여 기상청 발표 서울 지역 당일 일기예보(날씨 상태, 최저/최고 기온)를 가져옵니다.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        url = 'https://search.naver.com/search.naver?query=서울날씨'
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text

        # 1. 날씨 상태 (예: 흐리고 한때 비, 구름많음, 맑음 등)
        summary_text_match = re.search(r'<p class="summary">([^<]+)</p>', html)
        weather_desc = summary_text_match.group(1).strip() if summary_text_match else ""

        if not weather_desc:
            weather_desc_match = re.search(r'<span class="weather before_slash">([^<]+)</span>', html)
            weather_desc = weather_desc_match.group(1).strip() if weather_desc_match else "맑음"

        # 2. 최저 / 최고 기온 추출
        lowest_match = re.search(r'<span class="lowest"><span class="blind">최저기온</span>(\d+)°?</span>', html)
        highest_match = re.search(r'<span class="highest"><span class="blind">최고기온</span>(\d+)°?</span>', html)

        temp_min = lowest_match.group(1) if lowest_match else None
        temp_max = highest_match.group(1) if highest_match else None

        if temp_min and temp_max:
            return f"서울 지역 오늘 날씨는 {weather_desc} 수준이며, 낮 최고 기온은 {temp_max}도, 최저 기온은 {temp_min}도가 될 것으로 예상됩니다."
        elif weather_desc:
            return f"서울 지역 오늘 날씨는 {weather_desc} 수준이 될 것으로 예상됩니다."
        else:
            return "오늘 서울 날씨는 무난한 날씨가 이어질 것으로 예상됩니다."

    except Exception as e:
        logger.error(f"네이버 날씨 정보 가져오기 실패: {e}")
        return "오늘 서울 날씨는 무난한 날씨가 이어질 것으로 예상됩니다."

if __name__ == "__main__":
    print(get_weather_info())
