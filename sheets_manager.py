"""
sheets_manager.py - Google Sheets CRUD 관리 모듈

Settings 탭: 주제-키워드 설정 관리
News_Data 탭: 수집된 뉴스 통합 저장소

인증 방식:
  - 로컬: credentials/service_account.json 파일
  - GitHub Actions: GOOGLE_CREDENTIALS_JSON 환경변수 (base64)
"""

import os
import json
import base64
import tempfile
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEET_ID,
    SETTINGS_TAB,
    TOPIC_SETTINGS_TAB,
    NEWS_DATA_TAB,
    SETTINGS_HEADERS,
    TOPIC_SETTINGS_HEADERS,
    NEWS_DATA_HEADERS,
)


import logging
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def _get_credentials():
    """
    환경에 따라 적절한 인증 방법 선택.
    1순위: GOOGLE_CREDENTIALS_JSON 환경변수 (base64 인코딩된 서비스 계정 JSON)
    2순위: 로컬 JSON 파일
    """
    # 1순위: 환경변수 (GitHub Actions용)
    creds_raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if creds_raw:
        try:
            # 먼저 생 JSON인지 확인
            if creds_raw.startswith("{"):
                creds_dict = json.loads(creds_raw)
            else:
                # 아니면 base64로 시도
                creds_json = base64.b64decode(creds_raw).decode("utf-8")
                creds_dict = json.loads(creds_json)
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return creds
        except Exception as e:
            logger.error(f"환경변수 인증 정보 로드 실패: {e}")
            # 여기서 멈추지 않고 로컬 파일 확인으로 넘어감

    # 2순위: 로컬 JSON 파일
    if os.path.exists(GOOGLE_CREDENTIALS_PATH):
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
        return creds

    raise FileNotFoundError(
        "Google 인증 정보를 찾을 수 없습니다.\n"
        "로컬: credentials/service_account.json 파일을 배치하세요.\n"
        "GitHub Actions: GOOGLE_CREDENTIALS_JSON 시크릿을 설정하세요."
    )


