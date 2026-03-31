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
                user_id              INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                keywords             JSONB   DEFAULT '[]',
                use_filter           BOOLEAN DEFAULT FALSE,
                summary_mode_auto    TEXT    DEFAULT 'standard',
                summary_mode_manual  TEXT    DEFAULT 'standard',
                enabled_sources      JSONB   DEFAULT '[]',
                auto_enabled_default BOOLEAN DEFAULT FALSE,
                auto_enabled_custom  BOOLEAN DEFAULT FALSE,
                custom_schedules     JSONB   DEFAULT '[]',
                updated_at           TIMESTAMP DEFAULT NOW()
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
            CREATE TABLE IF NOT EXISTS detail_crawl_log (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS briefing_log (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                briefing_mode   TEXT DEFAULT 'standard',
                created_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schedule_change_log (
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schedule_change_log (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # 마이그레이션 (기존 컬럼 호환)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'trial'")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_weekly_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_briefing_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_detail_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_detail_manual_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_detail_auto_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_schedule_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_schedule_change_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS schedule_change_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_schedule_change_limit INTEGER DEFAULT NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS schedule_change_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS manual_crawl_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS detail_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS manual_detail_bonus INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_detail_bonus INTEGER DEFAULT 0")

        # user_settings 마이그레이션
        cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS summary_mode_auto TEXT DEFAULT 'standard'")
        cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS summary_mode_manual TEXT DEFAULT 'standard'")
        cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS auto_enabled_default BOOLEAN DEFAULT FALSE")
        # 구버전 auto_enabled → auto_enabled_default 자동 이전
        cur.execute("""
            UPDATE user_settings
            SET auto_enabled_default = auto_enabled
            WHERE auto_enabled_default = FALSE
              AND auto_enabled = TRUE
        """)
        cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS auto_enabled_custom BOOLEAN DEFAULT FALSE")
        cur.execute("""ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS custom_schedules JSONB DEFAULT '[]'""")
        # briefing_log에 mode 컬럼 추가
        cur.execute("ALTER TABLE briefing_log ADD COLUMN IF NOT EXISTS briefing_mode TEXT DEFAULT 'standard'")
        cur.execute("ALTER TABLE detail_crawl_log ADD COLUMN IF NOT EXISTS crawl_type TEXT DEFAULT 'manual'")

        # 인덱스
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, attempted_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_log_user ON manual_crawl_log(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_detail_log_user ON detail_crawl_log(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_briefing_log_user ON briefing_log(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_schedule_change_user ON schedule_change_log(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_schedule_change_user ON schedule_change_log(user_id, created_at)")

        # 기본 설정값
        defaults = [
            ('trial_weekly_limit',        '15'),
            ('free_weekly_limit',         '30'),
            ('trial_briefing_std_limit',  '5'),
            ('free_briefing_std_limit',   '10'),
            ('trial_briefing_det_limit',  '3'),
            ('free_briefing_det_limit',   '5'),
            ('trial_detail_manual_limit',  '10'),
            ('free_detail_manual_limit',   '20'),
            ('trial_detail_auto_limit',    '10'),
            ('free_detail_auto_limit',     '20'),
            ('max_crawl_hours',              '12'),
            ('trial_custom_schedule_limit',  '0'),
            ('trial_schedule_change_limit',   '0'),
            ('free_schedule_change_limit',    '4'),
            ('free_custom_schedule_limit',   '2'),
            ('trial_schedule_change_limit',  '0'),
            ('free_schedule_change_limit',   '4'),
        ]
        for k, v in defaults:
            cur.execute("INSERT INTO admin_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (k, v))


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

def update_notion_credentials(user_id: int, notion_token_enc, notion_db_id):
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

def update_user_custom_detail_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_detail_limit = %s WHERE user_id = %s", (limit, user_id))

def update_user_custom_detail_manual_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_detail_manual_limit = %s WHERE user_id = %s", (limit, user_id))

def update_user_custom_detail_auto_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_detail_auto_limit = %s WHERE user_id = %s", (limit, user_id))

def update_user_custom_schedule_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_schedule_limit = %s WHERE user_id = %s", (limit, user_id))

def update_user_custom_schedule_change_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_schedule_change_limit = %s WHERE user_id = %s", (limit, user_id))

def record_schedule_change(user_id: int):
    """커스텀 스케줄 추가 시 기록"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO schedule_change_log (user_id) VALUES (%s)", (user_id,))

def get_schedule_change_count(user_id: int, days: int = 28) -> int:
    """최근 N일 내 스케줄 추가 횟수"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM schedule_change_log
            WHERE user_id = %s
              AND created_at > NOW() - INTERVAL '1 day' * %s
        """, (user_id, days))
        return cur.fetchone()[0]

def update_user_custom_schedule_change_limit(user_id: int, limit):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET custom_schedule_change_limit = %s WHERE user_id = %s", (limit, user_id))

def record_schedule_change(user_id: int):
    """지정 시간 추가 행위 기록"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO schedule_change_log (user_id) VALUES (%s)", (user_id,))

def get_recent_schedule_change_count(user_id: int, days: int = 28) -> int:
    """최근 N일 내 지정 시간 추가 횟수"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM schedule_change_log
            WHERE user_id = %s
              AND created_at > NOW() - INTERVAL '1 day' * %s
        """, (user_id, days))
        return cur.fetchone()[0]

def add_user_bonus(user_id: int, bonus_type: str, amount: int):
    """bonus_type: 'manual_crawl_bonus' | 'briefing_bonus' | 'manual_detail_bonus' | 'auto_detail_bonus'"""
    allowed = {'manual_crawl_bonus', 'briefing_bonus', 'manual_detail_bonus', 'auto_detail_bonus'}
    if bonus_type not in allowed:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET {bonus_type} = COALESCE({bonus_type}, 0) + %s WHERE user_id = %s",
            (amount, user_id)
        )

def reset_user_bonus(user_id: int, bonus_type: str):
    allowed = {'manual_crawl_bonus', 'briefing_bonus', 'manual_detail_bonus', 'auto_detail_bonus'}
    if bonus_type not in allowed:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET {bonus_type} = 0 WHERE user_id = %s", (user_id,))

def get_all_users():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT user_id, email, role, is_active, created_at, last_login,
                   notion_db_id,
                   custom_weekly_limit, custom_briefing_limit, custom_detail_limit,
                   custom_detail_manual_limit, custom_detail_auto_limit, custom_schedule_limit, custom_schedule_change_limit, COALESCE(schedule_change_bonus,0) AS schedule_change_bonus, custom_schedule_change_limit, COALESCE(schedule_change_bonus,0) AS schedule_change_bonus,
                   COALESCE(manual_crawl_bonus, 0)   AS manual_crawl_bonus,
                   COALESCE(briefing_bonus, 0)       AS briefing_bonus,
                   COALESCE(manual_detail_bonus, 0)  AS manual_detail_bonus,
                   COALESCE(auto_detail_bonus, 0)    AS auto_detail_bonus,
                   CASE WHEN notion_token_enc IS NOT NULL THEN TRUE ELSE FALSE END AS notion_connected
            FROM users
            ORDER BY created_at DESC
        """)
        return cur.fetchall()


# ─── 세션 ────────────────────────────────────────────────
def create_session(session_id: str, user_id: int, ip_address: str = None, hours: int = 0, minutes: int = 30):
    from datetime import datetime, timedelta
    expires_at = datetime.now() + timedelta(hours=hours, minutes=minutes)
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
              AND attempted_at > NOW() - INTERVAL '1 minute' * %s
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
        diff = unlock_at - datetime.now()
        if diff.total_seconds() <= 0:
            return 0
        return max(0, int(diff.total_seconds() // 60) + 1)


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


# ─── 상세 요약 횟수 ──────────────────────────────────────
def record_detail_crawl(user_id: int, crawl_type: str = 'manual'):
    """crawl_type: 'manual' | 'auto'"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO detail_crawl_log (user_id, crawl_type) VALUES (%s, %s)", (user_id, crawl_type))

def get_weekly_detail_count(user_id: int, crawl_type: str = None) -> int:
    """crawl_type=None이면 전체, 'manual'/'auto'이면 해당 타입만"""
    with get_conn() as conn:
        cur = conn.cursor()
        if crawl_type:
            cur.execute("""
                SELECT COUNT(*) FROM detail_crawl_log
                WHERE user_id = %s AND crawl_type = %s
                  AND created_at >= DATE_TRUNC('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
            """, (user_id, crawl_type))
        else:
            cur.execute("""
                SELECT COUNT(*) FROM detail_crawl_log
                WHERE user_id = %s
                  AND created_at >= DATE_TRUNC('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
            """, (user_id,))
        return cur.fetchone()[0]

# 3. 계정 잠금 해제
def unlock_account(email: str):
    """로그인 실패 기록 삭제 → 잠금 해제"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM login_attempts WHERE email = %s AND success = FALSE",
            (email.lower().strip(),)
        )


# ─── 브리핑 횟수 ─────────────────────────────────────────
def record_briefing(user_id: int, mode: str = 'standard'):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO briefing_log (user_id, briefing_mode) VALUES (%s, %s)", (user_id, mode))

def get_weekly_briefing_count(user_id: int, mode: str = None) -> int:
    """mode=None이면 전체, mode='standard'/'detailed'이면 해당 모드만"""
    with get_conn() as conn:
        cur = conn.cursor()
        if mode:
            cur.execute("""
                SELECT COUNT(*) FROM briefing_log
                WHERE user_id = %s AND briefing_mode = %s
                  AND created_at >= DATE_TRUNC('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
            """, (user_id, mode))
        else:
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
            d = dict(row)
            # 구버전 호환: summary_mode → summary_mode_auto/manual
            if not d.get('summary_mode_auto'):
                d['summary_mode_auto']   = d.get('summary_mode', 'standard')
            if not d.get('summary_mode_manual'):
                d['summary_mode_manual'] = d.get('summary_mode', 'standard')
            # 구버전 호환: auto_enabled → auto_enabled_default
            if not d.get('auto_enabled_default') and d.get('auto_enabled'):
                d['auto_enabled_default'] = True
            return d
        return {
            "keywords": [],
            "use_filter": False,
            "summary_mode_auto": "standard",
            "summary_mode_manual": "standard",
            "enabled_sources": [],
            "auto_enabled_default": False,
            "auto_enabled_custom": False,
            "custom_schedules": [],
        }

def save_settings(user_id: int, settings: dict):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_settings
                (user_id, keywords, use_filter, summary_mode_auto, summary_mode_manual,
                 enabled_sources, auto_enabled_default, auto_enabled_custom,
                 custom_schedules, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET keywords             = EXCLUDED.keywords,
                    use_filter           = EXCLUDED.use_filter,
                    summary_mode_auto    = EXCLUDED.summary_mode_auto,
                    summary_mode_manual  = EXCLUDED.summary_mode_manual,
                    enabled_sources      = EXCLUDED.enabled_sources,
                    auto_enabled_default = EXCLUDED.auto_enabled_default,
                    auto_enabled_custom  = EXCLUDED.auto_enabled_custom,
                    custom_schedules     = EXCLUDED.custom_schedules,
                    updated_at           = NOW()
        """, (
            user_id,
            json.dumps(settings.get("keywords", []), ensure_ascii=False),
            settings.get("use_filter", False),
            settings.get("summary_mode_auto", "standard"),
            settings.get("summary_mode_manual", "standard"),
            json.dumps(settings.get("enabled_sources", []), ensure_ascii=False),
            settings.get("auto_enabled_default", False),
            settings.get("auto_enabled_custom", False),
            json.dumps(settings.get("custom_schedules", []), ensure_ascii=False),
        ))
