import streamlit as st
import os
from datetime import datetime, timedelta

from db import (
    get_user_by_id, get_settings, save_settings,
    update_notion_credentials, get_session,
    get_all_users, update_user_role,
    record_manual_crawl, get_weekly_crawl_count,
    get_admin_config, set_admin_config,
    update_user_custom_limit
)
from auth import register, login, logout
from security import encrypt_token, decrypt_token, validate_notion_token, extract_notion_db_id
from crawler import NEWS_SOURCES, run_crawler
from scheduler import add_user_jobs, remove_user_jobs

# ─── 페이지 설정 ─────────────────────────────────────────
st.set_page_config(page_title="📰 경제뉴스 자동화", page_icon="📰", layout="wide")

st.markdown("""
<style>
    .main-title { font-size: 2rem; font-weight: bold; color: #1a1a2e; margin-bottom: 0.3rem; }
    .subtitle   { color: #666; margin-bottom: 1.5rem; font-size: 0.95rem; }
    .keyword-tag {
        background: #e8f4f8; border: 1px solid #b8d9e8;
        border-radius: 20px; padding: 4px 12px; margin: 3px;
        display: inline-block; font-size: 0.88rem;
    }
    .schedule-box {
        background: #f0f9ff; border-left: 4px solid #0ea5e9;
        padding: 0.8rem 1rem; border-radius: 4px; margin: 0.5rem 0;
    }
    .mode-standard {
        background: #f0fdf4; border: 2px solid #86efac;
        border-radius: 8px; padding: 0.8rem 1rem; margin-top: 0.5rem;
    }
    .mode-detailed {
        background: #fdf4ff; border: 2px solid #d8b4fe;
        border-radius: 8px; padding: 0.8rem 1rem; margin-top: 0.5rem;
    }
    .guide-step {
        background: #f8fafc; border-left: 3px solid #0ea5e9;
        padding: 0.75rem 1rem; margin: 0.4rem 0;
        border-radius: 0 6px 6px 0; font-size: 0.91rem; line-height: 1.6;
    }
    .warn-box {
        background: #fffbeb; border: 1px solid #fcd34d;
        border-radius: 8px; padding: 0.9rem 1rem; margin: 0.8rem 0;
        font-size: 0.9rem;
    }
    .conn-badge {
        display: inline-block; padding: 4px 12px;
        border-radius: 20px; font-size: 0.85rem; font-weight: 600;
        margin: 2px;
    }
    .conn-ok  { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
    .conn-err { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
</style>
""", unsafe_allow_html=True)


# ─── 세션 복원 ───────────────────────────────────────────
def _restore_session():
    if st.session_state.get("logged_in"):
        return
    sid = st.session_state.get("session_id")
    if not sid:
        return
    row = get_session(sid)
    if row:
        user = get_user_by_id(row["user_id"])
        if user:
            st.session_state.update(logged_in=True, user_id=user["user_id"], email=user["email"], role=user.get("role","trial"))

_restore_session()


# ─── 로그아웃 ────────────────────────────────────────────
def _do_logout():
    sid = st.session_state.get("session_id")
    if sid:
        logout(sid)
    for k in ["user_id", "email", "logged_in", "session_id"]:
        st.session_state.pop(k, None)
    st.rerun()


