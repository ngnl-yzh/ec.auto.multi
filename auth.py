import os
from db import (
    create_user, get_user_by_email_for_login, update_last_login,
    record_login_attempt, is_account_locked, get_remaining_lockout_minutes,
    is_ip_bruteforce_locked, get_remaining_ip_lockout_minutes,
    count_rate_events, record_rate_event,
    create_session, delete_session, update_user_role,
)
from security import (
    hash_password, verify_password,
    generate_session_id,
    validate_email, validate_password
)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower().strip()

# 공개 서비스: IP당 일일 가입 상한 (환경변수로 조정)
_MAX_REG_PER_IP = int(os.environ.get("MAX_REGISTRATIONS_PER_IP_PER_DAY", "5"))
# 동일 IP에서 15분 내 로그인 실패(계정 무관) 상한
_IP_LOGIN_FAIL_MAX = int(os.environ.get("IP_LOGIN_MAX_FAILURES_PER_WINDOW", "30"))


def register(email: str, password: str, ip_address: str = None):
    ok, msg = validate_email(email)
    if not ok:
        return False, msg
    ok, msg = validate_password(password)
    if not ok:
        return False, msg

    if ip_address and count_rate_events(ip_address, "register", hours=24) >= _MAX_REG_PER_IP:
        return False, "같은 네트워크에서 오늘 가입 가능 횟수를 초과했습니다. 내일 다시 시도하거나 관리자에게 문의해주세요."

    user_id = create_user(email, hash_password(password))
    if user_id is None:
        return False, "이미 가입된 이메일입니다."

    if ip_address:
        record_rate_event(ip_address, "register")

    # ADMIN_EMAIL과 일치하면 자동으로 admin 권한 부여
    if email.lower().strip() == ADMIN_EMAIL:
        update_user_role(user_id, "admin")

    return True, user_id


def login(email: str, password: str, ip_address: str = None):
    email = email.lower().strip()

    if ip_address and is_ip_bruteforce_locked(ip_address, max_attempts=_IP_LOGIN_FAIL_MAX):
        remaining = get_remaining_ip_lockout_minutes(ip_address)
        return False, (
            f"이 네트워크에서 로그인 시도가 너무 많습니다. "
            f"약 {remaining}분 후에 다시 시도해주세요."
        ), None

    if is_account_locked(email):
        remaining = get_remaining_lockout_minutes(email)
        return False, f"로그인 시도가 너무 많습니다. {remaining}분 후에 다시 시도해주세요.", None

    user = get_user_by_email_for_login(email)

    if not user or not verify_password(password, user["password_hash"]):
        record_login_attempt(email, success=False, ip_address=ip_address)
        from db import get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM login_attempts
                WHERE email = %s AND success = FALSE
                  AND attempted_at > NOW() - INTERVAL '15 minutes'
            """, (email,))
            fail_count = cur.fetchone()[0]
        remaining_tries = max(0, 5 - fail_count)
        if remaining_tries > 0:
            return False, f"이메일 또는 비밀번호가 올바르지 않습니다. (남은 시도: {remaining_tries}회)", None
        else:
            return False, "로그인 시도가 너무 많습니다. 15분 후에 다시 시도해주세요.", None

    if user.get("role") == "blocked":
        return False, "차단된 계정입니다. 관리자에게 문의해주세요.", None

    record_login_attempt(email, success=True, ip_address=ip_address)
    update_last_login(user["user_id"])

    # 로그인 성공 시 실패 기록 초기화
    from db import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM login_attempts WHERE email = %s AND success = FALSE", (email,))

    # ADMIN_EMAIL 환경변수와 일치하면 자동 admin 승격
    if email == ADMIN_EMAIL and user.get("role") != "admin":
        update_user_role(user["user_id"], "admin")

    session_id = generate_session_id()
    create_session(session_id, user["user_id"], ip_address=ip_address, minutes=30)

    return True, session_id, user


def logout(session_id: str):
    delete_session(session_id)
