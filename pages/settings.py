"""
pages/settings.py - 키워드·카테고리 설정 페이지 (Streamlit)

기능:
  - 카테고리 + 키워드 추가/삭제/활성화 토글
  - 현재 설정 테이블 편집 (st.data_editor)
  - TTS 음성 선택
  - 변경사항 Google Sheets Settings 탭에 즉시 반영
"""

import streamlit as st
import pandas as pd

# ── 페이지 설정 ────────────────────────────────────────
st.set_page_config(
    page_title="설정 - AI 뉴스 비서",
    page_icon="⚙️",
    layout="wide",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }
    .settings-header {
        background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
        padding: 2rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(108, 92, 231, 0.3);
    }
    .settings-header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .settings-header p { margin: 0.5rem 0 0 0; opacity: 0.85; }
    .info-box {
        background: #f8f9fa;
        border-left: 4px solid #6c5ce7;
        padding: 1rem 1.5rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ── 헤더 ──────────────────────────────────────────────

st.markdown(
    '<div class="settings-header">'
    "<h1>⚙️ 설정</h1>"
    "<p>검색 키워드와 카테고리를 관리합니다</p>"
    "</div>",
    unsafe_allow_html=True,
)


# ── Google Sheets 연결 ────────────────────────────────

try:
    from sheets_manager import SheetsManager
    sheets = SheetsManager()
    connected = True
except Exception as e:
    st.error(
        f"Google Sheets 연결 실패: {e}\n\n"
        "`.env` 파일과 `credentials/service_account.json`을 확인해 주세요."
    )
    connected = False


if connected:

    # ── 현재 설정 편집 ──────────────────────────────────

    st.subheader("📋 키워드 관리")

    st.markdown(
        '<div class="info-box">'
        "💡 아래 테이블에서 직접 수정하고 <b>변경사항 저장</b>을 눌러주세요. "
        "활성화를 <code>FALSE</code>로 바꾸면 해당 키워드는 수집에서 제외됩니다."
        "</div>",
        unsafe_allow_html=True,
    )

    # 설정 로드
    settings = sheets.get_settings()

    if settings:
        df = pd.DataFrame(settings)

        # 활성화 열을 bool로 변환
        if "활성화" in df.columns:
            df["활성화"] = df["활성화"].apply(
                lambda x: str(x).upper() == "TRUE"
            )

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "카테고리": st.column_config.TextColumn(
                    "카테고리",
                    help="뉴스 분류 카테고리 (예: 상권, 소상공인, 국내뉴스)",
                    width="medium",
                ),
                "키워드": st.column_config.TextColumn(
                    "키워드",
                    help="네이버 뉴스 검색 키워드",
                    width="large",
                ),
                "활성화": st.column_config.CheckboxColumn(
                    "활성화",
                    help="체크 해제 시 수집에서 제외",
                    default=True,
                ),
            },
            key="settings_editor",
        )

        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            try:
                # bool → TRUE/FALSE 문자열 변환
                save_data = []
                for _, row in edited_df.iterrows():
                    cat = str(row.get("카테고리", "")).strip()
                    kw = str(row.get("키워드", "")).strip()
                    active = "TRUE" if row.get("활성화", True) else "FALSE"
                    if cat and kw:
                        save_data.append({
                            "카테고리": cat,
                            "키워드": kw,
                            "활성화": active,
                        })

                sheets.update_settings(save_data)
                st.success(f"✅ {len(save_data)}개 키워드 설정이 저장되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"저장 실패: {e}")
    else:
        st.info("등록된 키워드가 없습니다. 아래에서 새 키워드를 추가하세요.")

    # ── 키워드 빠른 추가 ───────────────────────────────

    st.markdown("---")
    st.subheader("➕ 키워드 빠른 추가")

    with st.form("add_keyword_form"):
        form_col1, form_col2 = st.columns(2)
        with form_col1:
            new_category = st.text_input(
                "카테고리",
                placeholder="예: 상권, 소상공인, 국내뉴스 ...",
            )
        with form_col2:
            new_keyword = st.text_input(
                "키워드",
                placeholder="예: 용산구 골목상권",
            )

        submitted = st.form_submit_button(
            "추가", type="primary", use_container_width=True,
        )

        if submitted:
            if new_category and new_keyword:
                try:
                    sheets.add_setting(new_category, new_keyword);
                    st.success(
                        f"✅ [{new_category}] '{new_keyword}' 키워드가 추가되었습니다!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"추가 실패: {e}")
            else:
                st.warning("카테고리와 키워드를 모두 입력해 주세요.")

    # ── 추천 키워드 ────────────────────────────────────

    st.markdown("---")
    st.subheader("💡 추천 키워드 예시")

    suggestions = {
        "상권": ["용산구 골목상권", "상권분석", "유동인구 분석", "소비트렌드"],
        "소상공인": ["자영업자 지원금", "소상공인 정책", "창업 지원", "소상공인 대출"],
        "국내뉴스": ["경제 동향", "부동산 시장", "고용 시장", "물가 동향"],
        "국제뉴스": ["미국 경제", "환율 전망", "글로벌 무역", "국제 유가"],
        "기술": ["인공지능 AI", "디지털 전환", "핀테크", "클라우드"],
    }

    for cat, keywords in suggestions.items():
        with st.expander(f"📁 {cat}"):
            cols = st.columns(2)
            for idx, kw in enumerate(keywords):
                with cols[idx % 2]:
                    if st.button(
                        f"➕ {kw}",
                        key=f"sug_{cat}_{kw}",
                        use_container_width=True,
                    ):
                        try:
                            sheets.add_setting(cat, kw)
                            st.success(f"✅ [{cat}] '{kw}' 추가 완료!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"추가 실패: {e}")

    # ── TTS 설정 ───────────────────────────────────────

    st.markdown("---")
    st.subheader("🎙️ 음성 설정")

    voice_options = {
        "ko-KR-SunHiNeural": "🙋‍♀️ 선희 (여성, 자연스러운 톤)",
        "ko-KR-InJoonNeural": "🙋‍♂️ 인준 (남성, 차분한 톤)",
    }

    current_voice = st.session_state.get("tts_voice", "ko-KR-SunHiNeural")
    selected_voice = st.radio(
        "브리핑 음성을 선택하세요",
        options=list(voice_options.keys()),
        format_func=lambda x: voice_options[x],
        index=0 if current_voice == "ko-KR-SunHiNeural" else 1,
    )

    if selected_voice != current_voice:
        st.session_state.tts_voice = selected_voice
        st.info(
            f"음성이 **{voice_options[selected_voice]}**로 변경되었습니다. "
            "다음 브리핑 생성 시 적용됩니다."
        )

# ── 푸터 ──────────────────────────────────────────────
st.markdown("---")
st.caption("AI 뉴스 비서 v1.0 | ⚙️ 설정 페이지")
