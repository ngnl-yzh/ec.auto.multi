import os
import secrets
import base64
import hashlib
import hmac
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ─── 암호화 키 초기화 ────────────────────────────────────
def _get_fernet() -> Fernet:
    """ENCRYPTION_KEY 환경변수로 Fernet 키 생성"""
    raw_key = os.environ.get("ENCRYPTION_KEY", "")
    if not raw_key:
        raise ValueError("ENCRYPTION_KEY 환경변수가 설정되지 않았습니다.")

    # PASSWORD_SALT 필수 (main.py·배포에서 검증). 미설정 시 고정값은 로컬 개발용일 뿐 비권장.
    salt_str = os.environ.get("PASSWORD_SALT") or "ecnews_static_salt_v1"
    salt = salt_str.encode()[:32].ljust(32, b"0")  # 32바이트로 정규화

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(raw_key.encode()))
    return Fernet(key)


# ─── 비밀번호 (bcrypt) ───────────────────────────────────
def hash_password(password: str) -> str:
    """bcrypt로 비밀번호 해싱"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    """bcrypt 비밀번호 검증"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── Notion 토큰 암호화 (AES-256 via Fernet) ────────────
def encrypt_token(token: str) -> str:
    """Notion 토큰 암호화"""
    f = _get_fernet()
    return f.encrypt(token.encode("utf-8")).decode("utf-8")

def decrypt_token(encrypted: str) -> str:
    """Notion 토큰 복호화"""
    f = _get_fernet()
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")


# ─── 세션 토큰 ───────────────────────────────────────────
def generate_session_id() -> str:
    """암호학적으로 안전한 세션 ID 생성 (64자 hex)"""
    return secrets.token_hex(32)


# ─── 입력값 검증 ─────────────────────────────────────────
def validate_email(email: str) -> tuple[bool, str]:
    import re as _re
    email = email.strip()
    if not email:
        return False, "이메일을 입력해주세요."
    if len(email) > 254:
        return False, "이메일이 너무 깁니다."
    # RFC 5322 간소화 정규식
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not _re.match(pattern, email):
        return False, "올바른 이메일 형식이 아닙니다."
    return True, ""

def safe_password_equal(candidate: str, expected: str) -> bool:
    """문자열 비교 시 타이밍 차이 완화(관리자 비밀번호 등). 평문을 직접 비교하지 않음."""
    ca = hashlib.sha256(candidate.encode("utf-8")).digest()
    ex = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(ca, ex)


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "비밀번호는 8자 이상이어야 합니다."
    if len(password) > 128:
        return False, "비밀번호가 너무 깁니다."
    # bcrypt는 72바이트 초과 입력을 조용히 잘라먹음 — 명시적으로 제한
    if len(password.encode("utf-8")) > 72:
        return False, "비밀번호는 UTF-8 기준 72바이트 이하여야 합니다."
    if not any(c.isdigit() for c in password):
        return False, "비밀번호에 숫자를 포함해주세요."
    if not any(c.isalpha() for c in password):
        return False, "비밀번호에 문자(한글·영문 등)를 포함해주세요."
    return True, ""


def validate_encryption_key_strength() -> tuple[bool, str]:
    """ENCRYPTION_KEY 길이 검사. 배포 호환을 위해 8자 미만만 실패, 그 외는 경고만."""
    raw = os.environ.get("ENCRYPTION_KEY", "")
    if len(raw) < 8:
        return False, "ENCRYPTION_KEY는 최소 8자 이상이어야 합니다."
    if len(raw) < 16:
        return True, "ENCRYPTION_KEY는 16자 이상(가능하면 32자 무작위)으로 늘리는 것을 권장합니다."
    if len(raw) < 32:
        return True, "ENCRYPTION_KEY는 32자 이상의 무작위 문자열을 권장합니다."
    return True, ""

def validate_notion_token(token: str) -> tuple[bool, str]:
    token = token.strip()
    if not token.startswith("ntn_"):
        return False, "토큰은 'ntn_' 으로 시작해야 합니다."
    if len(token) < 20:
        return False, "토큰이 너무 짧습니다."
    return True, ""

def validate_notion_db_id(db_id: str) -> tuple[bool, str]:
    """URL 전체 또는 DB ID 직접 입력 모두 허용"""
    extracted = extract_notion_db_id(db_id)
    if not extracted:
        return False, "DB ID를 찾을 수 없습니다. Notion DB 페이지 URL 또는 32자리 ID를 입력해주세요."
    return True, ""

def extract_notion_db_id(raw: str) -> str | None:
    """
    Notion DB URL 또는 ID에서 32자리 DB ID 추출.
    지원 형식:
      - https://www.notion.so/workspace/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
      - https://notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
      - xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (32자리 직접 입력)
      - xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (하이픈 포함)
    """
    import re
    raw = raw.strip()

    # URL인 경우 경로에서 추출
    if "notion.so" in raw:
        # ?v= 앞 부분만 사용
        raw = raw.split("?")[0].split("#")[0]
        # 마지막 경로 세그먼트 추출
        segment = raw.rstrip("/").split("/")[-1]
        # 하이픈 제거
        candidate = segment.replace("-", "")
        if len(candidate) == 32 and candidate.isalnum():
            return candidate
        return None

    # 직접 입력 (하이픈 있을 수도 없을 수도)
    candidate = raw.replace("-", "")
    if len(candidate) == 32 and candidate.isalnum():
        return candidate

    return None
