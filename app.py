import streamlit as st
import os
from datetime import datetime, timedelta

from db import (
    get_user_by_id, get_settings, save_settings,
    update_notion_credentials, get_session, extend_session,
    get_all_users, update_user_role,
    record_manual_crawl, get_weekly_crawl_count,
    record_briefing, get_weekly_briefing_count,
    get_admin_config, set_admin_config,
    update_user_custom_limit, update_user_custom_briefing_limit
)
from auth import register, login, logout
from security import encrypt_token, decrypt_token, validate_notion_token, extract_notion_db_id
from crawler import NEWS_SOURCES, run_crawler
from scheduler import add_user_jobs, remove_user_jobs, sync_all_user_jobs

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
        border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin: 2px;
    }
    .conn-ok  { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
    .conn-err { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
    .limit-info { background: #f0f9ff; border-radius: 6px; padding: 6px 10px; font-size: 0.85rem; color: #0369a1; margin: 4px 0; }
</style>
""", unsafe_allow_html=True)


# ─── 세션 복원 + 갱신 ────────────────────────────────────
def _restore_session():
    if st.session_state.get("logged_in"):
        # 활동 시 세션 1시간 연장
        sid = st.session_state.get("session_id")
        if sid:
            extend_session(sid, hours=1)
        return
    sid = st.session_state.get("session_id")
    if not sid:
        return
    row = get_session(sid)
    if row:
        user = get_user_by_id(row["user_id"])
        if user:
            st.session_state.update(
                logged_in=True, user_id=user["user_id"],
                email=user["email"], role=user.get("role", "trial")
            )
            extend_session(sid, hours=1)

_restore_session()


# ─── 로그아웃 ────────────────────────────────────────────
def _do_logout():
    sid = st.session_state.get("session_id")
    if sid:
        logout(sid)
    for k in ["user_id", "email", "logged_in", "session_id", "role"]:
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
                    st.error("❌ DB ID를 찾을 수 없습니다.")
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

    notion_token, notion_db_id = None, None
    if user_row:
        notion_db_id = user_row.get("notion_db_id")
        enc = user_row.get("notion_token_enc")
        if enc:
            try:
                notion_token = decrypt_token(enc)
            except Exception:
                pass

    cfg              = get_settings(user_id)
    keywords         = list(cfg.get("keywords") or [])
    use_filter       = cfg.get("use_filter", False)
    summary_mode     = cfg.get("summary_mode", "standard")
    all_sources      = [s["name"] for s in NEWS_SOURCES]
    enabled_sources  = list(cfg.get("enabled_sources") or all_sources)
    auto_enabled     = cfg.get("auto_enabled", False)
    custom_schedules = list(cfg.get("custom_schedules") or [])

    def _save(patch: dict):
        base = dict(keywords=keywords, use_filter=use_filter,
                    summary_mode=summary_mode, enabled_sources=enabled_sources,
                    auto_enabled=auto_enabled, custom_schedules=custom_schedules)
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
                st.session_state["confirm_notion_reset"] = True
        with b2:
            if st.button("로그아웃", use_container_width=True):
                _do_logout()

    # Notion 재설정 확인 팝업
    if st.session_state.get("confirm_notion_reset"):
        st.warning("⚠️ Notion 연결을 해제하시겠습니까? 다시 설정해야 합니다.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("✅ 확인", use_container_width=True, type="primary"):
                update_notion_credentials(user_id, "", "")
                st.session_state.pop("confirm_notion_reset", None)
                st.rerun()
        with cc2:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.pop("confirm_notion_reset", None)
                st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["⚡ 실행", "🔍 키워드 설정", "📡 소스 설정", "📋 브리핑"])

    # ══════════════════════════════════════════════════════
    # TAB 1: 실행
    # ══════════════════════════════════════════════════════
    with tab1:
        left, right = st.columns(2)

        with left:
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
            st.subheader("🕐 자동 실행 스케줄")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="schedule-box">🌅 <b>오전 7:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="schedule-box">🌆 <b>오후 8:00 KST</b><br>매일 자동 실행</div>', unsafe_allow_html=True)

        with right:
            st.subheader("🤖 자동화 설정")
            _role_auto = st.session_state.get("role", "trial")
            if _role_auto == "trial":
                st.warning("⚠️ 체험(trial) 계정은 자동화를 사용할 수 없습니다.")
            new_auto = st.toggle("자동화 활성화 (매일 오전 7시 · 오후 8시)", value=auto_enabled, disabled=(_role_auto == "trial"))
            if new_auto != auto_enabled:
                auto_enabled = new_auto
                _save({"auto_enabled": auto_enabled})
                if new_auto:
                    add_user_jobs(user_id, custom_schedules=custom_schedules)
                    st.toast("✅ 자동화 활성화됨!")
                else:
                    remove_user_jobs(user_id)
                    st.toast("⏸ 자동화 비활성화됨.")

            # 커스텀 스케줄 설정
            if _role_auto != "trial":
                with st.expander("⏰ 자동 수집 시간 추가 설정"):
                    st.caption("기본: 오전 7시, 오후 8시 (고정) · 추가 시간을 설정하세요 (최대 24시간 이내)")
                    
                    # 현재 커스텀 스케줄 표시
                    if custom_schedules:
                        st.write("**현재 추가 스케줄:**")
                        for i, sch in enumerate(custom_schedules):
                            sc1, sc2 = st.columns([3, 1])
                            with sc1:
                                r = sch.get("range_hours", 5)
                                st.write(f"🕐 {sch['hour']:02d}:{sch['minute']:02d} KST — 최근 {r}시간 수집")
                            with sc2:
                                if st.button("삭제", key=f"del_sch_{i}"):
                                    custom_schedules.pop(i)
                                    _save({"custom_schedules": custom_schedules})
                                    if auto_enabled:
                                        add_user_jobs(user_id, custom_schedules=custom_schedules)
                                    st.rerun()

                    # 새 스케줄 추가
                    if len(custom_schedules) < 5:
                        with st.form("add_schedule_form"):
                            nc1, nc2, nc3, nc4 = st.columns([2, 2, 2, 1])
                            with nc1:
                                new_hour = st.number_input("실행 시 (0~23)", min_value=0, max_value=23, value=12, key="new_sch_h")
                            with nc2:
                                new_min = st.number_input("실행 분 (0~59)", min_value=0, max_value=59, value=0, key="new_sch_m")
                            with nc3:
                                new_range = st.number_input("수집 범위 (시간)", min_value=1, max_value=24, value=5, key="new_sch_r",
                                                            help="실행 시각 기준 몇 시간 전부터 수집할지 설정")
                            with nc4:
                                st.write("")
                                st.write("")
                                add_btn = st.form_submit_button("➕", use_container_width=True)
                            if add_btn:
                                is_default = (new_hour == 7 and new_min == 0) or (new_hour == 20 and new_min == 0)
                                is_dup = any(s["hour"] == new_hour and s["minute"] == new_min for s in custom_schedules)
                                if is_default:
                                    st.error("기본 스케줄과 중복됩니다.")
                                elif is_dup:
                                    st.error("이미 추가된 시간입니다.")
                                else:
                                    custom_schedules.append({"hour": new_hour, "minute": new_min, "range_hours": new_range})
                                    _save({"custom_schedules": custom_schedules})
                                    if auto_enabled:
                                        add_user_jobs(user_id, custom_schedules=custom_schedules)
                                    st.toast(f"✅ {new_hour:02d}:{new_min:02d} (최근 {new_range}시간) 스케줄 추가!")
                                    st.rerun()
                    else:
                        st.caption("최대 5개까지 추가 가능합니다.")

            st.divider()
            st.subheader("▶ 수동 수집")
            hour_map = {"1시간":1,"3시간":3,"6시간":6,"12시간":12,"24시간":24,"36시간":36,"48시간":48}
            sel_range = st.select_slider("수집 범위", options=list(hour_map.keys()), value="6시간")
            sel_hours = hour_map[sel_range]
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)
            st.caption(f"📅 {(now - timedelta(hours=sel_hours)).strftime('%m/%d %H:%M')} ~ {now.strftime('%m/%d %H:%M')} (KST)")

            _role = st.session_state.get("role", "trial")
            _user_row = get_user_by_id(user_id)
            _custom_limit = _user_row.get("custom_weekly_limit") if _user_row else None
            if _role == "admin":
                _limit = 99999
            elif _custom_limit is not None:
                _limit = _custom_limit
            elif _role == "trial":
                _limit = int(get_admin_config("trial_weekly_limit") or 15)
            else:
                _limit = int(get_admin_config("free_weekly_limit") or 30)

            _used = get_weekly_crawl_count(user_id)
            _remaining = max(0, _limit - _used)

            if _role != "admin":
                st.markdown(f'<div class="limit-info">📊 이번 주 수동 수집: <b>{_used} / {_limit}회</b> (남은 횟수: <b>{_remaining}회</b>)</div>', unsafe_allow_html=True)

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
            st.subheader("🔌 연결 상태")
            openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
            st.markdown(
                f'<span class="conn-badge {"conn-ok" if openai_ok else "conn-err"}">{"✅" if openai_ok else "❌"} OpenAI</span>'
                f'<span class="conn-badge {"conn-ok" if notion_token else "conn-err"}">{"✅" if notion_token else "❌"} Notion</span>'
                f'<span class="conn-badge {"conn-ok" if notion_db_id else "conn-err"}">{"✅" if notion_db_id else "❌"} DB</span>',
                unsafe_allow_html=True
            )

            st.divider()
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
                        st.toast(f"✅ '{kw}' 키워드 추가됨!")
                        st.rerun()
            with d_col:
                if st.button("🗑️ 전체 삭제", use_container_width=True):
                    keywords = []
                    _save({"keywords": [], "use_filter": new_filter})
                    st.toast("🗑️ 키워드 전체 삭제됨.")
                    st.rerun()

            if new_filter != use_filter:
                use_filter = new_filter
                _save({"use_filter": use_filter})
                st.toast(f"{'✅ 키워드 필터 활성화!' if use_filter else '⏸ 키워드 필터 비활성화'}")

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
                    st.toast(f"✅ 소스 설정 저장 완료! 활성 {len(enabled_sources)}개")
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
        7. **브리핑** 탭에서 그룹별 한눈에 요약 확인
        """)

    # ══════════════════════════════════════════════════════
    # TAB 4: 브리핑
    # ══════════════════════════════════════════════════════
    with tab4:
        st.subheader("📋 오늘의 브리핑")
        st.caption("Notion에 저장된 기사들을 카테고리별로 묶어 한눈에 요약합니다.")

        if not notion_token or not notion_db_id:
            st.error("❌ Notion 연결이 필요합니다.")
        else:
            # 브리핑 횟수 제한
            _b_role = st.session_state.get("role", "trial")
            _b_user_row = get_user_by_id(user_id)
            _b_custom = _b_user_row.get("custom_briefing_limit") if _b_user_row else None
            if _b_role == "admin":
                _b_limit = 99999
            elif _b_custom is not None:
                _b_limit = _b_custom
            elif _b_role == "trial":
                _b_limit = int(get_admin_config("trial_briefing_limit") or 5)
            else:
                _b_limit = int(get_admin_config("free_briefing_limit") or 10)

            _b_used = get_weekly_briefing_count(user_id)
            _b_remaining = max(0, _b_limit - _b_used)

            if _b_role != "admin":
                st.markdown(f'<div class="limit-info">📊 이번 주 브리핑: <b>{_b_used} / {_b_limit}회</b> (남은 횟수: <b>{_b_remaining}회</b>)</div>', unsafe_allow_html=True)

            # 브리핑 모드 선택
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                briefing_mode = st.radio(
                    "브리핑 모드",
                    ["standard", "detailed"],
                    format_func=lambda x: "📄 기본 브리핑" if x == "standard" else "🔍 상세 브리핑",
                    horizontal=True,
                    label_visibility="collapsed"
                )
            if briefing_mode == "standard":
                st.caption("📄 기본 브리핑 — 카테고리별 핵심 1줄 요약 + 오늘의 핵심 메시지")
            else:
                st.caption("🔍 상세 브리핑 — 카테고리별 심층 분석 + 투자 시사점 + 리스크 요인")

            with st.spinner("Notion에서 데이터 불러오는 중..."):
                groups = _get_notion_groups(notion_token, notion_db_id)

            if not groups:
                st.info("저장된 기사가 없습니다.")
            else:
                selected_group = st.selectbox("브리핑할 그룹 선택", options=groups, index=0)

                if st.button("📋 브리핑 생성", type="primary", use_container_width=True,
                             disabled=(_b_role in ["trial", "free"] and _b_remaining <= 0)):
                    if _b_role in ["trial", "free"] and _b_remaining <= 0:
                        st.error(f"❌ 이번 주 브리핑 횟수({_b_limit}회)를 모두 사용했습니다.")
                    else:
                        with st.spinner("기사를 분석하고 브리핑을 생성 중입니다..."):
                            articles = _get_articles_by_group(notion_token, notion_db_id, selected_group)
                            if not articles:
                                st.warning("해당 그룹에 기사가 없습니다.")
                            else:
                                briefing = _generate_briefing(articles, mode=briefing_mode)
                                saved = _save_briefing_to_notion(
                                    notion_token, notion_db_id,
                                    selected_group, briefing, len(articles)
                                )
                                record_briefing(user_id)
                                st.session_state["briefing_result"] = briefing
                                st.session_state["briefing_group"] = selected_group
                                if saved:
                                    st.toast("✅ 브리핑이 Notion에 저장됐습니다!")

            if st.session_state.get("briefing_result"):
                st.divider()
                st.markdown(f"### 📰 {st.session_state.get('briefing_group', '')} 브리핑")
                st.markdown(st.session_state["briefing_result"])


# ════════════════════════════════════════════════════════
# 브리핑 헬퍼 함수
# ════════════════════════════════════════════════════════
def _get_notion_groups(notion_token: str, notion_db_id: str) -> list:
    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=notion_token)
        results = notion.databases.query(
            database_id=notion_db_id,
            filter={
                "and": [
                    {"property": "날짜", "date": {"on_or_after": (datetime.now() - timedelta(days=7)).date().isoformat()}},
                    {"or": [
                        {"property": "유형", "select": {"equals": "기사"}},
                        {"property": "유형", "select": {"is_empty": True}},
                    ]}
                ]
            },
            page_size=100
        )
        groups, seen = [], set()
        for page in results.get("results", []):
            slot = page.get("properties", {}).get("시간대", {})
            slot_text = slot["rich_text"][0]["text"]["content"] if slot.get("rich_text") else ""
            if slot_text and slot_text not in seen:
                seen.add(slot_text)
                groups.append(slot_text)
        groups.sort(reverse=True)
        return groups
    except Exception as e:
        print(f"Notion 그룹 조회 실패: {e}")
        return []


def _get_articles_by_group(notion_token: str, notion_db_id: str, group: str) -> list:
    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=notion_token)
        results = notion.databases.query(
            database_id=notion_db_id,
            filter={
                "and": [
                    {"property": "시간대", "rich_text": {"equals": group}},
                    {"or": [
                        {"property": "유형", "select": {"equals": "기사"}},
                        {"property": "유형", "select": {"is_empty": True}},
                    ]}
                ]
            },
            page_size=50
        )
        articles = []
        for page in results.get("results", []):
            props = page.get("properties", {})
            title = props["이름"]["title"][0]["text"]["content"] if props.get("이름", {}).get("title") else ""
            summary = props["요약"]["rich_text"][0]["text"]["content"] if props.get("요약", {}).get("rich_text") else ""
            url = props.get("URL", {}).get("url", "")
            if title and summary and summary != "요약 실패":
                articles.append({"title": title, "summary": summary, "url": url})
        return articles
    except Exception as e:
        print(f"Notion 기사 조회 실패: {e}")
        return []


