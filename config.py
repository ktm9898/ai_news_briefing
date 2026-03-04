"""
config.py - 환경변수 로드 및 전역 설정

인증 방식:
  - 로컬: .env 파일에서 환경변수 로드
  - GitHub Actions: Repository Secrets → 환경변수
"""

import os
from pathlib import Path

# .env 파일 로드 (로컬 환경, 없으면 무시)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_config(key: str, default: str = "") -> str:
    """환경변수에서 설정값 로드"""
    return os.getenv(key, default)


# ── 프로젝트 경로 ─────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
CREDENTIALS_DIR = BASE_DIR / "credentials"

# 디렉토리 자동 생성
AUDIO_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR.mkdir(exist_ok=True)

# ── 네이버 검색 API ───────────────────────────────────
NAVER_CLIENT_ID = _get_config("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = _get_config("NAVER_CLIENT_SECRET")
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_NEWS_DISPLAY = 20  # 키워드별 API 검색 건수
MAX_PER_TOPIC = 20       # 주제당 최대 수집 건수 (AI 선별 전)
SIMILARITY_THRESHOLD = 0.8  # 중복 기사 판별을 위한 제목 유사도 임계값 (0.8 = 80%)

# ── Google Gemini API ─────────────────────────────────
GEMINI_API_KEY = _get_config("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"  # 최신 모델 사용

# 기본 중요도 판단 기준
DEFAULT_CRITERIA = """
상: 정책 변화, 큰 폭의 금리 변동, 업계에 직접적인 타격을 주는 사건
중: 신규 서비스 출시, 통계 지표 발표, 전문가 의견
하: 단순 홍보, 중복 기사, 개인의 단순 미담
""".strip()

# ── Google Sheets ─────────────────────────────────────
GOOGLE_SHEET_ID = _get_config("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_PATH = _get_config(
    "GOOGLE_CREDENTIALS_PATH",
    str(CREDENTIALS_DIR / "service_account.json"),
)

# 시트 탭 이름
SETTINGS_TAB = "Settings"
TOPIC_SETTINGS_TAB = "Topic_Settings"
NEWS_DATA_TAB = "News_Data"

# Settings 탭 헤더
SETTINGS_HEADERS = ["주제", "키워드", "활성화"]
TOPIC_SETTINGS_HEADERS = ["Topic", "Criteria"]

# News_Data 탭 헤더
NEWS_DATA_HEADERS = [
    "날짜", "주제", "언론사", "제목", "네이버 요약",
    "본문 전문", "링크", "AI 요약", "중요도"
]

# ── TTS ────────────────────────────────────────────────
TTS_VOICE = _get_config("TTS_VOICE", "ko-KR-SunHiNeural")

# ── 스케줄러 ───────────────────────────────────────────
SCHEDULE_HOUR = 7   # 매일 실행 시각 (시)
SCHEDULE_MINUTE = 0  # 매일 실행 시각 (분)
