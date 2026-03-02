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

# ── 커스텀 CSS (Light Admin Table Dashboard) ────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&display=swap');
    
    :root {
        --bg-color: #f4f6f8;
        --card-bg: #ffffff;
        --text-main: #1e293b;
        --text-muted: #64748b;
        --primary: #0f172a;
        --border-color: #e2e8f0;
        --accent-blue: #2563eb;
    }

    /* 전체 폰트 및 라이트 테마 배경 */
    html, body, [class*="css"], .stApp {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
        background-color: var(--bg-color) !important;
        color: var(--text-main) !important;
        font-size: 13px !important; /* 어드민용 콤팩트 폰트 */
    }

    #MainMenu, header, footer, .stDeployButton {visibility: hidden !important; display: none !important;}
    
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 1600px !important; /* 넓은 테이블을 위해 가로폭 확장 */
    }

    /* 사이드바 라이트화 */
    [data-testid="stSidebar"] > div:first-child {
        background-color: var(--card-bg) !important;
        border-right: 1px solid var(--border-color);
        padding-top: 1rem;
    }
    
    /* 카드 컴포넌트 공통 (화이트, 옅은 보더, 그림자 억제) */
    .admin-card {
        background: var(--card-bg);
        border-radius: 6px;
        border: 1px solid var(--border-color);
        padding: 1rem;
        margin-bottom: 1rem;
    }

    /* 통계 카드 (가로 배열) */
    .stat-container {
        display: flex;
        gap: 1rem;
        margin-bottom: 1rem;
    }
    .stat-card {
        flex: 1;
        background: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 0.8rem 1rem;
        display: flex;
        flex-direction: column;
    }
    .stat-number {
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--primary);
    }
    .stat-label {
        color: var(--text-muted);
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* 테이블 헤더 스타일 */
    .table-header {
        display: flex;
        padding: 0.6rem 0.5rem;
        border-bottom: 2px solid var(--border-color);
        color: var(--text-muted);
        font-weight: 700;
        font-size: 0.8rem;
        margin-bottom: 0.2rem;
    }
    
    /* 뉴스 테이블 Row (가로형 리스트) */
    .news-row {
        display: flex;
        align-items: flex-start;
        padding: 0.8rem 0.5rem;
        border-bottom: 1px solid var(--border-color);
        background: var(--card-bg);
    }
    .news-row:hover {
        background-color: #f8fafc;
    }
    
    /* 뉴스 테이블 각 영역 폭 */
    .col-meta { width: 10%; flex-shrink: 0; padding-right: 0.5rem; }
    .col-title { width: 35%; flex-shrink: 0; padding-right: 1rem; }
    .col-desc { width: 40%; flex-shrink: 0; padding-right: 1rem; }
    .col-action { width: 15%; flex-shrink: 0; display:flex; gap:0.3rem; justify-content:flex-end;}

    /* 텍스트 요소 */
    .row-title {
        font-size: 1rem;
        font-weight: 600;
        color: var(--primary);
        margin: 0 0 0.2rem 0;
        line-height: 1.3;
    }
    .row-desc {
        font-size: 0.85rem;
        color: var(--text-muted);
        margin: 0;
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .row-info {
        font-size: 0.75rem;
        color: var(--text-muted);
    }

    /* 뱃지 포인트 (원색 억제, 파스텔/연한 톤) */
    .badge {
        display: inline-block;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.65rem;
        font-weight: 600;
        margin-bottom: 0.2rem;
    }
    .badge-high { background: #fee2e2; color: #b91c1c; }
    .badge-mid { background: #fef3c7; color: #b45309; }
    .badge-low { background: #e0f2fe; color: #0369a1; }
    .badge-cat { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

    /* Streamlit 기본 버튼 초소형(테이블용) */
    .stButton > button {
        background-color: #ffffff !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 4px !important;
        font-weight: 500 !important;
        padding: 0.2rem 0.6rem !important;
        font-size: 0.75rem !important;
        min-height: 0 !important;
    }
    .stButton > button:hover {
        background-color: #f1f5f9 !important;
        color: #000 !important;
    }

    /* 새로고침 등 주요 버튼 (파란색 포인트) */
    .btn-primary > button {
        background-color: var(--accent-blue) !important;
        color: #ffffff !important;
        border: none !important;
    }
    .btn-primary > button:hover {
        background-color: #1d4ed8 !important;
    }

    /* expander 스타일 (AI 요약 / 본문 보기 영역) */
    .streamlit-expanderHeader {
        font-size: 0.8rem !important;
        padding: 0.2rem 0.5rem !important;
        color: var(--accent-blue) !important;
    }
    
    @media (max-width: 768px) {
        .news-row { flex-direction: column; }
        .col-meta, .col-title, .col-desc, .col-action { width: 100%; padding-right:0; margin-bottom:0.5rem; }
        .col-action { justify-content: flex-start; }
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


# ── 메인 타이틀 및 새로고침 (한 줄 배치) ───────────────────
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.markdown(
        '<div class="main-header" style="border:none; margin-bottom:0; padding-bottom:0.5rem;">'
        "<h1>📰 상담 관리자<span style='color:var(--accent-blue);'>.</span></h1>"
        "<p>소상공인 종합지원 AI 뉴스 데이터 관리</p>"
        "</div>",
        unsafe_allow_html=True,
    )
with col_btn:
    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)
    if st.button("🔄 새로고침", type="primary", use_container_width=True):
        with st.spinner("수집 중..."):
            try:
                from scheduler import run_pipeline
                result = run_pipeline()
                st.session_state.pipeline_result = result
                st.session_state.last_refresh = datetime.now()
                if result.get("status") == "완료":
                    st.success("수집 완료")
                else:
                    st.error("수집 오류")
            except Exception as e:
                st.error(f"실패: {e}")

st.markdown("<hr style='margin-top:0; border-color:var(--border-color);'>", unsafe_allow_html=True)

# ── 오디오 브리핑 플레이어 (초경량 Expand) ────────────────────────
try:
    from tts_engine import TTSEngine
    tts = TTSEngine()
    latest_audio = tts.get_latest_audio()

    if latest_audio and latest_audio.exists():
        with st.expander("🎧 오늘의 AI 뉴스 브리핑 듣기 (클릭하여 펼치기)", expanded=False):
            audio_date = latest_audio.stem.replace("briefing_", "")
            st.caption(f"{audio_date} 자동 생성됨")
            with open(latest_audio, "rb") as f:
                st.audio(f.read(), format="audio/mp3")
except Exception as e:
    pass

# ── 통합 뉴스 데이터 테이블 (어드민 뷰) ────────────────────────────
try:
    from sheets_manager import SheetsManager
    sheets = SheetsManager()
    all_news = sheets.get_recent_news(limit=100)

    if all_news:
        # 필터 컨트롤 영역
        st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
        fcol1, fcol2, fcol3 = st.columns([1, 1, 1])
        
        categories = sorted(set(n.get("카테고리", "") for n in all_news if n.get("카테고리")))
        
        with fcol1:
             selected_categories = st.multiselect("분류 필터", options=categories, default=categories)
        with fcol2:
             selected_importance = st.multiselect("중요도 필터", options=["상", "중", "하"], default=["상", "중", "하"])
        with fcol3:
             # 달력(Date Input) 기반 날짜 필터. 기본값 오늘.
             import datetime as dt
             selected_date_val = st.date_input("기준 일자 선택", dt.datetime.today())
             selected_date = selected_date_val.strftime("%Y-%m-%d")

        # 필터 적용
        filtered = [
            n for n in all_news
            if (not selected_categories or n.get("카테고리") in selected_categories)
            and (not selected_importance or n.get("중요도", "중") in selected_importance)
            and (selected_date == "전체" or n.get("날짜") == selected_date)
        ]

        # 요약 통계(Minimal)
        st.markdown(f"""
        <div class="stat-container">
            <div class="stat-card">
                <div class="stat-label">조회된 기사</div>
                <div class="stat-number">{len(filtered)}<span style="font-size:0.8rem; font-weight:400; color:var(--text-muted);"> 건</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">핵심 중요도(상)</div>
                <div class="stat-number" style="color:#2563eb;">{sum(1 for n in filtered if n.get("중요도") == "상")}<span style="font-size:0.8rem; font-weight:400; color:var(--text-muted);"> 건</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">수집 카테고리 종류</div>
                <div class="stat-number">{len(categories)}<span style="font-size:0.8rem; font-weight:400; color:var(--text-muted);"> 개</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<h4 style='font-size:1rem; margin-top:2rem; margin-bottom:0.5rem;'>수집 목록</h4>", unsafe_allow_html=True)

        # 테이블 헤더 (columns 활용, 1:4:4:1 비율의 표 구성)
        c_h1, c_h2, c_h3, c_h4 = st.columns([1.2, 3.8, 5, 1.5])
        c_h1.markdown("<div class='table-header'>상태/분류</div>", unsafe_allow_html=True)
        c_h2.markdown("<div class='table-header'>기사 제목 및 출처</div>", unsafe_allow_html=True)
        c_h3.markdown("<div class='table-header'>네이버 자동 요약</div>", unsafe_allow_html=True)
        c_h4.markdown("<div class='table-header' style='text-align:right;'>관리 액션</div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:0; padding:0; border-color:var(--border-color);'>", unsafe_allow_html=True)

        # 뉴스 루프 
        for news in filtered:
            importance = news.get("중요도", "중")
            badge_class = "badge-mid"
            if importance == "상": badge_class = "badge-high"
            elif importance == "하": badge_class = "badge-low"
            
            category = news.get("카테고리", "기타")
            title = news.get("제목", "제목 없음")
            source = news.get("언론사", "")
            date = news.get("날짜", "")
            naver_desc = news.get("네이버 요약", "요약 정보 없음")
            summary = news.get("AI 요약", "대기 중")
            body = news.get("본문 전문", "")
            link = news.get("링크", "")

            # 행(row) 구조
            col1, col2, col3, col4 = st.columns([1.2, 3.8, 5, 1.5])
            
            with col1:
                st.markdown(f'<div style="padding-top:0.8rem;"><span class="badge {badge_class}">{importance}</span><br><span class="badge badge-cat">{category}</span></div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div style="padding-top:0.8rem;"><p class="row-title">{title}</p><p class="row-info">{source} | {date}</p></div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div style="padding-top:0.8rem;"><p class="row-desc">{naver_desc}</p></div>', unsafe_allow_html=True)
            with col4:
                st.markdown('<div style="padding-top:0.8rem; display:flex; flex-direction:column; gap:0.2rem; align-items:flex-end;">', unsafe_allow_html=True)
                if link:
                    st.link_button("↗ 원문", link)
                with st.popover("자세히 보기"):
                    st.markdown("**💡 AI 요약 브리핑**")
                    st.info(summary)
                    st.markdown("**📄 기사 전문 (발췌)**")
                    st.caption(body[:1500] + "..." if len(body) > 1500 else body)
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("<hr style='margin:0; padding:0; border-color:#e2e8f0;'>", unsafe_allow_html=True)

        if not filtered:
            st.info("해당 일자 및 조건에 맞는 뉴스가 없습니다.")

    else:
        st.info("수집된 뉴스가 없습니다. ⚙️ 새로고침을 진행해주세요.")

except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