class SheetsManager:
    """Google Sheets 읽기/쓰기 관리자"""

    def __init__(self):
        creds = _get_credentials()
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)
        self._ensure_tabs()

    # ── 초기화 ────────────────────────────────────────

    def _ensure_email_column(self, tab_name: str, expected_headers: list[str]):
        """시트에 '이메일' 컬럼이 첫 번째 열에 없으면 삽입하여 마이그레이션"""
        try:
            ws = self.spreadsheet.worksheet(tab_name)
            first_row = ws.row_values(1)
            if first_row and ("이메일" not in first_row and "Email" not in first_row):
                # 첫 번째 열로 '이메일' 컬럼 추가
                ws.insert_cols([[expected_headers[0]] + [""] * (ws.row_count - 1)], col=1)
                logger.info(f"'{tab_name}' 시트에 '이메일' 컬럼이 첫 번째 열로 삽입되었습니다.")
        except Exception as e:
            logger.warning(f"'{tab_name}' 시트 이메일 컬럼 검사 중 오류 (무시 가능): {e}")

    def _ensure_tabs(self):
        """Settings / News_Data / Topic_Settings / Briefing / Briefing_Docs 탭이 없으면 자동 생성 및 이메일 컬럼 추가 검사"""
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        # TOPIC_SETTINGS
        if TOPIC_SETTINGS_TAB not in existing:
            ws = self.spreadsheet.add_worksheet(
                title=TOPIC_SETTINGS_TAB, rows=100, cols=len(TOPIC_SETTINGS_HEADERS)
            )
            ws.append_row(TOPIC_SETTINGS_HEADERS)
        else:
            self._ensure_email_column(TOPIC_SETTINGS_TAB, TOPIC_SETTINGS_HEADERS)

        # NEWS_DATA
        if NEWS_DATA_TAB not in existing:
            ws = self.spreadsheet.add_worksheet(
                title=NEWS_DATA_TAB, rows=1000, cols=len(NEWS_DATA_HEADERS)
            )
            ws.append_row(NEWS_DATA_HEADERS)
        else:
            self._ensure_email_column(NEWS_DATA_TAB, NEWS_DATA_HEADERS)

        # Briefing
        if "Briefing" not in existing:
            ws = self.spreadsheet.add_worksheet(
                title="Briefing", rows=100, cols=3
            )
            ws.append_row(["이메일", "날짜", "대본"])
        else:
            self._ensure_email_column("Briefing", ["이메일", "날짜", "대본"])

        # Briefing_Docs
        if "Briefing_Docs" not in existing:
            ws = self.spreadsheet.add_worksheet(
                title="Briefing_Docs", rows=100, cols=4
            )
            ws.append_row(["이메일", "날짜", "제목", "내용"])
        else:
            self._ensure_email_column("Briefing_Docs", ["이메일", "날짜", "제목", "내용"])

        # Settings
        if SETTINGS_TAB in existing:
            self._ensure_email_column(SETTINGS_TAB, SETTINGS_HEADERS)

        # Approved_Users
        if "Approved_Users" not in existing:
            ws = self.spreadsheet.add_worksheet(
                title="Approved_Users", rows=100, cols=4
            )
            ws.append_row(["이메일", "상태", "등록일", "승인일"])
        else:
            self._ensure_email_column("Approved_Users", ["이메일", "상태", "등록일", "승인일"])

        # Weekly_Briefing_Docs
        if "Weekly_Briefing_Docs" not in existing:
            ws = self.spreadsheet.add_worksheet(
                title="Weekly_Briefing_Docs", rows=100, cols=4
            )
            ws.append_row(["이메일", "날짜", "제목", "내용"])
        else:
            self._ensure_email_column("Weekly_Briefing_Docs", ["이메일", "날짜", "제목", "내용"])

    # ── Settings 탭 ──────────────────────────────────

    def get_settings(self, email: str | None = None) -> list[dict]:
        """
        Settings 탭에서 활성화된 키워드-주제 목록 반환.
        """
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        records = ws.get_all_records()
        if email:
            target = email.strip().lower()
            return [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
        return records

    def get_active_settings(self, email: str | None = None) -> list[dict]:
        """활성화(TRUE)된 설정만 반환"""
        return [
            s for s in self.get_settings(email)
            if str(s.get("활성화", "")).upper() == "TRUE"
        ]

    def get_approved_emails(self) -> set[str]:
        """Approved_Users 탭에서 승인된 이메일 목록 반환"""
        try:
            ws = self.spreadsheet.worksheet("Approved_Users")
            records = ws.get_all_records()
            return set(
                str(r.get("이메일", "")).strip().lower() 
                for r in records 
                if str(r.get("상태", "")).strip().lower() == "approved" and str(r.get("이메일", "")).strip()
            )
        except Exception as e:
            logger.error(f"Approved_Users 시트 조회 실패 (기본값 빈 셋 반환): {e}")
            return set()

    def update_settings(self, data: list[dict], email: str | None = None):
        """
        Settings 탭을 업데이트. 만약 email이 주어지면 해당 email의 데이터만 교체하고
        나머지 이메일의 데이터는 그대로 둡니다. email이 없으면 전체 교체.
        """
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        if email:
            target = email.strip().lower()
            all_data = self.get_settings()
            # 해당 이메일이 아닌 데이터만 보존
            preserved = [r for r in all_data if str(r.get("이메일", "")).strip().lower() != target]
            # 새 데이터 추가
            for row in data:
                row["이메일"] = email
                preserved.append(row)
            
            ws.clear()
            ws.append_row(SETTINGS_HEADERS)
            rows_to_append = []
            for row in preserved:
                rows_to_append.append([
                    row.get("이메일", ""),
                    row.get("주제", ""),
                    row.get("키워드", ""),
                    row.get("활성화", "TRUE")
                ])
            if rows_to_append:
                ws.append_rows(rows_to_append)
        else:
            ws.clear()
            ws.append_row(SETTINGS_HEADERS)
            rows_to_append = []
            for row in data:
                rows_to_append.append([
                    row.get("이메일", ""),
                    row.get("주제", ""),
                    row.get("키워드", ""),
                    row.get("활성화", "TRUE"),
                ])
            if rows_to_append:
                ws.append_rows(rows_to_append)

    def add_setting(self, topic: str, keyword: str, active: str = "TRUE", email: str = ""):
        """Settings 탭에 새 항목 추가"""
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        ws.append_row([email, topic, keyword, active])

    def delete_setting(self, row_index: int):
        """Settings 탭에서 특정 행 삭제 (1-indexed, 헤더 = 1)"""
        ws = self.spreadsheet.worksheet(SETTINGS_TAB)
        ws.delete_rows(row_index)

    # ── Topic_Settings 탭 ─────────────────────────────

    def get_all_topic_criteria(self, email: str | None = None) -> dict[str, str]:
        """주제별 AI 중요도 기준 맵 반환"""
        try:
            ws = self.spreadsheet.worksheet(TOPIC_SETTINGS_TAB)
            records = ws.get_all_records()
            if email:
                target = email.strip().lower()
                records = [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
            return {r["Topic"]: r["Criteria"] for r in records if r.get("Topic") and r.get("Criteria")}
        except Exception:
            return {}

    def update_topic_criteria(self, topic: str, criteria: str, email: str = ""):
        """특정 주제의 AI 중요도 기준 업데이트"""
        ws = self.spreadsheet.worksheet(TOPIC_SETTINGS_TAB)
        data = ws.get_all_records()
        
        target_email = email.strip().lower()
        found_row = -1
        for idx, row in enumerate(data):
            row_email = str(row.get("이메일", "")).strip().lower()
            if row.get("Topic") == topic and row_email == target_email:
                found_row = idx + 2
                break
        
        if found_row != -1:
            ws.update_cell(found_row, 3, criteria)
        else:
            ws.append_row([email, topic, criteria])

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

    def append_news(self, news_list: list[dict], email: str = ""):
        """
        뉴스 데이터를 News_Data 탭에 추가.
        Args:
            news_list: [{"날짜": ..., "주제": ..., ...}, ...]
        """
        if not news_list:
            return

        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        rows = []
        for news in news_list:
            rows.append([
                email,
                news.get("날짜", ""),
                news.get("주제", ""),
                news.get("언론사", ""),
                news.get("제목", ""),
                news.get("네이버 요약", ""),
                news.get("본문 전문", ""),
                news.get("링크", ""),
                news.get("AI 요약", ""),
                news.get("중요도", ""),
            ])

        # 배치 추가 (API 호출 절약)
        ws.append_rows(rows, value_input_option="USER_ENTERED")

    def get_news_by_date(self, date_str: str, email: str | None = None) -> list[dict]:
        """특정 날짜의 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        if email:
            target = email.strip().lower()
            records = [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
        return [r for r in records if r.get("날짜", "") == date_str]

    def get_news_by_topic(self, topic: str, email: str | None = None) -> list[dict]:
        """특정 주제의 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        if email:
            target = email.strip().lower()
            records = [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
        return [r for r in records if r.get("주제", "") == topic]

    def get_all_news(self, email: str | None = None) -> list[dict]:
        """모든 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        if email:
            target = email.strip().lower()
            return [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
        return records

    def get_recent_news(self, limit: int = 50, email: str | None = None) -> list[dict]:
        """최근 뉴스 반환 (최신순)"""
        all_news = self.get_all_news(email)
        return sorted(
            all_news,
            key=lambda x: x.get("날짜", ""),
            reverse=True,
        )[:limit]

    def update_news_analysis(self, row_index: int, summary: str, importance: str):
        """특정 뉴스의 AI 요약과 중요도 업데이트 (1-indexed, 헤더 = 1) - 레거시 대응"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        summary_col = NEWS_DATA_HEADERS.index("AI 요약") + 1
        importance_col = NEWS_DATA_HEADERS.index("중요도") + 1
        ws.update_cell(row_index, summary_col, summary)
        ws.update_cell(row_index, importance_col, importance)

    def save_briefing(self, script: str, email: str = ""):
        """
        AI 브리핑 대본을 Briefing 탭에 저장.
        매번 최신 대본으로 덮어씁니다.
        """
        tab_name = "Briefing"
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if tab_name not in existing:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=100, cols=3)
            ws.append_row(["이메일", "날짜", "대본"])
        else:
            ws = self.spreadsheet.worksheet(tab_name)

        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        today = datetime.now(KST).strftime("%Y-%m-%d")

        target_email = email.strip().lower()

        # 기존 데이터 확인 → 이메일과 오늘 날짜 행이 있으면 업데이트, 없으면 추가
        data = ws.get_all_values()
        updated = False
        for idx, row in enumerate(data):
            if idx == 0:
                continue  # 헤더 건너뛰기
            row_email = str(row[0]).strip().lower()
            row_date = str(row[1]).strip()
            if row_email == target_email and row_date == today:
                ws.update_cell(idx + 1, 3, script)
                updated = True
                break

        if not updated:
            ws.append_row([email, today, script])

    def save_briefing_doc(self, title: str, content: str, email: str = ""):
        """
        AI 브리핑 리포트(문서용)를 Briefing_Docs 탭에 저장.
        """
        tab_name = "Briefing_Docs"
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if tab_name not in existing:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=100, cols=4)
            ws.append_row(["이메일", "날짜", "제목", "내용"])
        else:
            ws = self.spreadsheet.worksheet(tab_name)

        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        today = datetime.now(KST).strftime("%Y-%m-%d")

        target_email = email.strip().lower()

        # 기존 데이터 확인 → 이메일과 오늘 날짜 행이 있으면 업데이트, 없으면 추가
        data = ws.get_all_values()
        updated = False
        for idx, row in enumerate(data):
            if idx == 0:
                continue
            row_email = str(row[0]).strip().lower()
            row_date = str(row[1]).strip()
            if row_email == target_email and row_date == today:
                ws.update_cell(idx + 1, 3, title)
                ws.update_cell(idx + 1, 4, content)
                updated = True
                break

        if not updated:
            ws.append_row([email, today, title, content])

    def get_news_by_date_range(self, start_date: str, end_date: str, email: str | None = None) -> list[dict]:
        """시작 날짜와 종료 날짜 사이(포함)의 뉴스 반환"""
        ws = self.spreadsheet.worksheet(NEWS_DATA_TAB)
        records = ws.get_all_records()
        if email:
            target = email.strip().lower()
            records = [r for r in records if str(r.get("이메일", "")).strip().lower() == target]
        
        import datetime
        try:
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"날짜 포맷 오류 (YYYY-MM-DD 필요): start={start_date}, end={end_date}. Error: {e}")
            return []

        results = []
        for r in records:
            r_date_str = r.get("날짜", "")
            if not r_date_str:
                continue
            try:
                r_date_formatted = self._format_date_string(r_date_str)
                r_dt = datetime.datetime.strptime(r_date_formatted, "%Y-%m-%d").date()
                if start_dt <= r_dt <= end_dt:
                    results.append(r)
            except Exception as ex:
                continue
        return results

    def _format_date_string(self, date_str: str) -> str:
        """날짜 문자열을 YYYY-MM-DD 형식으로 변환"""
        import re
        import datetime
        date_str = str(date_str).strip()
        match = re.match(r'(\d{4})[\.\-\/\s]+(\d{1,2})[\.\-\/\s]+(\d{1,2})', date_str)
        if match:
            return f"{match[1]}-{int(match[2]):02d}-{int(match[3]):02d}"
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return d.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def save_weekly_briefing_doc(self, title: str, content: str, date_range_str: str, email: str = ""):
        """
        AI 주간 브리핑 리포트를 Weekly_Briefing_Docs 탭에 저장.
        """
        tab_name = "Weekly_Briefing_Docs"
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if tab_name not in existing:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=100, cols=4)
            ws.append_row(["이메일", "날짜", "제목", "내용"])
        else:
            ws = self.spreadsheet.worksheet(tab_name)

        target_email = email.strip().lower()

        data = ws.get_all_values()
        updated = False
        for idx, row in enumerate(data):
            if idx == 0:
                continue
            row_email = str(row[0]).strip().lower()
            row_date = str(row[1]).strip()
            if row_email == target_email and row_date == date_range_str:
                ws.update_cell(idx + 1, 3, title)
                ws.update_cell(idx + 1, 4, content)
                updated = True
                break

        if not updated:
            ws.append_row([email, date_range_str, title, content])
