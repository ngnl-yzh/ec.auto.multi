import streamlit as st
import json
import os
import schedule
import threading
import time
from datetime import datetime
from crawler import run_crawler, load_keywords, save_keywords

st.set_page_config(
    page_title="📰 경제뉴스 자동화",
    page_icon="📰",
    layout="wide"
)

# ─── CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 2rem;
        font-weight: bold;
        color: #1a1a2e;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        color: #666;
        margin-bottom: 2rem;
    }
    .keyword-tag {
        background: #e8f4f8;
        border: 1px solid #b8d9e8;
        border-radius: 20px;
        padding: 4px 12px;
        margin: 4px;
        display: inline-block;
        font-size: 0.9rem;
    }
    .status-box {
        background: #f0f9ff;
        border-left: 4px solid #0ea5e9;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ─── 상태 관리 ───────────────────────────────────────────
if "log" not in st.session_state:
    st.session_state.log = []

# ─── 헤더 ───────────────────────────────────────────────
st.markdown('<div class="main-title">📰 경제뉴스 자동화 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">매일경제, 한국경제 뉴스를 AI로 요약해서 Notion에 자동 저장합니다</div>', unsafe_allow_html=True)

# ─── 레이아웃 ────────────────────────────────────────────
col1, col2 = st.columns([1, 1])

# ─── 좌측: 키워드 설정 ──────────────────────────────────
with col1:
    st.subheader("🔍 관심 종목 설정")

    config = load_keywords()
    keywords = config.get("keywords", [])
    use_filter = config.get("use_filter", False)

    # 필터 ON/OFF
    use_filter_toggle = st.toggle("키워드 필터 사용", value=use_filter)

    if use_filter_toggle:
        st.info("키워드가 포함된 기사만 Notion에 저장됩니다.")
    else:
        st.info("모든 경제 기사를 Notion에 저장합니다.")

    # 키워드 추가
    st.write("**관심 키워드 추가**")
    new_keyword = st.text_input("키워드 입력 (예: AI, 반도체, 2차전지)", placeholder="키워드 입력 후 Enter")

    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("➕ 추가", use_container_width=True):
            if new_keyword and new_keyword not in keywords:
                keywords.append(new_keyword.strip())
                save_keywords({"keywords": keywords, "use_filter": use_filter_toggle})
                st.success(f"'{new_keyword}' 추가됨!")
                st.rerun()

    with col_clear:
        if st.button("🗑️ 전체 삭제", use_container_width=True):
            keywords = []
            save_keywords({"keywords": [], "use_filter": use_filter_toggle})
            st.rerun()

    # 현재 키워드 목록
    st.write("**현재 키워드 목록**")
    if keywords:
        for i, kw in enumerate(keywords):
            col_kw, col_del = st.columns([4, 1])
            with col_kw:
                st.markdown(f'<span class="keyword-tag">#{kw}</span>', unsafe_allow_html=True)
            with col_del:
                if st.button("✕", key=f"del_{i}"):
                    keywords.pop(i)
                    save_keywords({"keywords": keywords, "use_filter": use_filter_toggle})
                    st.rerun()
    else:
        st.markdown("*키워드 없음*")

    # 필터 설정 저장
    if use_filter_toggle != use_filter:
        save_keywords({"keywords": keywords, "use_filter": use_filter_toggle})

    # 추천 키워드
    st.write("**추천 키워드**")
    recommended = ["AI", "반도체", "2차전지", "부동산", "환율", "금리", "코스피", "ETF", "삼성전자", "SK하이닉스"]
    cols = st.columns(5)
    for i, kw in enumerate(recommended):
        with cols[i % 5]:
            if st.button(f"#{kw}", key=f"rec_{kw}", use_container_width=True):
                if kw not in keywords:
                    keywords.append(kw)
                    save_keywords({"keywords": keywords, "use_filter": use_filter_toggle})
                    st.rerun()

# ─── 우측: 실행 및 스케줄 ────────────────────────────────
with col2:
    st.subheader("⚡ 실행 설정")

    # 자동 실행 스케줄
    st.write("**자동 실행 스케줄**")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("""
        <div class="status-box">
            🌅 <b>오전 7:00</b><br>
            매일 자동 실행
        </div>
        """, unsafe_allow_html=True)
    with col_s2:
        st.markdown("""
        <div class="status-box">
            🌆 <b>오후 8:00</b><br>
            매일 자동 실행
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # 수동 실행
    st.write("**수동 실행**")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if st.button("🌅 오전 뉴스 가져오기", use_container_width=True, type="primary"):
            with st.spinner("크롤링 중..."):
                run_crawler(time_label="오전")
            st.success("✅ 오전 뉴스 저장 완료!")

    with col_m2:
        if st.button("🌆 오후 뉴스 가져오기", use_container_width=True, type="primary"):
            with st.spinner("크롤링 중..."):
                run_crawler(time_label="오후")
            st.success("✅ 오후 뉴스 저장 완료!")

    st.divider()

    # 환경변수 상태
    st.write("**API 연결 상태**")
    openai_key = os.environ.get("OPENAI_API_KEY")
    notion_token = os.environ.get("NOTION_TOKEN")
    notion_db = os.environ.get("NOTION_DB_ID")

    col_api1, col_api2, col_api3 = st.columns(3)
    with col_api1:
        if openai_key:
            st.success("✅ OpenAI")
        else:
            st.error("❌ OpenAI")
    with col_api2:
        if notion_token:
            st.success("✅ Notion")
        else:
            st.error("❌ Notion")
    with col_api3:
        if notion_db:
            st.success("✅ DB ID")
        else:
            st.error("❌ DB ID")

    if not all([openai_key, notion_token, notion_db]):
        st.warning("⚠️ .env 파일에 API 키를 설정해주세요!")

    st.divider()

    # 뉴스 소스
    st.write("**수집 뉴스 소스**")
    st.markdown("""
    - 📰 매일경제 경제면
    - 📰 한국경제 경제면
    """)

# ─── 하단: 사용 방법 ─────────────────────────────────────
st.divider()
with st.expander("📖 사용 방법"):
    st.markdown("""
    1. **관심 키워드 설정**: 왼쪽에서 관심 종목/키워드 추가
    2. **키워드 필터 ON**: 키워드가 포함된 기사만 저장
    3. **키워드 필터 OFF**: 모든 경제 기사 저장
    4. **수동 실행**: 원하는 시간에 직접 크롤링 실행
    5. **자동 실행**: 매일 오전 7시, 오후 8시 자동 실행
    6. **Notion 확인**: 저장된 기사를 Notion에서 확인
    """)
