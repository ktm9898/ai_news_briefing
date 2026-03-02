"""
app.py - AI 뉴스 비서 메인 대시보드 (Streamlit)

기능:
  - 🎙️ 브리핑 오디오 플레이어
  - 📰 통합 뉴스 피드 (카테고리/중요도/날짜 필터)
  - 🔄 수동 새로고침 (즉시 파이프라인 실행)
  - ⏰ 자동 스케줄러 제어
"""

import logging
import streamlit as st
from datetime import datetime

from config import SCHEDULE_HOUR, SCHEDULE_MINUTE

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── 페이지 설정 ────────────────────────────────────────
st.set_page_config(
    page_title="AI 뉴스 비서",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 커스텀 CSS ─────────────────────────────────────────
st.markdown("""
<style>
    /* 전체 폰트 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }

    /* 헤더 영역 */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.85;
        font-size: 1rem;
    }

    /* 뉴스 카드 */
    .news-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .news-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }

    /* 중요도 배지 */
    .badge-high {
        background: linear-gradient(135deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-mid {
        background: linear-gradient(135deg, #feca57, #ff9f43);
        color: #333;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-low {
        background: linear-gradient(135deg, #48dbfb, #0abde3);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* 카테고리 태그 */
    .category-tag {
        background: #f1f3f8;
        color: #667eea;
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 500;
    }

    /* 통계 카드 */
    .stat-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }
    .stat-number {
        font-size: 2rem;
        font-weight: 700;
        color: #667eea;
    }
    .stat-label {
        color: #888;
        font-size: 0.85rem;
        margin-top: 0.25rem;
    }

    /* 오디오 플레이어 영역 */
    .audio-section {
        background: linear-gradient(135deg, #2d3436 0%, #636e72 100%);
        border-radius: 16px;
        padding: 2rem;
        color: white;
        margin-bottom: 2rem;
    }

    /* 사이드바 */
    .sidebar-info {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        font-size: 0.85rem;
        color: #666;
    }

    /* Streamlit 기본 버튼 오버라이드 */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)


# ── 유틸리티 함수 ────────────────────────────────────

def get_importance_badge(importance: str) -> str:
    """중요도에 따른 배지 HTML"""
    badges = {
        "상": '<span class="badge-high">🔴 중요</span>',
        "중": '<span class="badge-mid">🟡 보통</span>',
        "하": '<span class="badge-low">🔵 일반</span>',
    }
    return badges.get(importance, badges["중"])


def init_session_state():
    """세션 상태 초기화"""
    if "scheduler" not in st.session_state:
        st.session_state.scheduler = None
    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = None


init_session_state()


# ── 사이드바 ──────────────────────────────────────────

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/news.png", width=64)
    st.title("AI 뉴스 비서")
    st.caption("통합 관리형 브리핑 시스템")

    st.divider()

    # 스케줄러 제어
    st.subheader("⏰ 자동 스케줄러")

    scheduler_status = "🔴 중지됨"
    if st.session_state.scheduler and st.session_state.scheduler.is_running:
        scheduler_status = "🟢 실행 중"

    st.markdown(f"상태: **{scheduler_status}**")
    st.markdown(f"예약 시각: 매일 **{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}**")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ 시작", use_container_width=True):
            try:
                from scheduler import NewsScheduler
                if st.session_state.scheduler is None:
                    st.session_state.scheduler = NewsScheduler()
                st.session_state.scheduler.start()
                st.success("스케줄러 시작됨!")
                st.rerun()
            except Exception as e:
                st.error(f"시작 실패: {e}")
    with col2:
        if st.button("⏹️ 중지", use_container_width=True):
            if st.session_state.scheduler:
                st.session_state.scheduler.stop()
                st.info("스케줄러 중지됨")
                st.rerun()

    st.divider()

    # 마지막 실행 정보
    st.subheader("📊 마지막 실행")
    if st.session_state.pipeline_result:
        r = st.session_state.pipeline_result
        st.metric("수집", f"{r.get('collected', 0)}건")
        st.metric("분석", f"{r.get('analyzed', 0)}건")
        st.caption(f"상태: {r.get('status', '미실행')}")
    else:
        st.caption("아직 실행 기록이 없습니다.")

    st.divider()
    st.markdown(
        '<div class="sidebar-info">'
        "💡 <b>설정</b> 페이지에서 검색 키워드를<br>추가·관리할 수 있습니다."
        "</div>",
        unsafe_allow_html=True,
    )


# ── 메인 헤더 ──────────────────────────────────────────

st.markdown(
    '<div class="main-header">'
    "<h1>📰 AI 뉴스 비서</h1>"
    "<p>매일 아침, 당신을 위한 맞춤형 뉴스 브리핑</p>"
    "</div>",
    unsafe_allow_html=True,
)


# ── 수동 새로고침 ─────────────────────────────────────

col_refresh, col_time = st.columns([1, 3])
with col_refresh:
    if st.button("🔄 지금 새로고침", type="primary", use_container_width=True):
        with st.spinner("뉴스를 수집하고 분석 중입니다... (1~3분 소요)"):
            try:
                from scheduler import run_pipeline
                result = run_pipeline()
                st.session_state.pipeline_result = result
                st.session_state.last_refresh = datetime.now()

                if result.get("status") == "완료":
                    st.success(
                        f"✅ 완료! {result.get('collected', 0)}건 수집, "
                        f"{result.get('analyzed', 0)}건 분석"
                    )
                elif result.get("error"):
                    st.error(f"오류: {result['error']}")
                else:
                    st.info(result.get("status", "완료"))
            except Exception as e:
                st.error(f"파이프라인 실행 실패: {e}")

with col_time:
    if st.session_state.last_refresh:
        st.caption(
            f"마지막 새로고침: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}"
        )


# ── 오디오 브리핑 플레이어 ──────────────────────────────

st.markdown("---")
st.subheader("🎙️ 오늘의 브리핑")

try:
    from tts_engine import TTSEngine
    tts = TTSEngine()
    latest_audio = tts.get_latest_audio()

    if latest_audio and latest_audio.exists():
        audio_date = latest_audio.stem.replace("briefing_", "")
        formatted_date = f"{audio_date[:4]}-{audio_date[4:6]}-{audio_date[6:]}"

        st.markdown(
            f'<div class="audio-section">'
            f"<h3>🎧 {formatted_date} 브리핑</h3>"
            f"<p>AI가 큐레이션한 오늘의 핵심 뉴스를 들어보세요</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        with open(latest_audio, "rb") as f:
            st.audio(f.read(), format="audio/mp3")

        # 이전 브리핑 목록
        all_audio = tts.get_audio_list()
        if len(all_audio) > 1:
            with st.expander("📂 이전 브리핑 목록"):
                for audio_file in all_audio[1:5]:  # 최근 5개까지
                    audio_name = audio_file.stem.replace("briefing_", "")
                    with open(audio_file, "rb") as f:
                        st.audio(f.read(), format="audio/mp3")
                    st.caption(f"📅 {audio_name}")
    else:
        st.info(
            "아직 생성된 브리핑이 없습니다. "
            "'지금 새로고침' 버튼을 눌러 첫 브리핑을 생성해 보세요!"
        )
except Exception as e:
    st.warning(f"오디오 로드 실패: {e}")


# ── 통합 뉴스 피드 ──────────────────────────────────────

st.markdown("---")
st.subheader("📰 통합 뉴스 피드")

try:
    from sheets_manager import SheetsManager
    sheets = SheetsManager()
    all_news = sheets.get_recent_news(limit=100)

    if all_news:
        # 필터 컨트롤
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        # 카테고리 목록 추출
        categories = sorted(set(n.get("카테고리", "") for n in all_news if n.get("카테고리")))
        dates = sorted(set(n.get("날짜", "") for n in all_news if n.get("날짜")), reverse=True)

        with filter_col1:
            selected_categories = st.multiselect(
                "카테고리 필터",
                options=categories,
                default=categories,
                key="cat_filter",
            )
        with filter_col2:
            selected_importance = st.multiselect(
                "중요도 필터",
                options=["상", "중", "하"],
                default=["상", "중", "하"],
                key="imp_filter",
            )
        with filter_col3:
            selected_date = st.selectbox(
                "날짜",
                options=["전체"] + dates,
                key="date_filter",
            )

        # 필터 적용
        filtered = [
            n for n in all_news
            if (not selected_categories or n.get("카테고리") in selected_categories)
            and (not selected_importance or n.get("중요도", "중") in selected_importance)
            and (selected_date == "전체" or n.get("날짜") == selected_date)
        ]

        # 통계 카드
        stat1, stat2, stat3, stat4 = st.columns(4)
        with stat1:
            st.metric("📊 전체 뉴스", f"{len(filtered)}건")
        with stat2:
            high_count = sum(1 for n in filtered if n.get("중요도") == "상")
            st.metric("🔴 중요 뉴스", f"{high_count}건")
        with stat3:
            st.metric("📁 카테고리", f"{len(categories)}개")
        with stat4:
            st.metric("📅 수집 일수", f"{len(dates)}일")

        st.markdown("---")

        # 뉴스 카드 렌더링
        for news in filtered:
            importance = news.get("중요도", "중")
            badge = get_importance_badge(importance)
            category = news.get("카테고리", "기타")
            title = news.get("제목", "제목 없음")
            source = news.get("언론사", "알 수 없음")
            summary = news.get("AI 요약", "")
            link = news.get("링크", "")
            date = news.get("날짜", "")

            st.markdown(
                f'<div class="news-card">'
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">'
                f'<span class="category-tag">{category}</span>'
                f"{badge}"
                f"</div>"
                f'<h4 style="margin:0.5rem 0;">{title}</h4>'
                f'<p style="color:#888; font-size:0.85rem; margin:0;">{source} · {date}</p>'
                f'<p style="margin:0.5rem 0; color:#555;">{summary}</p>'
                f"</div>",
                unsafe_allow_html=True,
            )

            # 원문 보기
            col_link, col_body = st.columns([1, 4])
            with col_link:
                if link:
                    st.link_button("🔗 원문 보기", link, use_container_width=True)
            with col_body:
                body = news.get("본문 전문", "")
                if body and body != "(본문 추출 실패)":
                    with st.expander("📄 본문 전체 보기"):
                        st.write(body[:5000])
                        if len(body) > 5000:
                            st.caption("(본문이 길어 일부만 표시)")

            st.markdown("")  # 간격

    else:
        st.info(
            "아직 수집된 뉴스가 없습니다.\n\n"
            "1. ⚙️ **설정** 페이지에서 키워드를 등록하세요\n"
            "2. 🔄 **지금 새로고침** 버튼을 클릭하세요"
        )

except Exception as e:
    st.warning("Google Sheets 연결을 확인해 주세요.")
    st.error(f"오류: {e}")

    # 진단 정보 표시
    with st.expander("🔍 연결 진단 정보"):
        from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_PATH
        import os

        st.write("**GOOGLE_SHEET_ID:**", GOOGLE_SHEET_ID[:10] + "..." if len(GOOGLE_SHEET_ID) > 10 else GOOGLE_SHEET_ID or "❌ 미설정")
        st.write("**GOOGLE_SHEET_ID 길이:**", len(GOOGLE_SHEET_ID))

        # Streamlit secrets 확인
        try:
            has_gcp = "gcp_service_account" in st.secrets
            st.write("**st.secrets[gcp_service_account]:**", "✅ 있음" if has_gcp else "❌ 없음")
            if has_gcp:
                gcp = dict(st.secrets["gcp_service_account"])
                st.write("**client_email:**", gcp.get("client_email", "❌ 없음"))
                st.write("**project_id:**", gcp.get("project_id", "❌ 없음"))
                st.write("**private_key 존재:**", "✅" if gcp.get("private_key") else "❌")
                st.write("**type:**", gcp.get("type", "❌ 없음"))
        except Exception as se:
            st.write(f"**st.secrets 접근 오류:** {se}")

        st.write("**credentials 파일 존재:**", os.path.exists(GOOGLE_CREDENTIALS_PATH))

        st.info(
            "💡 확인사항:\n"
            "1. Google Cloud Console에서 **Google Sheets API**와 **Google Drive API**가 활성화되었는지\n"
            "2. Google Sheet가 서비스 계정 이메일(client_email)에 **편집자**로 공유되었는지\n"
            "3. GOOGLE_SHEET_ID가 URL의 `/d/` 뒤 부분만 입력되었는지"
        )


# ── 푸터 ──────────────────────────────────────────────
st.markdown("---")
st.caption(
    "AI 뉴스 비서 v1.0 | "
    "Powered by 네이버 뉴스 API · Gemini · edge-tts · Streamlit"
)
