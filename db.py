import os
import psycopg2
import psycopg2.extras
import json
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id           SERIAL PRIMARY KEY,
                email             TEXT UNIQUE NOT NULL,
                password_hash     TEXT NOT NULL,
                notion_token_enc  TEXT,
                notion_db_id      TEXT,
                is_active         BOOLEAN DEFAULT TRUE,
                role              TEXT DEFAULT 'trial',
                created_at        TIMESTAMP DEFAULT NOW(),
                last_login        TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at   TIMESTAMP DEFAULT NOW(),
                expires_at   TIMESTAMP NOT NULL,
                ip_address   TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id           SERIAL PRIMARY KEY,
                email        TEXT NOT NULL,
                ip_address   TEXT,
                success      BOOLEAN NOT NULL,
                attempted_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id         INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                keywords        JSONB   DEFAULT '[]',
                use_filter      BOOLEAN DEFAULT FALSE,
                summary_mode    TEXT    DEFAULT 'standard',
                enabled_sources JSONB   DEFAULT '[]',
                auto_enabled    BOOLEAN DEFAULT FALSE,
                updated_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS manual_crawl_log (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS briefing_log (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 마이그레이션
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'trial'")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_weekly_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_briefing_limit INTEGER DEFAULT NULL")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, attempted_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_log_user ON manual_crawl_log(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_briefing_log_user ON briefing_log(user_id, created_at)")

        # 기본 설정값
        cur.execute("INSERT INTO admin_config (key, value) VALUES ('trial_weekly_limit', '15') ON CONFLICT (key) DO NOTHING")
        cur.execute("INSERT INTO admin_config (key, value) VALUES ('free_weekly_limit', '30') ON CONFLICT (key) DO NOTHING")
        cur.execute("INSERT INTO admin_config (key, value) VALUES ('trial_briefing_limit', '5') ON CONFLICT (key) DO NOTHING")
        cur.execute("INSERT INTO admin_config (key, value) VALUES ('free_briefing_limit', '10') ON CONFLICT (key) DO NOTHING")


# ─── 유저 ────────────────────────────────────────────────
def create_user(email: str, password_hash: str):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING user_id",
                (email.lower().strip(), password_hash)
            )
            return cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        return None

def get_user_by_email(email: str):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM users WHERE email = %s AND is_active = TRUE AND role != 'blocked'",
            (email.lower().strip(),)
        )
        return cur.fetchone()

def get_user_by_id(user_id: int):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return cur.fetchone()

def update_last_login(user_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET last_login = NOW() WHERE user_id = %s", (user_id,))

def update_notion_credentials(user_id: int, notion_token_enc: str, notion_db_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET notion_token_enc = %s, notion_db_id = %s WHERE user_id = %s",
            (notion_token_enc, notion_db_id, user_id)
        )

def update_user_role(user_id: int, role: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role = %s WHERE user_id = %s", (role, user_id))

def update_user_custom_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_weekly_limit = %s WHERE user_id = %s", (limit, user_id))

def update_user_custom_briefing_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_briefing_limit = %s WHERE user_id = %s", (limit, user_id))

def get_all_users():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT user_id, email, role, is_active, created_at, last_login,
                   notion_db_id, custom_weekly_limit, custom_briefing_limit,
                   CASE WHEN notion_token_enc IS NOT NULL THEN TRUE ELSE FALSE END AS notion_connected
            FROM users
            ORDER BY created_at DESC
        """)
        return cur.fetchall()


# ─── 세션 ────────────────────────────────────────────────
def create_session(session_id: str, user_id: int, ip_address: str = None, hours: int = 1):
    from datetime import datetime, timedelta
    expires_at = datetime.now() + timedelta(hours=hours)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        cur.execute(
            "INSERT INTO sessions (session_id, user_id, expires_at, ip_address) VALUES (%s, %s, %s, %s)",
            (session_id, user_id, expires_at, ip_address)
        )

def get_session(session_id: str):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM sessions WHERE session_id = %s AND expires_at > NOW()",
            (session_id,)
        )
        return cur.fetchone()

def extend_session(session_id: str, hours: int = 1):
    """세션 만료 시간 연장"""
    from datetime import datetime, timedelta
    new_expires = datetime.now() + timedelta(hours=hours)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET expires_at = %s WHERE session_id = %s",
            (new_expires, session_id)
        )

def delete_session(session_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))

def cleanup_expired_sessions():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE expires_at < NOW()")


# ─── 로그인 시도 제한 ────────────────────────────────────
def record_login_attempt(email: str, success: bool, ip_address: str = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO login_attempts (email, ip_address, success) VALUES (%s, %s, %s)",
            (email.lower().strip(), ip_address, success)
        )

def is_account_locked(email: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM login_attempts
            WHERE email = %s
              AND success = FALSE
              AND attempted_at > NOW() - INTERVAL '%s minutes'
        """, (email.lower().strip(), window_minutes))
        count = cur.fetchone()[0]
        return count >= max_attempts

def get_remaining_lockout_minutes(email: str, window_minutes: int = 15) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT attempted_at FROM login_attempts
            WHERE email = %s AND success = FALSE
            ORDER BY attempted_at DESC
            LIMIT 1
        """, (email.lower().strip(),))
        row = cur.fetchone()
        if not row:
            return 0
        from datetime import datetime, timedelta
        unlock_at = row[0] + timedelta(minutes=window_minutes)
        remaining = (unlock_at - datetime.now()).seconds // 60
        return max(0, remaining)


# ─── 수동 수집 횟수 ──────────────────────────────────────
def record_manual_crawl(user_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO manual_crawl_log (user_id) VALUES (%s)", (user_id,))

def get_weekly_crawl_count(user_id: int) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM manual_crawl_log
            WHERE user_id = %s
              AND created_at >= DATE_TRUNC('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
        """, (user_id,))
        return cur.fetchone()[0]


# ─── 브리핑 횟수 ─────────────────────────────────────────
def record_briefing(user_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO briefing_log (user_id) VALUES (%s)", (user_id,))

def get_weekly_briefing_count(user_id: int) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM briefing_log
            WHERE user_id = %s
              AND created_at >= DATE_TRUNC('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
        """, (user_id,))
        return cur.fetchone()[0]


# ─── 관리자 설정 ─────────────────────────────────────────
def get_admin_config(key: str) -> str:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM admin_config WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else None

def set_admin_config(key: str, value: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO admin_config (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (key, value))


# ─── 설정 ────────────────────────────────────────────────
def get_settings(user_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return {
            "keywords": [],
            "use_filter": False,
            "summary_mode": "standard",
            "enabled_sources": [],
            "auto_enabled": False,
        }

def save_settings(user_id: int, settings: dict):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_settings
                (user_id, keywords, use_filter, summary_mode, enabled_sources, auto_enabled, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET keywords        = EXCLUDED.keywords,
                    use_filter      = EXCLUDED.use_filter,
                    summary_mode    = EXCLUDED.summary_mode,
                    enabled_sources = EXCLUDED.enabled_sources,
                    auto_enabled    = EXCLUDED.auto_enabled,
                    updated_at      = NOW()
        """, (
            user_id,
            json.dumps(settings.get("keywords", []), ensure_ascii=False),
            settings.get("use_filter", False),
            settings.get("summary_mode", "standard"),
            json.dumps(settings.get("enabled_sources", []), ensure_ascii=False),
            settings.get("auto_enabled", False),
        ))