# ════════════════════════════════════════════════════════
# 1. 로그인 / 회원가입
# ════════════════════════════════════════════════════════
def show_auth_page():
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div style="text-align:center;font-size:2.5rem;margin-top:3rem;">📰</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-title" style="text-align:center;">경제뉴스 자동화</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle" style="text-align:center;">AI가 경제뉴스를 요약해서 Notion에 자동 저장합니다</div>', unsafe_allow_html=True)

        t_login, t_reg = st.tabs(["🔐 로그인", "✏️ 회원가입"])

        # 로그인
        with t_login:
            with st.form("login_form"):
                email    = st.text_input("이메일", placeholder="example@email.com")
                password = st.text_input("비밀번호", type="password")
                ok_btn   = st.form_submit_button("로그인", use_container_width=True, type="primary")
            if ok_btn:
                if not email or not password:
                    st.error("이메일과 비밀번호를 입력해주세요.")
                else:
                    ok, result, user = login(email, password)
                    if ok:
                        st.session_state.update(
                            session_id=result,
                            user_id=user["user_id"],
                            email=user["email"],
                            role=user.get("role", "trial"),
                            logged_in=True
                        )
                        st.rerun()
                    else:
                        st.error(f"❌ {result}")

        # 회원가입
        with t_reg:
            with st.form("reg_form"):
                r_email = st.text_input("이메일", placeholder="example@email.com", key="re")
                r_pw    = st.text_input("비밀번호 (8자 이상, 숫자 포함)", type="password", key="rp")
                r_pw2   = st.text_input("비밀번호 확인", type="password", key="rp2")
                reg_btn = st.form_submit_button("회원가입", use_container_width=True, type="primary")
            if reg_btn:
                if r_pw != r_pw2:
                    st.error("❌ 비밀번호가 일치하지 않습니다.")
                else:
                    ok, result = register(r_email, r_pw)
                    if ok:
                        st.success("✅ 회원가입 완료! 로그인 탭에서 로그인해주세요.")
                    else:
                        st.error(f"❌ {result}")


