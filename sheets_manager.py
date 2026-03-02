"""
sheets_manager.py - Google Sheets CRUD 관리 모듈

Settings 탭: 카테고리-키워드 설정 관리
News_Data 탭: 수집된 뉴스 통합 저장소

인증 방식:
  - 로컬: credentials/service_account.json 파일
  - Streamlit Cloud: st.secrets["gcp_service_account"]
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEET_ID,
    SETTINGS_TAB,
    NEWS_DATA_TAB,
    SETTINGS_HEADERS,
    NEWS_DATA_HEADERS,
)


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_credentials():
    """
    환경에 따라 적절한 인증 방법 선택.
    1순위: Streamlit Cloud Secrets (st.secrets)
    2순위: 로컬 JSON 파일
    """
    # 1순위: Streamlit Cloud Secrets
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return creds
    except Exception:
        pass

    # 2순위: 로컬 JSON 파일
    if os.path.exists(GOOGLE_CREDENTIALS_PATH):
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
        return creds

    raise FileNotFoundError(
        "Google 인증 정보를 찾을 수 없습니다.\n"
        "로컬: credentials/service_account.json 파일을 배치하세요.\n"
        "Streamlit Cloud: Secrets에 [gcp_service_account] 섹션을 추가하세요."
    )


class SheetsManager:
    """Google Sheets 읽기/쓰기 관리자"""

    def __init__(self):
        creds = _get_credentials()
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)
        self._ensure_tabs()

    # ── 초기화 ────────────────────────────────────────

    def _ensure_tabs(self):
        """Settings / News_Data 탭이 없으면 자동 생성"""
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if SETTINGS_TAB not in existing:
            ws = self.spreadsheet.add_worksheet(
                title=SETTINGS_TAB, rows=100, cols=len(SETTINGS_HEADERS)
            )
            ws.append_row(SETTINGS_HEADERS)

        if NEWS_DATA_TAB not in existing:
            ws = self.spreadsheet.add_worksheet(
                title=NEWS_DATA_TAB, rows=1000, cols=len(NEWS_DATA_HEADERS)
            )
            ws.append_row(NEWS_DATA_HEADERS)

    # ── Settings 탭 ──────────────────────────────────

    def get_settings(self) -> list[dict]:
        """
        Settings 탭에서 활성화된 키워드-카테고리 목록 반환.
        Returns:
            [{"카테고리": "상권", "키워드": "용산구 골목상권", "활성화": "TRUE"}, ...]
        """
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        records = ws.get_all_records()
        return records

    def get_active_settings(self) -> list[dict]:
        """활성화(TRUE)된 설정만 반환"""
        return [
            s for s in self.get_settings()
            if str(s.get("활성화", "")).upper() == "TRUE"
        ]

    def update_settings(self, data: list[dict]):
        """
        Settings 탭 전체를 새 데이터로 교체.
        Args:
            data: [{"카테고리": ..., "키워드": ..., "활성화": ...}, ...]
        """
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        ws.clear()
        ws.append_row(SETTINGS_HEADERS)
        for row in data:
            ws.append_row([
                row.get("카테고리", ""),
                row.get("키워드", ""),
                row.get("활성화", "TRUE"),
            ])

    def add_setting(self, category: str, keyword: str, active: str = "TRUE"):
        """Settings 탭에 새 항목 추가"""
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        ws.append_row([category, keyword, active])

    def delete_setting(self, row_index: int):
        """Settings 탭에서 특정 행 삭제 (1-indexed, 헤더 = 1)"""
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        ws.delete_rows(row_index)

    # ── News_Data 탭 ─────────────────────────────────

    def get_existing_links(self) -> set[str]:
        """News_Data 탭에 이미 저장된 링크 집합 반환 (중복 방지용)"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        try:
            link_col_index = NEWS_DATA_HEADERS.index("링크") + 1
            links = ws.col_values(link_col_index)
            return set(links[1:])  # 헤더 제외
        except Exception:
            return set()

    def append_news(self, news_list: list[dict]):
        """
        뉴스 데이터를 News_Data 탭에 추가.
        Args:
            news_list: [{"날짜": ..., "카테고리": ..., ...}, ...]
        """
        if not news_list:
            return

        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        rows = []
        for news in news_list:
            rows.append([
                news.get("날짜", ""),
                news.get("카테고리", ""),
                news.get("언론사", ""),
                news.get("제목", ""),
                news.get("본문 전문", ""),
                news.get("링크", ""),
                news.get("AI 요약", ""),
                news.get("중요도", ""),
                news.get("네이버 요약", ""),
            ])

        # 배치 추가 (API 호출 절약)
        ws.append_rows(rows, value_input_option="USER_ENTERED")

    def get_news_by_date(self, date_str: str) -> list[dict]:
        """특정 날짜의 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        return [r for r in records if r.get("날짜", "") == date_str]

    def get_news_by_category(self, category: str) -> list[dict]:
        """특정 카테고리의 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        return [r for r in records if r.get("카테고리", "") == category]

    def get_all_news(self) -> list[dict]:
        """모든 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        return ws.get_all_records()

    def get_recent_news(self, limit: int = 50) -> list[dict]:
        """최근 뉴스 반환 (최신순)"""
        all_news = self.get_all_news()
        return sorted(
            all_news,
            key=lambda x: x.get("날짜", ""),
            reverse=True,
        )[:limit]

    def update_news_analysis(self, row_index: int, summary: str, importance: str):
        """특정 뉴스의 AI 요약과 중요도 업데이트 (1-indexed, 헤더 = 1)"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        summary_col = NEWS_DATA_HEADERS.index("AI 요약") + 1
        importance_col = NEWS_DATA_HEADERS.index("중요도") + 1
        ws.update_cell(row_index, summary_col, summary)
        ws.update_cell(row_index, importance_col, importance)
