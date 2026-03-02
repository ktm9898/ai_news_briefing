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
    page_title="AI 기사 브리핑",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed", # 모바일에선 기본으로 닫기
)

# ── 커스텀 CSS (Ultra Compact Admin Dashboard) ────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&display=swap');
    
    :root {
        --bg-color: #0c0c0c;
        --card-bg: #161618;
        --text-main: #fcfcfc;
        --text-muted: #8b8f97;
        --accent: #e2e2e2;
        --primary: #ffffff;
        --border-color: #2a2c30;
    }

    /* 전체 폰트 및 다크 테마 배경 */
    html, body, [class*="css"], .stApp {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
        background-color: var(--bg-color) !important;
        color: var(--text-main) !important;
        font-size: 14px !important; /* 전체 폰트 사이즈 대폭 축소 */
    }

    /* Streamlit 기본 요소 숨기기 (헤더바, 푸터 등) */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden !important; display: none !important;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* 전체 패딩 극소화 */
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 1400px !important; /* 폭을 넓혀 더 많은 정보를 밀집 */
    }

    /* 사이드바 다크화 및 패딩 축소 */
    [data-testid="stSidebar"] > div:first-child {
        background-color: var(--card-bg) !important;
        border-right: 1px solid var(--border-color);
        padding-top: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    
    /* 메인 타이틀 영역 (매우 작게) */
    .main-header {
        padding: 1rem 0 1rem 0;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
        margin-bottom: 1rem;
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.2;
        color: var(--text-main);
    }
    .main-header p {
        margin: 0.3rem 0 0 0;
        font-size: 0.9rem;
        font-weight: 400;
        color: var(--text-muted);
    }

    /* 통계 카드 (Minimal Grid & Compact) */
    .stat-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.5rem;
        margin-bottom: 1.5rem;
    }
    .stat-card {
        background: transparent;
        border-radius: 0;
        padding: 0.5rem 0;
        text-align: left;
        border-top: 1px solid var(--border-color);
    }
    .stat-number {
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--primary);
    }
    .stat-label {
        color: var(--text-muted);
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        margin-top: 0.1rem;
    }

    /* 오디오 플레이어 (Soft Rectangle & Compact) */
    .audio-section {
        background: var(--card-bg);
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1.5rem;
        border: 1px solid var(--border-color);
    }
    .audio-section h3 {
        color: var(--primary) !important;
        margin: 0 0 0.3rem 0 !important;
        font-size: 1rem;
        font-weight: 700;
    }

    /* 뉴스 피드 카드 (Compact List View) */
    .news-card {
        background: var(--card-bg);
        border-radius: 6px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
        border: 1px solid var(--border-color);
        transition: border-color 0.1s;
    }
    .news-card:hover {
        border-color: #555555;
    }
    
    /* 뉴스 제목 & 메타 (Compact) */
    .news-card h3 {
        margin: 0 0 0.2rem 0;
        font-size: 1.05rem;
        font-weight: 600;
        line-height: 1.3;
        color: var(--primary);
    }
    
    .news-desc {
        font-size: 0.85rem;
        color: #aaaaaa;
        margin: 0 0 0.4rem 0;
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2; /* 2줄까지만 표시 */
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .news-meta {
        color: var(--text-muted);
        font-size: 0.75rem;
        margin-bottom: 0.6rem;
        font-weight: 400;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* 본문 요약 박스 (Compact) */
    .summary-box {
        background: rgba(255, 255, 255, 0.03);
        padding: 0.6rem 0.8rem;
        border-radius: 4px;
        border-left: 2px solid #444;
    }
    .summary-box p {
        margin: 0;
        color: #d1d5db;
        line-height: 1.5;
        font-size: 0.85rem;
        font-weight: 300;
    }

    /* 태그 및 배지 (Muted Colors & Small) */
    .category-tag {
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-main);
        padding: 0.1rem 0.4rem;
        border-radius: 4px;
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-high { color: #f87171; font-weight: 600; font-size: 0.65rem; }
    .badge-mid { color: #fbbf24; font-weight: 600; font-size: 0.65rem; }
    .badge-low { color: #60a5fa; font-weight: 600; font-size: 0.65rem; }

    /* Streamlit 기본 버튼 커스텀 (Tiny) */
    .stButton > button {
        background-color: var(--primary) !important;
        color: var(--bg-color) !important;
        border: none !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        padding: 0.3rem 0.8rem !important;
        font-size: 0.85rem !important;
    }
    .stButton > button:hover {
        background-color: #e5e5e5 !important;
        opacity: 0.9;
    }

    /* 모바일 초밀착 최적화 */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.4rem !important;
            padding-right: 0.4rem !important;
        }
        
        /* 모바일에선 스택형 2x2 유지하되 간격 극소화 */
        .stat-container {
            gap: 0.3rem;
            margin-bottom: 1rem;
        }
        .stat-card {
            border-left: 1px solid var(--border-color);
            padding: 0 0 0 0.5rem;
        }
        .stat-number { font-size: 1.2rem; }
        
        .news-card {
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.4rem;
        }
        .news-card h3 {
            font-size: 0.95rem;
        }
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
    "<h1>AI 뉴스 비서<span style='color:var(--primary);'>.</span></h1>"
    "<p>간결하고 강력한 모닝 인텔리전스</p>"
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

        # 통계 카드 (Minimal Grid)
        st.write("") # 간격
        st.markdown('<div class="stat-container">', unsafe_allow_html=True)
        stat1, stat2, stat3, stat4 = st.columns(4)
        with stat1:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{len(filtered)}</div><div class="stat-label">Total News</div></div>', unsafe_allow_html=True)
        with stat2:
            high_count = sum(1 for n in filtered if n.get("중요도") == "상")
            st.markdown(f'<div class="stat-card"><div class="stat-number" style="color:#f87171;">{high_count}</div><div class="stat-label">High Priority</div></div>', unsafe_allow_html=True)
        with stat3:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{len(categories)}</div><div class="stat-label">Categories</div></div>', unsafe_allow_html=True)
        with stat4:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{len(dates)}</div><div class="stat-label">Days Collected</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 뉴스 카드 렌더링 (Dark Minimal)
        for news in filtered:
            importance = news.get("중요도", "중")
            # 중요도 텍스트 스타일
            if importance == "상":
                badge_html = '<span class="badge-high">🔴 HIGH</span>'
            elif importance == "중":
                badge_html = '<span class="badge-mid">🟡 MID</span>'
            else:
                badge_html = '<span class="badge-low">🔵 LOW</span>'
                
            category = news.get("카테고리", "기타")
            title = news.get("제목", "제목 없음")
            source = news.get("언론사", "알 수 없음")
            naver_desc = news.get("네이버 요약", "")
            summary = news.get("AI 요약", "")
            link = news.get("링크", "")
            date = news.get("날짜", "")

            # 네이버 요약이 있으면 표시, 없으면 무시
            naver_desc_html = f'<div class="news-desc">{naver_desc}</div>' if naver_desc else ''

            st.markdown(
                f'<div class="news-card">'
                f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem;">'
                f'<span class="category-tag">{category}</span>'
                f'{badge_html}'
                f'</div>'
                f'<h3>{title}</h3>'
                f'{naver_desc_html}'
                f'<div class="news-meta">'
                f'<span>{source}</span>'
                f'<span style="opacity:0.5;">|</span>'
                f'<span>{date}</span>'
                f'</div>'
                f'<div class="summary-box">'
                f'<p>{summary}</p>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # 원문 보기 (Streamlit Link Button 활용하되 여백 최소화)
            col_link, col_body = st.columns([1, 4])
            with col_link:
                if link:
                    st.link_button("↗ 원문 보기", link, use_container_width=True)
            with col_body:
                body = news.get("본문 전문", "")
                if body and body != "(본문 추출 실패)":
                    with st.expander("본문 전체 보기 (Expand)"):
                        st.write(body[:5000])
                        if len(body) > 5000:
                            st.caption("(본문이 길어 일부만 표시)")

            st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)  # 뉴스 간 간격

    else:
        st.info(
            "아직 수집된 뉴스가 없습니다.\n\n"
            "1. 사이드바 설정 영역에서 키워드를 확인하세요.\n"
            "2. 상단의 '지금 새로고침' 버튼을 클릭하세요."
        )

except Exception as e:
    st.warning("Google Sheets 연결을 확인해 주세요.")
    st.error(f"오류: {e}")

    # 진단 정보 표시 (개발자 도구 숨김 처리 등으로 깔끔하게 보일 수 있으나 일단 유지)
    with st.expander("System Diagnostic Info"):
        from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_PATH
        import os

        st.write("**GOOGLE_SHEET_ID:**", GOOGLE_SHEET_ID[:10] + "..." if len(GOOGLE_SHEET_ID) > 10 else GOOGLE_SHEET_ID or "❌ 미설정")
        
        try:
            has_gcp = "gcp_service_account" in st.secrets
            st.write("**st.secrets[gcp_service_account]:**", "✅ 있음" if has_gcp else "❌ 없음")
        except Exception as se:
            st.write(f"**st.secrets 접근 오류:** {se}")

        st.write("**credentials 파일 존재:**", os.path.exists(GOOGLE_CREDENTIALS_PATH))


# ── 푸터 (Streamlit 푸터가 아닌 커스텀 최소화 푸터) ────────────────
st.markdown("<br><hr style='border-color:var(--border-color); opacity:0.3;'><div style='text-align:center; color:var(--text-muted); font-size:0.8rem; padding:1rem 0;'>AI News Intelligence Dashboard V2 <br>Powered by Gemini & Streamlit</div>", unsafe_allow_html=True)