def _generate_briefing(articles: list, mode: str = "standard") -> str:
    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), http_client=httpx.Client())

        articles_text = "\n\n".join([
            f"[기사 {i+1}] {a['title']}\n요약: {a['summary']}"
            for i, a in enumerate(articles)
        ])

        if mode == "detailed":
            system_prompt = """당신은 경제 뉴스 전문 분석가입니다. 기사들을 카테고리별로 묶어 상세하게 분석해주세요.

형식:
## 🏷️ [카테고리명]
- **핵심 내용**: 1~2줄 요약
- **세부 분석**: 배경, 원인, 영향 설명
- **투자 시사점**: 단기/중기 관점
- **리스크**: 주의할 점

---
📌 **오늘의 핵심 메시지**
전체를 관통하는 3~4줄 핵심 요약 및 투자 관점"""
        else:
            system_prompt = """당신은 경제 뉴스 브리퍼입니다. 카테고리별로 묶어 간결하게 브리핑해주세요.

형식:
## 🏷️ [카테고리명]
- 핵심 내용 1줄 요약
- 핵심 내용 1줄 요약

---
📌 **오늘의 핵심 메시지**
전체를 관통하는 2~3줄 핵심 요약"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음 {len(articles)}개 기사를 브리핑해주세요:\n\n{articles_text}"}
            ],
            max_tokens=2500 if mode == "detailed" else 2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"브리핑 생성 실패: {e}"


def _save_briefing_to_notion(notion_token: str, notion_db_id: str, group: str, briefing: str, article_count: int) -> bool:
    try:
        from notion_client import Client as NotionClient
        from datetime import date
        notion = NotionClient(auth=notion_token)
        title = f"📋 브리핑 | {group} ({article_count}개 기사)"
        base_props = {
            "이름":  {"title": [{"text": {"content": title}}]},
            "날짜":  {"date": {"start": date.today().isoformat()}},
            "시간대": {"rich_text": [{"text": {"content": f"📋브리핑 | {group}"}}]},
            "요약":  {"rich_text": [{"text": {"content": briefing[:1990]}}]},
            "유형":  {"select": {"name": "브리핑"}},
        }
        try:
            notion.pages.create(
                parent={"database_id": notion_db_id},
                properties={**base_props, "상태": {"status": {"name": "읽기 전"}}}
            )
        except Exception:
            notion.pages.create(parent={"database_id": notion_db_id}, properties=base_props)
        return True
    except Exception as e:
        print(f"❌ 브리핑 Notion 저장 실패: {e}")
        return False


# ════════════════════════════════════════════════════════
# 4. 어드민 패널
# ════════════════════════════════════════════════════════
def show_admin_page():
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

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
                weekly_crawl = get_weekly_crawl_count(user["user_id"])
                weekly_brief = get_weekly_briefing_count(user["user_id"])
                st.write(f"**이번 주 수동 수집:** {weekly_crawl}회")
                st.write(f"**이번 주 브리핑:** {weekly_brief}회")
            with col2:
                current_idx = role_options.index(user["role"]) if user["role"] in role_options else 0
                new_role = st.selectbox(
                    "권한 변경", options=role_options, index=current_idx,
                    format_func=lambda x: role_labels.get(x, x),
                    key=f"role_{user['user_id']}"
                )
                if st.button("저장", key=f"save_{user['user_id']}"):
                    update_user_role(user["user_id"], new_role)
                    st.toast(f"✅ {user['email']} → {role_labels[new_role]}")
                    st.rerun()

                # 수동 수집 개별 한도
                cur_custom = user.get("custom_weekly_limit")
                custom_input = st.number_input(
                    "수동 수집 개별 한도 (0=기본값)",
                    min_value=0, max_value=500,
                    value=cur_custom if cur_custom is not None else 0,
                    key=f"custom_{user['user_id']}"
                )
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("수집 저장", key=f"climit_{user['user_id']}"):
                        update_user_custom_limit(user["user_id"], custom_input if custom_input > 0 else None)
                        st.toast("✅ 수집 한도 저장!")
                        st.rerun()
                with cc2:
                    if st.button("수집 기본값", key=f"creset_{user['user_id']}"):
                        update_user_custom_limit(user["user_id"], None)
                        st.toast("✅ 기본값 초기화!")
                        st.rerun()

                # 브리핑 개별 한도
                cur_b_custom = user.get("custom_briefing_limit")
                briefing_input = st.number_input(
                    "브리핑 개별 한도 (0=기본값)",
                    min_value=0, max_value=100,
                    value=cur_b_custom if cur_b_custom is not None else 0,
                    key=f"blimit_{user['user_id']}"
                )
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("브리핑 저장", key=f"bsave_{user['user_id']}"):
                        update_user_custom_briefing_limit(user["user_id"], briefing_input if briefing_input > 0 else None)
                        st.toast("✅ 브리핑 한도 저장!")
                        st.rerun()
                with bc2:
                    if st.button("브리핑 기본값", key=f"breset_{user['user_id']}"):
                        update_user_custom_briefing_limit(user["user_id"], None)
                        st.toast("✅ 기본값 초기화!")
                        st.rerun()

    # ── 권한별 제한 설정 ──────────────────────────────────
    st.divider()
    st.subheader("⚙️ 권한별 제한 설정")

    cur_trial  = int(get_admin_config("trial_weekly_limit") or 15)
    cur_free   = int(get_admin_config("free_weekly_limit") or 30)
    cur_trial_b = int(get_admin_config("trial_briefing_limit") or 5)
    cur_free_b  = int(get_admin_config("free_briefing_limit") or 10)

    st.markdown("**수동 수집 주간 한도**")
    s1, s2 = st.columns(2)
    with s1:
        new_trial_limit = st.number_input("체험(trial)", min_value=1, max_value=100, value=cur_trial, key="tl")
    with s2:
        new_free_limit = st.number_input("무료(free)", min_value=1, max_value=200, value=cur_free, key="fl")

    st.markdown("**브리핑 주간 한도**")
    b1, b2 = st.columns(2)
    with b1:
        new_trial_b = st.number_input("체험(trial)", min_value=1, max_value=50, value=cur_trial_b, key="tb")
    with b2:
        new_free_b = st.number_input("무료(free)", min_value=1, max_value=100, value=cur_free_b, key="fb")

    if st.button("💾 제한 설정 저장", type="primary"):
        set_admin_config("trial_weekly_limit", str(new_trial_limit))
        set_admin_config("free_weekly_limit", str(new_free_limit))
        set_admin_config("trial_briefing_limit", str(new_trial_b))
        set_admin_config("free_briefing_limit", str(new_free_b))
        st.toast("✅ 제한 설정 저장 완료!")
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

    if _role == "blocked":
        st.error("❌ 이용이 제한된 계정입니다. 관리자에게 문의해주세요.")
        _do_logout()
        st.stop()

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
