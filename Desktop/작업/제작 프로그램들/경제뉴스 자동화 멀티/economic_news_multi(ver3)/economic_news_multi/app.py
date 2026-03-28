import streamlit as st
import os
from db import get_user_by_id, get_settings, save_settings, update_notion_credentials, get_session, cleanup_expired_sessions
from auth import register, login, logout
from security import encrypt_token, decrypt_token, validate_notion_token, validate_notion_db_id
from crawler import NEWS_SOURCES, run_crawler
from scheduler import add_user_jobs, remove_user_jobs

st.set_page_config(
    page_title="📰 경제뉴스 자동화",
    page_icon="📰",
    layout="wide"
)

st.markdown("""
<style>
    .main-title { font-size: 2rem; font-weight: bold; color: #1a1a2e; margin-bottom: 0.5rem; }
    .subtitle { color: #666; margin-bottom: 1.5rem; }
    .keyword-tag {
        background: #e8f4f8; border: 1px solid #b8d9e8;
        border-radius: 20px; padding: 4px 12px; margin: 4px;
        display: inline-block; font-size: 0.9rem;
    }
    .status-box {
        background: #f0f9ff; border-left: 4px solid #0ea5e9;
        padding: 1rem; border-radius: 4px; margin: 1rem 0;
    }
    .mode-box-standard {
        background: #f0fdf4; border: 2px solid #86efac;
        border-radius: 8px; padding: 0.8rem 1rem;
    }
    .mode-box-detailed {
        background: #fdf4ff; border: 2px solid #d8b4fe;
        border-radius: 8px; padding: 0.8rem 1rem;
    }
    .guide-step {
        background: #f8fafc; border-left: 3px solid #0ea5e9;
        padding: 0.8rem 1rem; margin: 0.5rem 0;
        border-radius: 0 6px 6px 0; font-size: 0.92rem;
    }
    .guide-step b { color: #0369a1; }
    .warn-box {
        background: #fffbeb; border: 1px solid #fcd34d;
        border-radius: 8px; padding: 1rem; margin: 1rem 0;
    }
    .success-box {
        background: #f0fdf4; border: 1px solid #86efac;
        border-radius: 8px; padding: 1rem; margin: 1rem 0;
    }
    .lock-box {
        background: #fef2f2; border: 1px solid #fca5a5;
        border-radius: 8px; padding: 1rem; margin: 1rem 0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


# ─── 세션 복원 (DB 기반) ─────────────────────────────────
def restore_session():
    """페이지 새로고침 시 DB 세션으로 로그인 상태 복원"""
    if st.session_state.get("logged_in"):
        return

    session_id = st.session_state.get("session_id")
    if not session_id:
        return

    session = get_session(session_id)
    if session:
        user = get_user_by_id(session["user_id"])
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user_id"]   = user["user_id"]
            st.session_state["email"]     = user["email"]

restore_session()


# ════════════════════════════════════════════════════════
# 로그인 / 회원가입 페이지
# ════════════════════════════════════════════════════════
def show_auth_page():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown('<div style="text-align:center; font-size:2.5rem; margin-top:3rem;">📰</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-title" style="text-align:center;">경제뉴스 자동화</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle" style="text-align:center;">AI가 경제뉴스를 요약해서 Notion에 자동 저장합니다</div>', unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔐 로그인", "✏️ 회원가입"])

        with tab_login:
            with st.form("login_form"):
                email    = st.text_input("이메일", placeholder="example@email.com")
                password = st.text_input("비밀번호", type="password")
                submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")

            if submitted:
                if not email or not password:
                    st.error("이메일과 비밀번호를 입력해주세요.")
                else:
                    ok, result, user = login(email, password)
                    if ok:
                        session_id = result
                        st.session_state["session_id"] = session_id
                        st.session_state["user_id"]    = user["user_id"]
                        st.session_state["email"]      = user["email"]
                        st.session_state["logged_in"]  = True
                        st.rerun()
                    else:
                        st.error(f"❌ {result}")

        with tab_register:
            with st.form("register_form"):
                r_email     = st.text_input("이메일", placeholder="example@email.com", key="r_email")
                r_password  = st.text_input("비밀번호 (8자 이상, 숫자 포함)", type="password", key="r_pw")
                r_password2 = st.text_input("비밀번호 확인", type="password", key="r_pw2")
                r_submitted = st.form_submit_button("회원가입", use_container_width=True, type="primary")

            if r_submitted:
                if r_password != r_password2:
                    st.error("❌ 비밀번호가 일치하지 않습니다.")
                else:
                    ok, result = register(r_email, r_password)
                    if ok:
                        st.success("✅ 회원가입 완료! 로그인 탭에서 로그인해주세요.")
                    else:
                        st.error(f"❌ {result}")


# ════════════════════════════════════════════════════════
# Notion 연결 설정 페이지
# ════════════════════════════════════════════════════════
def show_notion_setup_page(user_id: int, email: str):
    st.markdown('<div class="main-title">📰 경제뉴스 자동화</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Notion 연결이 필요합니다. 아래 가이드를 따라 설정해주세요.</div>', unsafe_allow_html=True)

    col_gap, col_logout = st.columns([5, 1])
    with col_logout:
        if st.button("로그아웃"):
            _do_logout()

    st.divider()
    col1, col2 = st.columns([1.1, 1])

    with col1:
        st.subheader("📋 Notion 연결 가이드")

        st.markdown("#### 1단계. Notion Integration 토큰 발급")
        st.markdown("""
        <div class="guide-step">
            <b>①</b> 아래 링크 접속<br>
            👉 <a href="https://www.notion.so/profile/integrations" target="_blank">
                notion.so/profile/integrations
            </a>
        </div>
        <div class="guide-step">
            <b>②</b> <b>"새 API 통합 만들기"</b> 클릭
        </div>
        <div class="guide-step">
            <b>③</b> 이름 입력 (예: <i>경제뉴스 자동화</i>) → <b>저장</b>
        </div>
        <div class="guide-step">
            <b>④</b> <b>"내부 통합 시크릿"</b> 항목의 토큰 복사<br>
            <small style="color:#666">형식: <code>ntn_xxxxxxxxxxxxxxxxxxxx</code></small>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 2단계. Notion DB 생성 및 Integration 연결")
        st.markdown("""
        <div class="guide-step">
            <b>①</b> Notion에서 새 페이지 생성<br>
            → <b>데이터베이스 &gt; 전체 페이지</b> 선택
        </div>
        <div class="guide-step">
            <b>②</b> DB 페이지 우측 상단 <b>···</b> 클릭 → <b>"연결 추가"</b><br>
            → 방금 만든 Integration 선택하여 연결
        </div>
        <div class="guide-step">
            <b>③</b> DB 페이지 URL을 그대로 복사해서 붙여넣기<br>
            <small style="color:#666">
                예: <code>https://notion.so/workspace/abc123...?v=xyz</code><br>
                URL 전체를 붙여넣으면 ID를 자동으로 추출합니다 ✅
            </small>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="warn-box">
            ⚠️ <b>DB에 아래 속성이 있어야 저장됩니다</b><br>
            <code>이름</code>(제목) · <code>URL</code>(URL) · <code>날짜</code>(날짜) ·
            <code>상태</code>(상태) · <code>요약</code>(텍스트) · <code>시간대</code>(텍스트)
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.subheader("🔑 Notion 연결 정보 입력")

        with st.form("notion_setup_form"):
            notion_token = st.text_input(
                "Notion Integration 토큰",
                placeholder="ntn_xxxxxxxxxxxxxxxxxxxx",
                type="password",
                help="Notion Integration 페이지에서 복사한 시크릿 토큰 (ntn_ 으로 시작)"
            )
            notion_db_raw = st.text_input(
                "Notion DB URL 또는 DB ID",
                placeholder="https://notion.so/workspace/xxxxxxxx... 또는 32자리 ID",
                help="Notion DB 페이지 URL을 그대로 붙여넣거나, 32자리 ID만 입력해도 됩니다"
            )
            submitted = st.form_submit_button("✅ 연결 저장 및 테스트", use_container_width=True, type="primary")

        if submitted:
            from security import extract_notion_db_id
            token = notion_token.strip()

            ok, msg = validate_notion_token(token)
            if not ok:
                st.error(f"❌ {msg}")
            else:
                db_id = extract_notion_db_id(notion_db_raw)
                if not db_id:
                    st.error("❌ DB ID를 찾을 수 없습니다. Notion DB 페이지 URL 또는 32자리 ID를 입력해주세요.")
                else:
                    with st.spinner("Notion 연결 확인 중..."):
                        test_ok = _test_notion_connection(token, db_id)
                    if test_ok:
                        encrypted = encrypt_token(token)
                        update_notion_credentials(user_id, encrypted, db_id)
                        st.markdown('<div class="success-box">✅ Notion 연결 완료!</div>', unsafe_allow_html=True)
                        st.rerun()
                    else:
                        st.error("❌ Notion 연결 실패.\n\n토큰과 DB ID를 확인하고, DB에 Integration이 연결되어 있는지 확인해주세요.")

        st.divider()
        st.markdown("""
        **💡 DB URL 입력 방법**
        
        Notion DB 페이지를 열고 브라우저 주소창의 URL을 **그대로 복사**해서 붙여넣으면 됩니다.
        ```
        https://notion.so/workspace/abc123def456...?v=xyz
        ```
        → DB ID를 자동으로 추출합니다 ✅
        """)


def _test_notion_connection(token: str, db_id: str) -> bool:
    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=token)
        notion.databases.retrieve(database_id=db_id)
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════
# 메인 앱
# ════════════════════════════════════════════════════════
def show_main_app():
    user_id = st.session_state["user_id"]
    email   = st.session_state["email"]

    user_row         = get_user_by_id(user_id)
    notion_token_enc = user_row["notion_token_enc"] if user_row else None
    notion_db_id     = user_row["notion_db_id"] if user_row else None

    # 토큰 복호화
    notion_token = None
    if notion_token_enc:
        try:
            notion_token = decrypt_token(notion_token_enc)
        except Exception:
            st.error("❌ Notion 토큰 복호화 실패. Notion 재설정이 필요합니다.")
            notion_token = None

    config          = get_settings(user_id)
    keywords        = list(config.get("keywords") or [])
    use_filter      = config.get("use_filter", False)
    summary_mode    = config.get("summary_mode", "standard")
    all_source_names = [s["name"] for s in NEWS_SOURCES]
    enabled_sources = list(config.get("enabled_sources") or all_source_names)
    auto_enabled    = config.get("auto_enabled", False)

    def _save(patch: dict):
        merged = {
            "keywords": keywords, "use_filter": use_filter,
            "summary_mode": summary_mode, "enabled_sources": enabled_sources,
            "auto_enabled": auto_enabled,
        }
        merged.update(patch)
        save_settings(user_id, merged)

    # ─── 헤더 ─────────────────────────────────────────────
    col_title, col_user = st.columns([3, 1])
    with col_title:
        st.markdown('<div class="main-title">📰 경제뉴스 자동화 시스템</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">경제뉴스를 AI로 요약해서 Notion에 자동 저장합니다</div>', unsafe_allow_html=True)
    with col_user:
        st.markdown(f"**{email}**")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("⚙️ Notion 재설정"):
                update_notion_credentials(user_id, "", "")
                st.rerun()
        with b2:
            if st.button("로그아웃"):
                _do_logout()

    # ─── 탭 ───────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["⚡ 실행", "🔍 키워드 설정", "📡 소스 설정"])

    # ══════════════════════════════════════════════════════
    # TAB 1: 실행
    # ══════════════════════════════════════════════════════
    with tab1:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📝 요약 모드")
            new_mode = st.radio(
                "요약 방식",
                options=["standard", "detailed"],
                format_func=lambda x: "📄 기본 요약" if x == "standard" else "🔍 상세 분석",
                index=0 if summary_mode == "standard" else 1,
                horizontal=True,
                label_visibility="collapsed"
            )
            if new_mode == "standard":
                st.markdown("""
                <div class="mode-box-standard">
                    <b>📄 기본 요약</b><br>
                    핵심 요약 · 주요 내용 3가지 · 투자 시사점<br>
                    <small style="color:#666">빠르게 훑어보기에 적합</small>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="mode-box-detailed">
                    <b>🔍 상세 분석</b><br>
                    핵심 요약 · 주요 내용 5가지 · 심층 분석 · 시사점 · 관련 기업/섹터<br>
                    <small style="color:#666">깊이 있는 분석이 필요할 때 적합</small>
                </div>
                """, unsafe_allow_html=True)

            if new_mode != summary_mode:
                summary_mode = new_mode
                _save({"summary_mode": summary_mode})
                st.success("✅ 요약 모드 저장됨!")

            st.divider()
            st.subheader("🕐 자동 실행 스케줄")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="status-box">🌅 <b>오전 7:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="status-box">🌆 <b>오후 8:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)

        with col2:
            st.subheader("🤖 자동화 설정")
            auto_toggle = st.toggle("자동화 활성화 (매일 오전 7시 · 오후 8시)", value=auto_enabled)
            if auto_toggle != auto_enabled:
                auto_enabled = auto_toggle
                _save({"auto_enabled": auto_enabled})
                if auto_toggle:
                    add_user_jobs(user_id)
                    st.success("✅ 자동화 활성화됨!")
                else:
                    remove_user_jobs(user_id)
                    st.warning("⏸ 자동화 비활성화됨.")

            st.divider()
            st.subheader("▶ 수동 수집")
            hour_options = {
                "1시간": 1, "3시간": 3, "6시간": 6,
                "12시간": 12, "24시간": 24, "36시간": 36, "48시간": 48
            }
            selected_range = st.select_slider(
                "수집 범위 (현재 시각 기준)",
                options=list(hour_options.keys()),
                value="6시간"
            )
            selected_hours = hour_options[selected_range]

            from datetime import datetime as dt, timedelta as td
            now = dt.now()
            st.caption(f"📅 수집 범위: {(now - td(hours=selected_hours)).strftime('%m/%d %H:%M')} ~ {now.strftime('%m/%d %H:%M')}")

            if st.button("📥 수동 수집 시작", use_container_width=True, type="primary"):
                if not notion_token or not notion_db_id:
                    st.error("❌ Notion 연결이 필요합니다.")
                else:
                    with st.spinner(f"최근 {selected_range} 기사 수집 중..."):
                        current_settings = {
                            "keywords": keywords, "use_filter": use_filter,
                            "summary_mode": summary_mode, "enabled_sources": enabled_sources
                        }
                        saved, skipped = run_crawler(
                            notion_token=notion_token,
                            notion_db_id=notion_db_id,
                            settings=current_settings,
                            time_label="수동",
                            hours=selected_hours,
                        )
                    st.success(f"✅ 완료! {saved}개 저장, {skipped}개 중복 건너뜀")

            st.divider()
            st.subheader("🔌 연결 상태")
            openai_key = os.environ.get("OPENAI_API_KEY")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.success("✅ OpenAI") if openai_key else st.error("❌ OpenAI")
            with c2:
                st.success("✅ Notion") if notion_token else st.error("❌ Notion")
            with c3:
                st.success("✅ DB") if notion_db_id else st.error("❌ DB")

            st.divider()
            st.subheader("📡 현재 활성 소스")
            active   = [s for s in all_source_names if s in enabled_sources]
            inactive = [s for s in all_source_names if s not in enabled_sources]
            st.write(f"✅ 활성: {len(active)}개 — " + ", ".join(active))
            if inactive:
                st.write("⏸ 비활성: " + ", ".join(inactive))

    # ══════════════════════════════════════════════════════
    # TAB 2: 키워드
    # ══════════════════════════════════════════════════════
    with tab2:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("🔍 키워드 필터")
            use_filter_toggle = st.toggle("키워드 필터 사용", value=use_filter)
            if use_filter_toggle:
                st.info("키워드가 포함된 기사만 Notion에 저장됩니다.")
            else:
                st.info("모든 경제 기사를 Notion에 저장합니다.")

            new_keyword = st.text_input("키워드 입력", placeholder="예: AI, 반도체, 2차전지")
            ca, cb = st.columns(2)
            with ca:
                if st.button("➕ 추가", use_container_width=True):
                    kw = new_keyword.strip()
                    if kw and kw not in keywords and len(kw) <= 20:
                        keywords.append(kw)
                        _save({"keywords": keywords, "use_filter": use_filter_toggle})
                        st.success(f"'{kw}' 추가됨!")
                        st.rerun()
            with cb:
                if st.button("🗑️ 전체 삭제", use_container_width=True):
                    keywords = []
                    _save({"keywords": [], "use_filter": use_filter_toggle})
                    st.rerun()

            if use_filter_toggle != use_filter:
                use_filter = use_filter_toggle
                _save({"use_filter": use_filter})

        with col2:
            st.subheader("현재 키워드")
            if keywords:
                for i, kw in enumerate(keywords):
                    ck, cd = st.columns([4, 1])
                    with ck:
                        st.markdown(f'<span class="keyword-tag">#{kw}</span>', unsafe_allow_html=True)
                    with cd:
                        if st.button("✕", key=f"del_{i}"):
                            keywords.pop(i)
                            _save({"keywords": keywords})
                            st.rerun()
            else:
                st.markdown("*키워드 없음*")

            st.write("**추천 키워드**")
            recommended = ["AI", "반도체", "2차전지", "부동산", "환율", "금리", "코스피", "ETF", "삼성전자", "SK하이닉스"]
            cols = st.columns(5)
            for i, kw in enumerate(recommended):
                with cols[i % 5]:
                    if st.button(f"#{kw}", key=f"rec_{kw}", use_container_width=True):
                        if kw not in keywords:
                            keywords.append(kw)
                            _save({"keywords": keywords})
                            st.rerun()

    # ══════════════════════════════════════════════════════
    # TAB 3: 소스 설정
    # ══════════════════════════════════════════════════════
    with tab3:
        st.subheader("📡 뉴스 소스 ON/OFF")
        st.caption("체크된 소스만 크롤링합니다. 변경 후 저장 버튼을 눌러주세요.")

        new_enabled = []
        cols = st.columns(3)
        for i, source in enumerate(NEWS_SOURCES):
            with cols[i % 3]:
                checked = st.checkbox(
                    source["name"],
                    value=(source["name"] in enabled_sources),
                    key=f"src_{source['name']}"
                )
                if checked:
                    new_enabled.append(source["name"])

        st.divider()
        col_save, col_all, col_none = st.columns([2, 1, 1])
        with col_save:
            if st.button("💾 소스 설정 저장", type="primary", use_container_width=True):
                if not new_enabled:
                    st.error("최소 1개 이상의 소스를 선택해야 합니다.")
                else:
                    enabled_sources = new_enabled
                    _save({"enabled_sources": enabled_sources})
                    st.success(f"✅ 저장 완료! 활성 소스: {len(enabled_sources)}개")
                    st.rerun()
        with col_all:
            if st.button("전체 선택", use_container_width=True):
                enabled_sources = all_source_names
                _save({"enabled_sources": enabled_sources})
                st.rerun()
        with col_none:
            if st.button("전체 해제", use_container_width=True):
                st.warning("최소 1개는 선택되어야 합니다.")

    st.divider()
    with st.expander("📖 사용 방법"):
        st.markdown("""
        1. **소스 설정** 탭에서 수집할 신문사 선택
        2. **키워드 설정** 탭에서 관심 키워드 추가 / 필터 ON·OFF
        3. **요약 모드** 선택 — 기본(빠른 훑기) 또는 상세(깊이 있는 분석)
        4. **수동 실행** — 원하는 시간에 직접 크롤링
        5. **자동 실행** — 매일 오전 7시, 오후 8시 자동 저장
        6. **Notion** 에서 저장된 기사 확인
        """)


# ─── 로그아웃 헬퍼 ───────────────────────────────────────
def _do_logout():
    session_id = st.session_state.get("session_id")
    if session_id:
        logout(session_id)
    for k in ["user_id", "email", "logged_in", "session_id"]:
        st.session_state.pop(k, None)
    st.rerun()


# ════════════════════════════════════════════════════════
# 라우팅
# ════════════════════════════════════════════════════════
if not st.session_state.get("logged_in"):
    show_auth_page()
else:
    user_id  = st.session_state["user_id"]
    email    = st.session_state["email"]
    user_row = get_user_by_id(user_id)

    if not user_row or not user_row.get("notion_token_enc") or not user_row.get("notion_db_id"):
        show_notion_setup_page(user_id, email)
    else:
        show_main_app()