# ════════════════════════════════════════════════════════
# 2. Notion 연결 설정
# ════════════════════════════════════════════════════════
def show_notion_setup_page(user_id: int):
    st.markdown('<div class="main-title">📰 경제뉴스 자동화</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Notion 연결이 필요합니다. 아래 가이드를 따라 설정해주세요.</div>', unsafe_allow_html=True)

    _, col_lo = st.columns([6, 1])
    with col_lo:
        if st.button("로그아웃"):
            _do_logout()

    st.divider()
    col_guide, col_form = st.columns([1.1, 1])

    # 가이드
    with col_guide:
        st.subheader("📋 Notion 연결 가이드")
        st.markdown("#### 1단계. 토큰 발급")
        st.markdown("""
        <div class="guide-step">
            <b>①</b> 아래 링크 접속<br>
            👉 <a href="https://www.notion.so/profile/integrations" target="_blank">notion.so/profile/integrations</a>
        </div>
        <div class="guide-step"><b>②</b> <b>"새 API 통합 만들기"</b> 클릭</div>
        <div class="guide-step"><b>③</b> 이름 입력 (예: 경제뉴스 자동화) → 저장</div>
        <div class="guide-step">
            <b>④</b> <b>"내부 통합 시크릿"</b> 복사<br>
            <small style="color:#888">형식: <code>ntn_xxxxxxxxxxxxxxxxxxxx</code></small>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 2단계. DB 생성 및 연결")
        st.markdown("""
        <div class="guide-step"><b>①</b> Notion 새 페이지 → <b>데이터베이스 &gt; 전체 페이지</b> 생성</div>
        <div class="guide-step">
            <b>②</b> DB 우측 상단 <b>···</b> → <b>"연결 추가"</b> → 방금 만든 Integration 선택
        </div>
        <div class="guide-step">
            <b>③</b> DB 페이지 URL을 그대로 복사해서 붙여넣기<br>
            <small style="color:#888">URL 전체 붙여넣으면 ID 자동 추출 ✅</small>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="warn-box">
            ⚠️ <b>DB 속성 필수 항목</b><br>
            <code>이름</code>(제목) &nbsp;·&nbsp; <code>URL</code>(URL) &nbsp;·&nbsp;
            <code>날짜</code>(날짜) &nbsp;·&nbsp; <code>상태</code>(상태) &nbsp;·&nbsp;
            <code>요약</code>(텍스트) &nbsp;·&nbsp; <code>시간대</code>(텍스트)
        </div>
        """, unsafe_allow_html=True)

    # 입력 폼
    with col_form:
        st.subheader("🔑 연결 정보 입력")
        with st.form("notion_form"):
            token_input = st.text_input(
                "Notion Integration 토큰",
                placeholder="ntn_xxxxxxxxxxxxxxxxxxxx",
                type="password"
            )
            db_input = st.text_input(
                "Notion DB URL 또는 DB ID",
                placeholder="https://notion.so/workspace/xxxxxxxx..."
            )
            save_btn = st.form_submit_button("✅ 연결 저장 및 테스트", use_container_width=True, type="primary")

        if save_btn:
            token = token_input.strip()
            ok, msg = validate_notion_token(token)
            if not ok:
                st.error(f"❌ {msg}")
            else:
                db_id = extract_notion_db_id(db_input)
                if not db_id:
                    st.error("❌ DB ID를 찾을 수 없습니다. URL 또는 32자리 ID를 입력해주세요.")
                else:
                    with st.spinner("Notion 연결 확인 중..."):
                        if _test_notion(token, db_id):
                            update_notion_credentials(user_id, encrypt_token(token), db_id)
                            st.success("✅ Notion 연결 완료!")
                            st.rerun()
                        else:
                            st.error("❌ 연결 실패. 토큰·DB ID 확인, DB에 Integration 연결 여부 확인해주세요.")

        st.divider()
        st.caption("💡 DB URL 예시: `https://notion.so/workspace/abc123...?v=xyz` → URL 그대로 붙여넣기")


def _test_notion(token: str, db_id: str) -> bool:
    try:
        from notion_client import Client as NotionClient
        NotionClient(auth=token).databases.retrieve(database_id=db_id)
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════
# 3. 메인 앱
# ════════════════════════════════════════════════════════
def show_main_app():
    user_id  = st.session_state["user_id"]
    email    = st.session_state["email"]
    user_row = get_user_by_id(user_id)

    # Notion 토큰 복호화
    notion_token, notion_db_id = None, None
    if user_row:
        notion_db_id = user_row.get("notion_db_id")
        enc = user_row.get("notion_token_enc")
        if enc:
            try:
                notion_token = decrypt_token(enc)
            except Exception:
                pass

    # 설정 로드
    cfg             = get_settings(user_id)
    keywords        = list(cfg.get("keywords") or [])
    use_filter      = cfg.get("use_filter", False)
    summary_mode    = cfg.get("summary_mode", "standard")
    all_sources     = [s["name"] for s in NEWS_SOURCES]
    enabled_sources = list(cfg.get("enabled_sources") or all_sources)
    auto_enabled    = cfg.get("auto_enabled", False)

    def _save(patch: dict):
        base = dict(keywords=keywords, use_filter=use_filter,
                    summary_mode=summary_mode, enabled_sources=enabled_sources,
                    auto_enabled=auto_enabled)
        base.update(patch)
        save_settings(user_id, base)

    # ── 헤더 ──────────────────────────────────────────────
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown('<div class="main-title">📰 경제뉴스 자동화 시스템</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">경제뉴스를 AI로 요약해서 Notion에 자동 저장합니다</div>', unsafe_allow_html=True)
    with h2:
        st.markdown(f"**{email}**")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("⚙️ Notion 재설정", use_container_width=True):
                update_notion_credentials(user_id, "", "")
                st.rerun()
        with b2:
            if st.button("로그아웃", use_container_width=True):
                _do_logout()

    tab1, tab2, tab3 = st.tabs(["⚡ 실행", "🔍 키워드 설정", "📡 소스 설정"])

    # ══════════════════════════════════════════════════════
    # TAB 1: 실행
    # ══════════════════════════════════════════════════════
    with tab1:
        left, right = st.columns(2)

        with left:
            # 요약 모드
            st.subheader("📝 요약 모드")
            new_mode = st.radio(
                "요약",
                ["standard", "detailed"],
                format_func=lambda x: "📄 기본 요약" if x == "standard" else "🔍 상세 분석",
                index=0 if summary_mode == "standard" else 1,
                horizontal=True,
                label_visibility="collapsed"
            )
            if new_mode == "standard":
                st.markdown("""<div class="mode-standard">
                    <b>📄 기본 요약</b> — 핵심 요약 · 주요 내용 3가지 · 투자 시사점<br>
                    <small style="color:#666">빠르게 훑어보기에 적합</small>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="mode-detailed">
                    <b>🔍 상세 분석</b> — 핵심 요약 · 주요 내용 5가지 · 심층 분석 · 관련 기업/섹터<br>
                    <small style="color:#666">깊이 있는 분석이 필요할 때</small>
                </div>""", unsafe_allow_html=True)
            if new_mode != summary_mode:
                summary_mode = new_mode
                _save({"summary_mode": summary_mode})
                st.toast("요약 모드 저장됨!")

            st.divider()

            # 자동 스케줄
            st.subheader("🕐 자동 실행 스케줄")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="schedule-box">🌅 <b>오전 7:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="schedule-box">🌆 <b>오후 8:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)

        with right:
            # 자동화 토글
            st.subheader("🤖 자동화 설정")
            _role_auto = st.session_state.get("role", "trial")
            if _role_auto == "trial":
                st.warning("⚠️ 체험(trial) 계정은 자동화를 사용할 수 없습니다.")
            new_auto = st.toggle("자동화 활성화 (매일 오전 7시 · 오후 8시)", value=auto_enabled, disabled=(_role_auto == "trial"))
            if new_auto != auto_enabled:
                auto_enabled = new_auto
                _save({"auto_enabled": auto_enabled})
                if new_auto:
                    add_user_jobs(user_id)
                    st.toast("✅ 자동화 활성화됨!")
                else:
                    remove_user_jobs(user_id)
                    st.toast("⏸ 자동화 비활성화됨.")

            st.divider()

            # 수동 수집
            st.subheader("▶ 수동 수집")
            hour_map = {"1시간":1,"3시간":3,"6시간":6,"12시간":12,"24시간":24,"36시간":36,"48시간":48}
            sel_range = st.select_slider("수집 범위", options=list(hour_map.keys()), value="6시간")
            sel_hours = hour_map[sel_range]
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)
            st.caption(f"📅 {(now - timedelta(hours=sel_hours)).strftime('%m/%d %H:%M')} ~ {now.strftime('%m/%d %H:%M')} (KST)")

            # 권한별 수동 수집 제한 (개별 설정 우선)
            _role = st.session_state.get("role", "trial")
            _user_row = get_user_by_id(user_id)
            _custom_limit = _user_row.get("custom_weekly_limit") if _user_row else None
            if _role == "admin":
                _limit = 99999
            elif _custom_limit is not None:
                _limit = _custom_limit  # 개별 설정값 우선
            elif _role == "trial":
                _limit = int(get_admin_config("trial_weekly_limit") or 15)
            else:
                _limit = int(get_admin_config("free_weekly_limit") or 30)

            _used = get_weekly_crawl_count(user_id)
            _remaining = max(0, _limit - _used)

            if _role != "admin":
                st.caption(f"📊 이번 주 수동 수집: {_used} / {_limit}회 (남은 횟수: {_remaining}회)")

            if st.button("📥 수동 수집 시작", use_container_width=True, type="primary",
                         disabled=(_role in ["trial", "free"] and _remaining <= 0)):
                if not notion_token or not notion_db_id:
                    st.error("❌ Notion 연결이 필요합니다.")
                elif _role in ["trial", "free"] and _remaining <= 0:
                    st.error(f"❌ 이번 주 수동 수집 횟수({_limit}회)를 모두 사용했습니다.")
                else:
                    with st.spinner(f"최근 {sel_range} 기사 수집 중..."):
                        saved, skipped = run_crawler(
                            notion_token=notion_token,
                            notion_db_id=notion_db_id,
                            settings=dict(keywords=keywords, use_filter=use_filter,
                                          summary_mode=summary_mode, enabled_sources=enabled_sources),
                            time_label="수동", hours=sel_hours,
                        )
                    record_manual_crawl(user_id)
                    st.success(f"✅ 완료! {saved}개 저장, {skipped}개 중복 건너뜀")

            st.divider()

            # 연결 상태
            st.subheader("🔌 연결 상태")
            openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
            st.markdown(
                f'<span class="conn-badge {"conn-ok" if openai_ok else "conn-err"}">{"✅" if openai_ok else "❌"} OpenAI</span>'
                f'<span class="conn-badge {"conn-ok" if notion_token else "conn-err"}">{"✅" if notion_token else "❌"} Notion</span>'
                f'<span class="conn-badge {"conn-ok" if notion_db_id else "conn-err"}">{"✅" if notion_db_id else "❌"} DB</span>',
                unsafe_allow_html=True
            )

            st.divider()

            # 활성 소스
            st.subheader("📡 현재 활성 소스")
            active   = [s for s in all_sources if s in enabled_sources]
            inactive = [s for s in all_sources if s not in enabled_sources]
            st.write(f"✅ 활성 {len(active)}개 — " + ", ".join(active))
            if inactive:
                st.write("⏸ 비활성 — " + ", ".join(inactive))

    # ══════════════════════════════════════════════════════
    # TAB 2: 키워드
    # ══════════════════════════════════════════════════════
    with tab2:
        kw_left, kw_right = st.columns(2)

        with kw_left:
            st.subheader("🔍 키워드 필터")
            new_filter = st.toggle("키워드 필터 사용", value=use_filter)
            st.info("키워드가 포함된 기사만 저장됩니다." if new_filter else "모든 경제 기사를 저장합니다.")

            new_kw = st.text_input("키워드 입력", placeholder="예: AI, 반도체, 2차전지")
            a_col, d_col = st.columns(2)
            with a_col:
                if st.button("➕ 추가", use_container_width=True):
                    kw = new_kw.strip()
                    if kw and kw not in keywords and len(kw) <= 20:
                        keywords.append(kw)
                        _save({"keywords": keywords, "use_filter": new_filter})
                        st.rerun()
            with d_col:
                if st.button("🗑️ 전체 삭제", use_container_width=True):
                    keywords = []
                    _save({"keywords": [], "use_filter": new_filter})
                    st.rerun()

            if new_filter != use_filter:
                use_filter = new_filter
                _save({"use_filter": use_filter})

        with kw_right:
            st.subheader("현재 키워드")
            if keywords:
                for i, kw in enumerate(keywords):
                    kc, dc = st.columns([4, 1])
                    with kc:
                        st.markdown(f'<span class="keyword-tag">#{kw}</span>', unsafe_allow_html=True)
                    with dc:
                        if st.button("✕", key=f"del_{i}"):
                            keywords.pop(i)
                            _save({"keywords": keywords})
                            st.rerun()
            else:
                st.caption("키워드 없음")

            st.write("**추천 키워드**")
            recommended = ["AI","반도체","2차전지","부동산","환율","금리","코스피","ETF","삼성전자","SK하이닉스"]
            rc = st.columns(5)
            for i, kw in enumerate(recommended):
                with rc[i % 5]:
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
        st.caption("체크된 소스만 크롤링합니다.")

        new_enabled = []
        sc = st.columns(3)
        for i, src in enumerate(NEWS_SOURCES):
            with sc[i % 3]:
                if st.checkbox(src["name"], value=(src["name"] in enabled_sources), key=f"src_{src['name']}"):
                    new_enabled.append(src["name"])

        st.divider()
        s1, s2, s3 = st.columns([2, 1, 1])
        with s1:
            if st.button("💾 소스 설정 저장", type="primary", use_container_width=True):
                if not new_enabled:
                    st.error("최소 1개 이상 선택해야 합니다.")
                else:
                    enabled_sources = new_enabled
                    _save({"enabled_sources": enabled_sources})
                    st.toast(f"✅ 저장 완료! 활성 {len(enabled_sources)}개")
                    st.rerun()
        with s2:
            if st.button("전체 선택", use_container_width=True):
                _save({"enabled_sources": all_sources})
                st.rerun()
        with s3:
            if st.button("전체 해제", use_container_width=True):
                st.warning("최소 1개는 선택되어야 합니다.")

    st.divider()
    with st.expander("📖 사용 방법"):
        st.markdown("""
        1. **소스 설정** 탭에서 수집할 신문사 선택
        2. **키워드 설정** 탭에서 관심 키워드 추가 / 필터 ON·OFF
        3. **요약 모드** 선택 — 기본(빠른 훑기) 또는 상세(깊이 있는 분석)
        4. **수동 실행** — 원하는 시간 범위로 직접 크롤링
        5. **자동 실행** — 매일 오전 7시, 오후 8시 자동 저장
        6. **Notion** 에서 저장된 기사 확인
        """)


# ════════════════════════════════════════════════════════
# 4. 어드민 패널
# ════════════════════════════════════════════════════════
def show_admin_page():
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # ── 관리자 비밀번호 재확인 (환경변수) ─────────────────
    verified_at = st.session_state.get("admin_verified_at")
    is_verified = False
    if verified_at:
        elapsed = (datetime.now() - verified_at).seconds // 60
        if elapsed < 30:
            is_verified = True
        else:
            st.session_state.pop("admin_verified_at", None)

    if not is_verified:
        st.markdown('<div class="main-title">🛡️ 관리자 인증</div>', unsafe_allow_html=True)
        st.caption("관리자 페이지 접근을 위해 관리자 비밀번호를 입력해주세요.")

        # 어드민 비번 브루트포스 방어
        fail_key = "admin_pw_fails"
        lock_key = "admin_pw_locked_until"
        from datetime import datetime as _dt
        locked_until = st.session_state.get(lock_key)
        if locked_until and _dt.now() < locked_until:
            remaining = int((locked_until - _dt.now()).seconds / 60) + 1
            st.error(f"🔒 관리자 비밀번호 5회 오류. {remaining}분 후 다시 시도해주세요.")
            return

        with st.form("admin_verify_form"):
            admin_pw = st.text_input("관리자 비밀번호", type="password")
            verify_btn = st.form_submit_button("확인", use_container_width=True, type="primary")
        if verify_btn:
            if admin_pw == ADMIN_PASSWORD:
                st.session_state["admin_verified_at"] = datetime.now()
                st.session_state[fail_key] = 0
                st.rerun()
            else:
                fails = st.session_state.get(fail_key, 0) + 1
                st.session_state[fail_key] = fails
                remaining_tries = max(0, 5 - fails)
                if fails >= 5:
                    from datetime import timedelta as _td
                    st.session_state[lock_key] = _dt.now() + _td(minutes=30)
                    st.session_state[fail_key] = 0
                    st.error("🔒 5회 오류. 30분 동안 잠깁니다.")
                else:
                    st.error(f"❌ 비밀번호가 올바르지 않습니다. (남은 시도: {remaining_tries}회)")
        return

    # ── 관리자 패널 본문 ──────────────────────────────────
    col_title, col_lock = st.columns([5, 1])
    with col_title:
        st.markdown('<div class="main-title">🛡️ 관리자 패널</div>', unsafe_allow_html=True)
    with col_lock:
        if st.button("🔒 잠금", use_container_width=True):
            st.session_state.pop("admin_verified_at", None)
            st.rerun()

    st.divider()
    users = get_all_users()

    total     = len(users)
    free      = sum(1 for u in users if u["role"] == "free")
    trial     = sum(1 for u in users if u["role"] == "trial")
    blocked   = sum(1 for u in users if u["role"] == "blocked")
    connected = sum(1 for u in users if u["notion_connected"])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("전체 유저", total)
    c2.metric("무료 이용", free)
    c3.metric("체험 중", trial)
    c4.metric("차단", blocked)
    c5.metric("Notion 연결", connected)

    st.divider()
    st.subheader("👥 유저 목록")

    role_labels  = {"trial": "🟡 체험", "free": "🟢 무료", "blocked": "🔴 차단", "admin": "🛡️ 관리자"}
    role_options = ["trial", "free", "blocked", "admin"]

    for user in users:
        with st.expander(f"{user['email']}  —  {role_labels.get(user['role'], user['role'])}"):
            col1, col2 = st.columns([2, 1])
            with col1:
                from datetime import timezone, timedelta as _td
                KST = timezone(_td(hours=9))
                def _kst(dt):
                    if not dt: return '-'
                    return dt.replace(tzinfo=timezone.utc).astimezone(KST).strftime('%Y-%m-%d %H:%M')
                st.write(f"**가입일:** {_kst(user['created_at'])}")
                st.write(f"**마지막 로그인:** {_kst(user['last_login'])}")
                st.write(f"**Notion 연결:** {'✅' if user['notion_connected'] else '❌'}")
                # 이번 주 수집 횟수
                weekly = get_weekly_crawl_count(user["user_id"])
                st.write(f"**이번 주 수동 수집:** {weekly}회")
            with col2:
                current_idx = role_options.index(user["role"]) if user["role"] in role_options else 0
                new_role = st.selectbox(
                    "권한 변경",
                    options=role_options,
                    index=current_idx,
                    format_func=lambda x: role_labels.get(x, x),
                    key=f"role_{user['user_id']}"
                )
                if st.button("저장", key=f"save_{user['user_id']}"):
                    update_user_role(user["user_id"], new_role)
                    st.toast(f"✅ {user['email']} → {role_labels[new_role]}")
                    st.rerun()

                # 개별 수집 횟수 제한
                cur_custom = user.get("custom_weekly_limit")
                custom_input = st.number_input(
                    "개별 주간 한도 (비워두면 권한 기본값)",
                    min_value=0, max_value=500,
                    value=cur_custom if cur_custom is not None else 0,
                    key=f"custom_{user['user_id']}"
                )
                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    if st.button("한도 저장", key=f"climit_{user['user_id']}"):
                        update_user_custom_limit(user["user_id"], custom_input if custom_input > 0 else None)
                        st.toast(f"✅ 개별 한도 저장!")
                        st.rerun()
                with c_col2:
                    if st.button("기본값으로", key=f"creset_{user['user_id']}"):
                        update_user_custom_limit(user["user_id"], None)
                        st.toast("✅ 기본값으로 초기화!")
                        st.rerun()

    # ── 제한 횟수 설정 ────────────────────────────────────
    st.divider()
    st.subheader("⚙️ 권한별 수동 수집 제한 설정")
    cur_trial = int(get_admin_config("trial_weekly_limit") or 15)
    cur_free  = int(get_admin_config("free_weekly_limit") or 30)

    s1, s2 = st.columns(2)
    with s1:
        new_trial_limit = st.number_input("체험(trial) 주간 수집 한도", min_value=1, max_value=100, value=cur_trial)
    with s2:
        new_free_limit = st.number_input("무료(free) 주간 수집 한도", min_value=1, max_value=200, value=cur_free)

    if st.button("💾 제한 설정 저장", type="primary"):
        set_admin_config("trial_weekly_limit", str(new_trial_limit))
        set_admin_config("free_weekly_limit", str(new_free_limit))
        st.toast("✅ 제한 횟수 저장 완료!")
        st.rerun()


# ════════════════════════════════════════════════════════
# 라우팅
# ════════════════════════════════════════════════════════
if not st.session_state.get("logged_in"):
    show_auth_page()
else:
    _uid  = st.session_state["user_id"]
    _row  = get_user_by_id(_uid)
    _role = _row.get("role", "trial") if _row else "trial"

    # 차단된 유저 강제 로그아웃
    if _role == "blocked":
        st.error("❌ 이용이 제한된 계정입니다. 관리자에게 문의해주세요.")
        _do_logout()
        st.stop()

    # 관리자면 어드민 페이지
    if _role == "admin":
        tab_main, tab_admin = st.tabs(["📰 메인", "🛡️ 관리자"])
        with tab_main:
            _has_notion = _row and _row.get("notion_token_enc") and _row.get("notion_db_id")
            if not _has_notion:
                show_notion_setup_page(_uid)
            else:
                show_main_app()
        with tab_admin:
            show_admin_page()
    else:
        _has_notion = _row and _row.get("notion_token_enc") and _row.get("notion_db_id")
        if not _has_notion:
            show_notion_setup_page(_uid)
        else:
            show_main_app()
