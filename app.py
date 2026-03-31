import streamlit as st
import os
from datetime import datetime, timedelta

from db import (
    get_user_by_id, get_settings, save_settings,
    unlock_account,
    update_notion_credentials, get_session,
    get_all_users, update_user_role,
    record_manual_crawl, get_weekly_crawl_count,
    record_detail_crawl, get_weekly_detail_count,
    record_briefing, get_weekly_briefing_count,
    get_admin_config, set_admin_config,
    update_user_custom_limit, update_user_custom_briefing_limit,
    update_user_custom_detail_limit,
    add_user_bonus, reset_user_bonus
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
    .limit-info { background: #f0f9ff; border-radius: 6px; padding: 6px 10px;
                  font-size: 0.85rem; color: #0369a1; margin: 4px 0; }
    .info-box { background: #f0f9ff; border: 1px solid #bae6fd;
                border-radius: 6px; padding: 8px 12px; font-size: 0.85rem; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)


# ─── 세션 복원 (쿠키 없음 - 수정7) ──────────────────────
def _restore_session():
    if st.session_state.get("logged_in"):
        return
    sid = st.session_state.get("session_id")
    if not sid:
        return
    row = get_session(sid)
    if row:
        user = get_user_by_id(row["user_id"])
        if user and user.get("role") != "blocked":
            st.session_state.update(
                logged_in=True, user_id=user["user_id"],
                email=user["email"], role=user.get("role", "trial"),
                session_id=sid
            )

_restore_session()


# ─── 로그아웃 ────────────────────────────────────────────
def _do_logout():
    sid = st.session_state.get("session_id")
    if sid:
        logout(sid)
    for k in ["user_id", "email", "logged_in", "session_id", "role"]:
        st.session_state.pop(k, None)
    st.rerun()


# ─── 한도 계산 헬퍼 ──────────────────────────────────────
def _get_limit(role, user_row, config_key_trial, config_key_free, custom_col):
    if role == "admin":
        return 99999
    custom = user_row.get(custom_col) if user_row else None
    if custom is not None:
        return custom
    if role == "trial":
        return int(get_admin_config(config_key_trial) or 0)
    return int(get_admin_config(config_key_free) or 0)


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
            <code>이름</code>(제목) · <code>URL</code>(URL) · <code>날짜</code>(날짜) ·
            <code>상태</code>(상태) · <code>요약</code>(텍스트) · <code>시간대</code>(텍스트)
        </div>
        """, unsafe_allow_html=True)

    with col_form:
        st.subheader("🔑 연결 정보 입력")
        with st.form("notion_form"):
            token_input = st.text_input("Notion Integration 토큰", placeholder="ntn_xxxxxxxxxxxxxxxxxxxx", type="password")
            db_input    = st.text_input("Notion DB URL 또는 DB ID", placeholder="https://notion.so/workspace/xxxxxxxx...")
            save_btn    = st.form_submit_button("✅ 연결 저장 및 테스트", use_container_width=True, type="primary")

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
                            # DB 속성 자동 추가
                            with st.spinner("DB 속성 자동 설정 중..."):
                                added, skipped, errors = _setup_notion_db(token, db_id)
                            st.session_state["notion_setup_done"] = True
                            st.session_state["notion_setup_added"] = added
                            st.session_state["notion_setup_skipped"] = skipped
                            st.rerun()
                        else:
                            st.error("❌ 연결 실패. 토큰·DB ID 확인, DB에 Integration 연결 여부 확인해주세요.")

        # 연결 완료 후 가이드 표시
        if st.session_state.get("notion_setup_done"):
            added   = st.session_state.get("notion_setup_added", [])
            skipped = st.session_state.get("notion_setup_skipped", [])
            st.success("✅ Notion 연결 및 DB 설정 완료!")
            if added:
                st.info(f"📝 자동 추가된 속성: {', '.join(added)}")
            if skipped:
                st.caption(f"이미 있는 속성 (건너뜀): {', '.join(skipped)}")

            st.markdown("""
            ---
            ### 📋 뷰(View) 설정 가이드
            속성은 자동으로 추가됐어요! 이제 Notion에서 뷰 4개만 직접 만들어주세요.

            **뷰 만드는 방법:** DB 상단 `표 ∨` → `새 보기` → `표` 선택 → 이름 입력

            ---
            #### 1️⃣ 자동수집 뷰
            - 이름: `자동 수집`
            - **필터:** `유형` = `기사` + `시간대` **포함하지 않음** `수동`
            - **그룹화:** `시간대` / 정렬: 알파벳 역순 / 빈 그룹 숨기기 ON

            #### 2️⃣ 수동수집 뷰
            - 이름: `수동 수집`
            - **필터:** `유형` = `기사` + `시간대` **포함** `수동`
            - **그룹화:** `시간대` / 정렬: 알파벳 역순 / 빈 그룹 숨기기 ON

            #### 3️⃣ 브리핑 뷰
            - 이름: `브리핑`
            - **필터:** `유형` = `브리핑`
            - 그룹화 없음

            #### 4️⃣ 전체 뷰
            - 이름: `전체`
            - 필터 없음, 정렬: `날짜` 내림차순

            ---
            **그룹화 설정 방법:**
            필터 아이콘(≡) → 그룹화 → 그룹화 기준: `시간대` → 정렬: `알파벳 역순` → 빈 그룹 숨기기 ON

            > 💡 뷰 설정이 완료되면 아래 버튼을 눌러 시작하세요!
            """)

            if st.button("🚀 시작하기", type="primary", use_container_width=True):
                for k in ["notion_setup_done", "notion_setup_added", "notion_setup_skipped"]:
                    st.session_state.pop(k, None)
                st.rerun()

        st.divider()
        st.caption("💡 DB URL 예시: `https://notion.so/workspace/abc123...?v=xyz` → URL 그대로 붙여넣기")


def _test_notion(token: str, db_id: str) -> bool:
    try:
        from notion_client import Client as NotionClient
        NotionClient(auth=token).databases.retrieve(database_id=db_id)
        return True
    except Exception:
        return False


def _setup_notion_db(token: str, db_id: str) -> tuple:
    """
    Notion DB에 필수 속성 자동 추가.
    반환: (추가된 속성 목록, 건너뜀 목록, 오류 목록)
    """
    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=token)

        # 현재 DB 속성 조회
        db_info = notion.databases.retrieve(database_id=db_id)
        existing = set(db_info.get("properties", {}).keys())

        # 필요한 속성 정의
        props_to_add = {}

        if "상태" not in existing:
            props_to_add["상태"] = {
                "status": {
                    "options": [
                        {"name": "읽기 전", "color": "red"},
                        {"name": "읽는 중", "color": "yellow"},
                        {"name": "읽음",   "color": "green"},
                    ]
                }
            }

        if "날짜" not in existing:
            props_to_add["날짜"] = {"date": {}}

        if "URL" not in existing:
            props_to_add["URL"] = {"url": {}}

        if "시간대" not in existing:
            props_to_add["시간대"] = {"rich_text": {}}

        if "유형" not in existing:
            props_to_add["유형"] = {
                "select": {
                    "options": [
                        {"name": "기사",   "color": "blue"},
                        {"name": "브리핑", "color": "purple"},
                    ]
                }
            }

        added   = list(props_to_add.keys())
        skipped = [p for p in ["URL","날짜","상태","요약","시간대","유형"] if p in existing]
        errors  = []

        if props_to_add:
            try:
                notion.databases.update(
                    database_id=db_id,
                    properties=props_to_add
                )
            except Exception as e:
                errors.append(str(e))
                added = []

        return added, skipped, errors

    except Exception as e:
        return [], [], [str(e)]


# ════════════════════════════════════════════════════════
# 3. 메인 앱
# ════════════════════════════════════════════════════════
def show_main_app():
    user_id  = st.session_state["user_id"]
    email    = st.session_state["email"]
    role     = st.session_state.get("role", "trial")
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

    cfg = get_settings(user_id)
    keywords             = list(cfg.get("keywords") or [])
    use_filter           = cfg.get("use_filter", False)
    summary_mode_auto    = cfg.get("summary_mode_auto", "standard")
    summary_mode_manual  = cfg.get("summary_mode_manual", "standard")
    all_sources          = [s["name"] for s in NEWS_SOURCES]
    enabled_sources      = list(cfg.get("enabled_sources") or all_sources)
    auto_enabled_default = cfg.get("auto_enabled_default", False)
    auto_enabled_custom  = cfg.get("auto_enabled_custom", False)
    custom_schedules     = list(cfg.get("custom_schedules") or [])

    def _save(patch: dict):
        base = dict(
            keywords=keywords, use_filter=use_filter,
            summary_mode_auto=summary_mode_auto, summary_mode_manual=summary_mode_manual,
            enabled_sources=enabled_sources,
            auto_enabled_default=auto_enabled_default,
            auto_enabled_custom=auto_enabled_custom,
            custom_schedules=custom_schedules
        )
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
            if st.button("🔧 DB 속성 설정", use_container_width=True, help="Notion DB에 필수 속성을 자동으로 추가합니다"):
                st.session_state["show_db_setup"] = True
        
        if st.session_state.get("show_db_setup"):
            with st.spinner("DB 속성 설정 중..."):
                added, skipped, errors = _setup_notion_db(notion_token, notion_db_id)
            st.session_state.pop("show_db_setup", None)
            if errors:
                st.error(f"❌ 설정 실패: {errors[0]}")
            else:
                if added:
                    st.toast(f"✅ 속성 추가 완료: {', '.join(added)}")
                else:
                    st.toast("✅ 모든 속성이 이미 설정되어 있습니다!")

        if st.button("로그아웃", use_container_width=True):
            _do_logout()

    if st.session_state.get("confirm_notion_reset"):
        st.warning("⚠️ Notion 연결을 해제하시겠습니까? 다시 설정해야 합니다.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("✅ 확인", use_container_width=True, type="primary"):
                update_notion_credentials(user_id, None, None)
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
        _det_bonus = (user_row.get("detail_bonus") or 0) if user_row else 0

        # 자동 상세 요약 한도
        _auto_det_limit  = _get_limit(role, user_row, "trial_detail_auto_limit",   "free_detail_auto_limit",   "custom_detail_limit")
        _auto_det_used   = get_weekly_detail_count(user_id, crawl_type="auto")
        _auto_det_total  = _auto_det_limit + _det_bonus
        _auto_det_remain = max(0, _auto_det_total - _auto_det_used)

        # 수동 상세 요약 한도
        _manual_det_limit  = _get_limit(role, user_row, "trial_detail_manual_limit", "free_detail_manual_limit", "custom_detail_limit")
        _manual_det_used   = get_weekly_detail_count(user_id, crawl_type="manual")
        _manual_det_total  = _manual_det_limit + _det_bonus
        _manual_det_remain = max(0, _manual_det_total - _manual_det_used)

        # 수동 수집 한도
        _m_limit  = _get_limit(role, user_row, "trial_weekly_limit", "free_weekly_limit", "custom_weekly_limit")
        _m_bonus  = (user_row.get("manual_crawl_bonus") or 0) if user_row else 0
        _m_total  = _m_limit + _m_bonus
        _m_used   = get_weekly_crawl_count(user_id)
        _m_remain = max(0, _m_total - _m_used)

        left, right = st.columns(2)

        with left:
            # ── 자동화 설정 ────────────────────────────────
            st.subheader("🤖 자동화 설정")

            if role == "trial":
                st.warning("⚠️ 체험(trial) 계정은 자동화 기능을 사용할 수 없습니다. 무료 플랜으로 업그레이드하세요.")

            # 기본 스케줄 ON/OFF (trial은 disabled)
            _auto_disabled = (role == "trial")
            new_auto_default = st.toggle(
                "🔒 기본 자동 수집 (오전 7시 · 오후 8시)",
                value=auto_enabled_default,
                help="매일 오전 7시, 오후 8시에 자동 수집합니다.",
                disabled=_auto_disabled
            )
            if new_auto_default != auto_enabled_default and not _auto_disabled:
                auto_enabled_default = new_auto_default
                _save({"auto_enabled_default": auto_enabled_default})
                add_user_jobs(user_id, settings={**cfg,
                    "auto_enabled_default": auto_enabled_default,
                    "auto_enabled_custom": auto_enabled_custom,
                    "custom_schedules": custom_schedules,
                    "summary_mode_auto": summary_mode_auto})
                st.toast("✅ 기본 자동 수집 활성화!" if auto_enabled_default else "⏸ 기본 자동 수집 비활성화")

            if not _auto_disabled:
                if auto_enabled_default:
                    st.success("🟢 기본 자동 수집 활성화 중 (오전 7시 · 오후 8시)")
                else:
                    st.warning("🔴 기본 자동 수집 비활성화")

            # 커스텀 스케줄 ON/OFF
            new_auto_custom = st.toggle(
                "⏰ 지정 시간 자동 수집",
                value=auto_enabled_custom,
                help="아래에서 설정한 추가 시간에 자동 수집합니다.",
                disabled=_auto_disabled
            )
            if new_auto_custom != auto_enabled_custom and not _auto_disabled:
                auto_enabled_custom = new_auto_custom
                _save({"auto_enabled_custom": auto_enabled_custom})
                add_user_jobs(user_id, settings={**cfg,
                    "auto_enabled_default": auto_enabled_default,
                    "auto_enabled_custom": auto_enabled_custom,
                    "custom_schedules": custom_schedules,
                    "summary_mode_auto": summary_mode_auto})
                st.toast("✅ 지정 시간 자동 수집 활성화!" if auto_enabled_custom else "⏸ 지정 시간 자동 수집 비활성화")

            if not _auto_disabled:
                if auto_enabled_custom:
                    st.success("🟢 지정 시간 자동 수집 활성화 중")
                else:
                    st.warning("🔴 지정 시간 자동 수집 비활성화")

            # 커스텀 스케줄 관리
            with st.expander("⏰ 지정 시간 추가/관리"):
                    st.markdown("""
                    <div class="info-box">
                    💡 <b>수집 범위 안내</b><br>
                    각 시간대의 수집 범위는 <b>이전 활성 시간대 ~ 현재 시간대</b>로 자동 계산됩니다.<br>
                    기본 스케줄(7시·20시)과 시간이 겹쳐도 <b>중복된 기사는 URL로 자동 제외</b>됩니다.
                    </div>
                    """, unsafe_allow_html=True)

                    if custom_schedules:
                        st.write("**현재 지정 스케줄:**")
                        for i, sch in enumerate(custom_schedules):
                            sc1, sc2 = st.columns([4, 1])
                            with sc1:
                                r = sch.get("range_hours", "?")
                                st.write(f"🕐 자동 {sch['hour']:02d}:{sch['minute']:02d} KST — 최근 {r}시간 수집")
                            with sc2:
                                if st.button("삭제", key=f"del_sch_{i}"):
                                    custom_schedules.pop(i)
                                    _save({"custom_schedules": custom_schedules})
                                    add_user_jobs(user_id, settings={**cfg,
                                        "auto_enabled_default": auto_enabled_default,
                                        "auto_enabled_custom": auto_enabled_custom,
                                        "custom_schedules": custom_schedules})
                                    st.rerun()

                    if len(custom_schedules) < 5:
                        with st.form("add_schedule_form"):
                            nc1, nc2, nc3, nc4 = st.columns([2, 2, 2, 1])
                            with nc1:
                                new_hour  = st.number_input("시 (0~23)", min_value=0, max_value=23, value=12)
                            with nc2:
                                new_min   = st.number_input("분 (0~59)", min_value=0, max_value=59, value=0)
                            with nc3:
                                _max_hours = int(get_admin_config("max_crawl_hours") or 12)
                                new_range = st.number_input(f"수집 범위(시간, 최대 {_max_hours}h)", min_value=1, max_value=_max_hours, value=min(5, _max_hours),
                                                            help="실행 시각 기준 몇 시간 전부터 수집할지 설정")
                            with nc4:
                                st.write("")
                                st.write("")
                                add_btn = st.form_submit_button("➕", use_container_width=True)
                            if add_btn:
                                is_dup = any(s["hour"] == new_hour and s["minute"] == new_min for s in custom_schedules)
                                is_default = (new_hour == 7 and new_min == 0) or (new_hour == 20 and new_min == 0)
                                if is_default:
                                    st.error("기본 스케줄(7시·20시)과 중복됩니다.")
                                elif is_dup:
                                    st.error("이미 추가된 시간입니다.")
                                else:
                                    custom_schedules.append({"hour": new_hour, "minute": new_min, "range_hours": new_range, "enabled": True})
                                    _save({"custom_schedules": custom_schedules})
                                    add_user_jobs(user_id, settings={**cfg,
                                        "auto_enabled_default": auto_enabled_default,
                                        "auto_enabled_custom": auto_enabled_custom,
                                        "custom_schedules": custom_schedules})
                                    st.toast(f"✅ 자동 {new_hour:02d}:{new_min:02d} (최근 {new_range}시간) 추가!")
                                    st.rerun()
                    else:
                        st.caption("최대 5개까지 추가 가능합니다.")

            st.divider()

            # ── 자동 수집 요약 모드 ────────────────────────
            st.subheader("📝 자동 수집 요약 모드")

            new_mode_auto = st.radio(
                "자동수집_요약",
                ["standard", "detailed"],
                format_func=lambda x: "📄 기본 요약" if x == "standard" else "🔍 상세 분석",
                index=0 if summary_mode_auto == "standard" else 1,
                horizontal=True, label_visibility="collapsed",
                key="auto_mode_radio"
            )

            if role != "admin":
                if new_mode_auto == "standard":
                    st.markdown("""<div class="mode-standard">
                        <b>📄 기본 요약</b> — 핵심 요약 · 주요 내용 3가지 · 투자 시사점
                    </div>""", unsafe_allow_html=True)
                else:
                    # 상세 한도 확인
                    if _auto_det_remain <= 0:
                        st.error(f"🔒 이번 주 자동 상세 요약 횟수를 모두 사용했습니다. ({_auto_det_total}회 소진)")
                        new_mode_auto = "standard"
                    else:
                        st.markdown(f'<div class="limit-info">🔍 자동 상세 요약 남은 횟수: <b>{_auto_det_remain}회</b> ({_auto_det_used}/{_auto_det_total}회 사용)</div>', unsafe_allow_html=True)
                        st.markdown("""<div class="mode-detailed">
                            <b>🔍 상세 분석</b> — 핵심 요약 · 주요 내용 5가지 · 심층 분석 · 관련 기업/섹터
                        </div>""", unsafe_allow_html=True)
            else:
                if new_mode_auto == "standard":
                    st.markdown("""<div class="mode-standard"><b>📄 기본 요약</b></div>""", unsafe_allow_html=True)
                else:
                    st.markdown("""<div class="mode-detailed"><b>🔍 상세 분석</b></div>""", unsafe_allow_html=True)

            if new_mode_auto != summary_mode_auto:
                summary_mode_auto = new_mode_auto
                _save({"summary_mode_auto": summary_mode_auto})
                st.toast("자동 수집 요약 모드 저장됨!")

        with right:
            # ── 수동 수집 ──────────────────────────────────
            st.subheader("▶ 수동 수집")

            # 요약 모드 선택
            new_mode_manual = st.radio(
                "수동수집_요약",
                ["standard", "detailed"],
                format_func=lambda x: "📄 기본 요약" if x == "standard" else "🔍 상세 분석",
                index=0 if summary_mode_manual == "standard" else 1,
                horizontal=True, label_visibility="collapsed",
                key="manual_mode_radio"
            )

            # 수정3,5: 선택한 모드에 따라 해당 한도만 표시
            if role != "admin":
                if new_mode_manual == "standard":
                    if _m_remain <= 0:
                        st.error(f"🔒 이번 주 수동 기본 수집 횟수를 모두 사용했습니다. ({_m_total}회 소진)")
                    else:
                        st.markdown(
                            f'<div class="limit-info">📄 수동 기본 수집 — 이번 주 <b>{_m_used}/{_m_total}회</b> 사용 · 남은 횟수: <b>{_m_remain}회</b></div>',
                            unsafe_allow_html=True
                        )
                else:
                    # 상세 선택 시 상세 한도 + 수동 횟수 모두 확인
                    if _manual_det_remain <= 0:
                        st.error(f"🔒 이번 주 수동 상세 요약 횟수를 모두 사용했습니다. ({_manual_det_total}회 소진)")
                        new_mode_manual = "standard"
                    elif _m_remain <= 0:
                        st.error(f"🔒 이번 주 수동 수집 횟수를 모두 사용했습니다. ({_m_total}회 소진)")
                    else:
                        st.markdown(
                            f'<div class="limit-info">'
                            f'🔍 수동 상세 수집 — 수집 <b>{_m_used}/{_m_total}회</b> · 상세 요약 <b>{_manual_det_used}/{_manual_det_total}회</b> 사용<br>'
                            f'&nbsp;&nbsp;&nbsp;남은 수집: <b>{_m_remain}회</b> · 남은 상세 요약: <b>{_manual_det_remain}회</b>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

            if new_mode_manual != summary_mode_manual:
                summary_mode_manual = new_mode_manual
                _save({"summary_mode_manual": summary_mode_manual})
                st.toast("수동 수집 요약 모드 저장됨!")

            st.divider()

            hour_map = {"1시간":1,"3시간":3,"6시간":6,"12시간":12,"24시간":24,"36시간":36,"48시간":48}
            sel_range = st.select_slider("수집 범위", options=list(hour_map.keys()), value="6시간")
            sel_hours = hour_map[sel_range]
            from zoneinfo import ZoneInfo
            now_kst = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)
            st.caption(f"📅 {(now_kst - timedelta(hours=sel_hours)).strftime('%m/%d %H:%M')} ~ {now_kst.strftime('%m/%d %H:%M')} (KST)")

            # 버튼 비활성화 조건: 수동 횟수 또는 상세 횟수 초과
            _btn_disabled = False
            if role in ["trial", "free"]:
                if _m_remain <= 0:
                    _btn_disabled = True
                elif new_mode_manual == "detailed" and _manual_det_remain <= 0:
                    _btn_disabled = True

            if st.button("📥 수동 수집 시작", use_container_width=True, type="primary",
                         disabled=_btn_disabled):
                if not notion_token or not notion_db_id:
                    st.error("❌ Notion 연결이 필요합니다.")
                else:
                    with st.spinner(f"최근 {sel_range} 기사 수집 중..."):
                        saved, skipped = run_crawler(
                            notion_token=notion_token,
                            notion_db_id=notion_db_id,
                            settings=dict(keywords=keywords, use_filter=use_filter,
                                          summary_mode=new_mode_manual, enabled_sources=enabled_sources),
                            time_label="수동", hours=sel_hours,
                        )
                    record_manual_crawl(user_id)
                    if new_mode_manual == "detailed":
                        record_detail_crawl(user_id, crawl_type="manual")
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
        3. **자동 수집 요약 모드** 선택 (기본/상세 별도 설정)
        4. **수동 수집** — 원하는 시간 범위로 직접 크롤링
        5. **기본 자동 수집** — 매일 오전 7시, 오후 8시 자동 저장
        6. **지정 시간 자동 수집** — 원하는 시간 추가 설정 가능
        7. **Notion** 에서 저장된 기사 확인
        8. **브리핑** 탭에서 그룹별 한눈에 요약 확인
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
            # 브리핑 모드 선택
            briefing_mode = st.radio(
                "브리핑 모드",
                ["standard", "detailed"],
                format_func=lambda x: "📄 기본 브리핑" if x == "standard" else "🔍 상세 브리핑",
                horizontal=True, label_visibility="collapsed",
                key="briefing_mode_radio"
            )
            if briefing_mode == "standard":
                st.caption("📄 기본 — 카테고리별 핵심 1줄 요약 + 오늘의 핵심 메시지")
            else:
                st.caption("🔍 상세 — 카테고리별 심층 분석 + 투자 시사점 + 리스크 요인")

            # 브리핑 횟수 제한 (기본/상세 별개)
            if briefing_mode == "standard":
                _b_limit  = _get_limit(role, user_row, "trial_briefing_std_limit", "free_briefing_std_limit", "custom_briefing_limit")
            else:
                _b_limit  = _get_limit(role, user_row, "trial_briefing_det_limit", "free_briefing_det_limit", "custom_briefing_limit")

            _b_bonus  = (user_row.get("briefing_bonus") or 0) if user_row else 0
            _b_total  = _b_limit + _b_bonus
            _b_used   = get_weekly_briefing_count(user_id, mode=briefing_mode)
            _b_remain = max(0, _b_total - _b_used)

            if role != "admin":
                mode_label = "기본" if briefing_mode == "standard" else "상세"
                st.markdown(f'<div class="limit-info">📊 이번 주 {mode_label} 브리핑: <b>{_b_used} / {_b_total}회</b> (남은: <b>{_b_remain}회</b>)</div>', unsafe_allow_html=True)

            with st.spinner("Notion에서 데이터 불러오는 중..."):
                groups = _get_notion_groups(notion_token, notion_db_id)

            if not groups:
                st.info("저장된 기사가 없습니다.")
            else:
                selected_group = st.selectbox("브리핑할 그룹 선택", options=groups, index=0)

                if st.button("📋 브리핑 생성", type="primary", use_container_width=True,
                             disabled=(role in ["trial", "free"] and _b_remain <= 0)):
                    if role in ["trial", "free"] and _b_remain <= 0:
                        st.error(f"❌ 이번 주 브리핑 횟수({_b_total}회)를 모두 사용했습니다.")
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
                                record_briefing(user_id, mode=briefing_mode)
                                st.session_state["briefing_result"] = briefing
                                st.session_state["briefing_group"]  = selected_group
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
        notion  = NotionClient(auth=notion_token)
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
        notion  = NotionClient(auth=notion_token)
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
            props   = page.get("properties", {})
            title   = props["이름"]["title"][0]["text"]["content"] if props.get("이름", {}).get("title") else ""
            summary = props["요약"]["rich_text"][0]["text"]["content"] if props.get("요약", {}).get("rich_text") else ""
            url     = props.get("URL", {}).get("url", "")
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
        notion     = NotionClient(auth=notion_token)
        title      = f"📋 브리핑 | {group} ({article_count}개 기사)"
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
        elapsed_total = (datetime.now() - verified_at).total_seconds() / 60
        if elapsed_total < 30:
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
            remaining = int((locked_until - _dt.now()).total_seconds() / 60) + 1
            st.error(f"🔒 관리자 비밀번호 5회 오류. {remaining}분 후 다시 시도해주세요.")
            return

        with st.form("admin_verify_form"):
            admin_pw   = st.text_input("관리자 비밀번호", type="password")
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
    users     = get_all_users()
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

    from datetime import timezone, timedelta as _td
    _KST = timezone(_td(hours=9))
    def _kst(dt):
        if not dt: return '-'
        return dt.replace(tzinfo=timezone.utc).astimezone(_KST).strftime('%Y-%m-%d %H:%M')

    for user in users:
        uid = user["user_id"]
        with st.expander(f"{user['email']}  —  {role_labels.get(user['role'], user['role'])}"):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write(f"**가입일:** {_kst(user['created_at'])}")
                st.write(f"**마지막 로그인:** {_kst(user['last_login'])}")
                st.write(f"**Notion 연결:** {'✅' if user['notion_connected'] else '❌'}")
                # 잠금 여부 확인
                from db import is_account_locked
                is_locked = is_account_locked(user["email"])
                if is_locked:
                    st.error("🔒 로그인 잠금 상태")
                    if st.button("🔓 잠금 해제", key=f"unlock_{uid}", type="primary"):
                        unlock_account(user["email"])
                        st.toast(f"✅ {user['email']} 잠금 해제!")
                        st.rerun()
                w_crawl = get_weekly_crawl_count(uid)
                w_detail = get_weekly_detail_count(uid)
                w_brief_std = get_weekly_briefing_count(uid, mode='standard')
                w_brief_det = get_weekly_briefing_count(uid, mode='detailed')
                st.write(f"**이번 주 수동 수집:** {w_crawl}회")
                st.write(f"**이번 주 상세 요약:** {w_detail}회")
                st.write(f"**이번 주 브리핑(기본):** {w_brief_std}회 / **브리핑(상세):** {w_brief_det}회")

                # 보너스 횟수 표시
                b_crawl  = user.get("manual_crawl_bonus", 0)
                b_brief  = user.get("briefing_bonus", 0)
                b_detail = user.get("detail_bonus", 0)
                if b_crawl or b_brief or b_detail:
                    st.caption(f"🎁 보너스 — 수동수집: +{b_crawl} / 브리핑: +{b_brief} / 상세: +{b_detail}")

            with col2:
                # 권한 변경
                current_idx = role_options.index(user["role"]) if user["role"] in role_options else 0
                new_role    = st.selectbox("권한 변경", options=role_options, index=current_idx,
                                           format_func=lambda x: role_labels.get(x, x),
                                           key=f"role_{uid}")
                if st.button("저장", key=f"save_{uid}"):
                    update_user_role(uid, new_role)
                    st.toast(f"✅ {user['email']} → {role_labels[new_role]}")
                    st.rerun()

                st.divider()

                # 개별 한도 설정 (0=기본값, 개별설정 > 전체설정 우선)
                st.caption("**개별 한도 설정** (0=전체 기본값 적용, 개별 설정이 전체보다 우선)")

                cur_m = user.get("custom_weekly_limit")
                st.caption("기본 수동 수집 한도")
                m_input = st.number_input("기본 수동 수집 (주간)", min_value=0, max_value=500,
                                          value=cur_m if cur_m is not None else 0, key=f"m_{uid}",
                                          label_visibility="collapsed")
                mc1, mc2 = st.columns(2)
                with mc1:
                    if st.button("저장", key=f"ms_{uid}"):
                        update_user_custom_limit(uid, m_input if m_input > 0 else None)
                        st.toast("✅ 기본 수동 수집 한도 저장!")
                        st.rerun()
                with mc2:
                    if st.button("기본값", key=f"mr_{uid}"):
                        update_user_custom_limit(uid, None)
                        st.toast("✅ 초기화!")
                        st.rerun()

                st.divider()
                cur_dm = user.get("custom_detail_manual_limit")
                st.caption("수동 상세 요약 한도")
                dm_input = st.number_input("수동 상세 (주간)", min_value=0, max_value=200,
                                           value=cur_dm if cur_dm is not None else 0, key=f"dm_{uid}",
                                           label_visibility="collapsed")
                dmc1, dmc2 = st.columns(2)
                with dmc1:
                    if st.button("저장", key=f"dms_{uid}"):
                        from db import update_user_custom_detail_manual_limit
                        update_user_custom_detail_manual_limit(uid, dm_input if dm_input > 0 else None)
                        st.toast("✅ 수동 상세 한도 저장!")
                        st.rerun()
                with dmc2:
                    if st.button("기본값", key=f"dmr_{uid}"):
                        from db import update_user_custom_detail_manual_limit
                        update_user_custom_detail_manual_limit(uid, None)
                        st.toast("✅ 초기화!")
                        st.rerun()

                st.divider()
                cur_da = user.get("custom_detail_auto_limit")
                st.caption("자동 상세 요약 한도")
                da_input = st.number_input("자동 상세 (주간)", min_value=0, max_value=200,
                                           value=cur_da if cur_da is not None else 0, key=f"da_{uid}",
                                           label_visibility="collapsed")
                dac1, dac2 = st.columns(2)
                with dac1:
                    if st.button("저장", key=f"das_{uid}"):
                        from db import update_user_custom_detail_auto_limit
                        update_user_custom_detail_auto_limit(uid, da_input if da_input > 0 else None)
                        st.toast("✅ 자동 상세 한도 저장!")
                        st.rerun()
                with dac2:
                    if st.button("기본값", key=f"dar_{uid}"):
                        from db import update_user_custom_detail_auto_limit
                        update_user_custom_detail_auto_limit(uid, None)
                        st.toast("✅ 초기화!")
                        st.rerun()

                st.divider()
                cur_b = user.get("custom_briefing_limit")
                st.caption("브리핑 한도")
                b_input = st.number_input("브리핑 (주간)", min_value=0, max_value=100,
                                          value=cur_b if cur_b is not None else 0, key=f"b_{uid}",
                                          label_visibility="collapsed")
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("저장", key=f"bs_{uid}"):
                        update_user_custom_briefing_limit(uid, b_input if b_input > 0 else None)
                        st.toast("✅ 브리핑 한도 저장!")
                        st.rerun()
                with bc2:
                    if st.button("기본값", key=f"br_{uid}"):
                        update_user_custom_briefing_limit(uid, None)
                        st.toast("✅ 초기화!")
                        st.rerun()

                st.divider()

                # 이번 주 보너스 추가 (당주만 유효, 다음주 초기화)
                st.caption("**이번 주 보너스 추가** (당주에만 적용, 다음주 자동 초기화)")
                bonus_type = st.selectbox("항목", ["기본 수동 수집", "수동 상세 요약", "자동 상세 요약", "브리핑"], key=f"bt_{uid}")
                bonus_amt  = st.number_input("추가 횟수", min_value=1, max_value=100, value=5, key=f"ba_{uid}")
                if st.button("➕ 보너스 추가", key=f"badd_{uid}", use_container_width=True):
                    type_map = {
                        "기본 수동 수집": "manual_crawl_bonus",
                        "수동 상세 요약": "manual_detail_bonus",
                        "자동 상세 요약": "auto_detail_bonus",
                        "브리핑":         "briefing_bonus"
                    }
                    add_user_bonus(uid, type_map[bonus_type], bonus_amt)
                    st.toast(f"✅ {user['email']} {bonus_type} +{bonus_amt}회 추가!")
                    st.rerun()

    # ── 권한별 제한 설정 (수정8 - 다음주부터 적용 안내) ──
    st.divider()
    st.subheader("⚙️ 권한별 제한 설정")
    st.info("⚠️ 여기서 변경한 한도는 **다음 주 월요일부터** 적용됩니다. 이번 주 즉시 추가가 필요하면 위 개별 계정의 **보너스 추가** 기능을 사용하세요.")

    cur_trial_m  = int(get_admin_config("trial_weekly_limit")       or 15)
    cur_free_m   = int(get_admin_config("free_weekly_limit")        or 30)
    cur_trial_dm = int(get_admin_config("trial_detail_manual_limit") or 10)
    cur_free_dm  = int(get_admin_config("free_detail_manual_limit")  or 20)
    cur_trial_da = int(get_admin_config("trial_detail_auto_limit")   or 10)
    cur_free_da  = int(get_admin_config("free_detail_auto_limit")    or 20)
    cur_trial_bs = int(get_admin_config("trial_briefing_std_limit") or 5)
    cur_free_bs  = int(get_admin_config("free_briefing_std_limit")  or 10)
    cur_trial_bd = int(get_admin_config("trial_briefing_det_limit") or 3)
    cur_free_bd  = int(get_admin_config("free_briefing_det_limit")  or 5)

    cur_max_hours = int(get_admin_config("max_crawl_hours") or 12)
    st.markdown("**지정 시간 자동 수집 최대 범위 (시간)**")
    new_max_hours = st.number_input("최대 수집 범위 (시간)", min_value=1, max_value=48, value=cur_max_hours, key="nmh")

    st.markdown("**기본 수동 수집 주간 한도**")
    s1, s2 = st.columns(2)
    with s1: new_tm = st.number_input("체험", min_value=1, max_value=100,  value=cur_trial_m,  key="ntm")
    with s2: new_fm = st.number_input("무료", min_value=1, max_value=200,  value=cur_free_m,   key="nfm")

    st.markdown("**수동 상세 요약 주간 한도**")
    d1, d2 = st.columns(2)
    with d1: new_tdm = st.number_input("체험", min_value=1, max_value=100, value=cur_trial_dm, key="ntdm")
    with d2: new_fdm = st.number_input("무료", min_value=1, max_value=200, value=cur_free_dm,  key="nfdm")

    st.markdown("**자동 상세 요약 주간 한도**")
    da1, da2 = st.columns(2)
    with da1: new_tda = st.number_input("체험", min_value=1, max_value=100, value=cur_trial_da, key="ntda")
    with da2: new_fda = st.number_input("무료", min_value=1, max_value=200, value=cur_free_da,  key="nfda")

    st.markdown("**브리핑(기본) 주간 한도**")
    b1, b2 = st.columns(2)
    with b1: new_tbs = st.number_input("체험", min_value=1, max_value=50,  value=cur_trial_bs, key="ntbs")
    with b2: new_fbs = st.number_input("무료", min_value=1, max_value=100, value=cur_free_bs,  key="nfbs")

    st.markdown("**브리핑(상세) 주간 한도**")
    bd1, bd2 = st.columns(2)
    with bd1: new_tbd = st.number_input("체험", min_value=1, max_value=50,  value=cur_trial_bd, key="ntbd")
    with bd2: new_fbd = st.number_input("무료", min_value=1, max_value=100, value=cur_free_bd,  key="nfbd")

    if st.button("💾 제한 설정 저장", type="primary"):
        set_admin_config("max_crawl_hours",          str(new_max_hours))
        set_admin_config("trial_weekly_limit",       str(new_tm))
        set_admin_config("free_weekly_limit",        str(new_fm))
        set_admin_config("trial_detail_manual_limit", str(new_tdm))
        set_admin_config("free_detail_manual_limit",  str(new_fdm))
        set_admin_config("trial_detail_auto_limit",   str(new_tda))
        set_admin_config("free_detail_auto_limit",    str(new_fda))
        set_admin_config("trial_briefing_std_limit", str(new_tbs))
        set_admin_config("free_briefing_std_limit",  str(new_fbs))
        set_admin_config("trial_briefing_det_limit", str(new_tbd))
        set_admin_config("free_briefing_det_limit",  str(new_fbd))
        st.toast("✅ 제한 설정 저장 완료! (다음 주부터 적용)")
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
