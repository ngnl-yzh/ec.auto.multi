from db import (
    create_user, get_user_by_email, update_last_login,
    record_login_attempt, is_account_locked, get_remaining_lockout_minutes,
    create_session, delete_session
)
from security import (
    hash_password, verify_password,
    generate_session_id,
    validate_email, validate_password
)


def register(email: str, password: str):
    """
    회원가입.
    반환: (True, user_id) | (False, 오류메시지)
    """
    ok, msg = validate_email(email)
    if not ok:
        return False, msg

    ok, msg = validate_password(password)
    if not ok:
        return False, msg

    user_id = create_user(email, hash_password(password))
    if user_id is None:
        return False, "이미 가입된 이메일입니다."
    return True, user_id


def login(email: str, password: str, ip_address: str = None):
    """
    로그인.
    반환: (True, session_id, user_row) | (False, 오류메시지, None)
    """
    email = email.lower().strip()

    # 계정 잠금 확인
    if is_account_locked(email):
        remaining = get_remaining_lockout_minutes(email)
        return False, f"로그인 시도가 너무 많습니다. {remaining}분 후에 다시 시도해주세요.", None

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        record_login_attempt(email, success=False, ip_address=ip_address)
        # 남은 시도 횟수 계산
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

    record_login_attempt(email, success=True, ip_address=ip_address)
    update_last_login(user["user_id"])

    # 세션 생성
    session_id = generate_session_id()
    create_session(session_id, user["user_id"], ip_address=ip_address, hours=24)

    return True, session_id, user


def logout(session_id: str):
    delete_session(session_id)
