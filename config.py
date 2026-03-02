"""
config.py - 환경변수 로드 및 전역 설정
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ── 프로젝트 경로 ─────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
CREDENTIALS_DIR = BASE_DIR / "credentials"

# 디렉토리 자동 생성
AUDIO_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR.mkdir(exist_ok=True)

# ── 네이버 검색 API ───────────────────────────────────
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_NEWS_DISPLAY = 10  # 키워드당 최대 수집 건수

# ── Google Gemini API ─────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3-flash-preview"

# ── Google Sheets ─────────────────────────────────────
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    str(CREDENTIALS_DIR / "service_account.json"),
)

# 시트 탭 이름
SETTINGS_TAB = "Settings"
NEWS_DATA_TAB = "News_Data"

# Settings 탭 헤더
SETTINGS_HEADERS = ["카테고리", "키워드", "활성화"]

# News_Data 탭 헤더
NEWS_DATA_HEADERS = [
    "날짜", "카테고리", "언론사", "제목",
    "본문 전문", "링크", "AI 요약", "중요도",
]

# ── TTS ────────────────────────────────────────────────
TTS_VOICE = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")

# ── 스케줄러 ───────────────────────────────────────────
SCHEDULE_HOUR = 7   # 매일 실행 시각 (시)
SCHEDULE_MINUTE = 0  # 매일 실행 시각 (분)
