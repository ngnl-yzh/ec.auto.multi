from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

KST = ZoneInfo('Asia/Seoul')
_scheduler = None

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone=KST)
        _scheduler.start()
        print("✅ APScheduler 시작 (KST)")
    return _scheduler

def _crawl_job(user_id: int):
    from db import get_user_by_id, get_settings
    from crawler import run_crawler, NEWS_SOURCES
    from security import decrypt_token

    try:
        user = get_user_by_id(user_id)
        if not user:
            return

        settings = get_settings(user_id)
        if not settings.get("auto_enabled", False):
            return

        notion_token_enc = user.get("notion_token_enc")
        notion_db_id     = user.get("notion_db_id")
        if not notion_token_enc or not notion_db_id:
            print(f"[스케줄] Notion 미설정 user_id={user_id}")
            return

        notion_token = decrypt_token(notion_token_enc)

        hour = datetime.now(KST).hour
        time_label = "오전" if hour < 12 else "오후"
        print(f"\n⏰ 자동 실행 [{time_label}] - user_id={user_id} ({user.get('email','')})")

        if not settings.get("enabled_sources"):
            settings["enabled_sources"] = [s["name"] for s in NEWS_SOURCES]

        run_crawler(
            notion_token=notion_token,
            notion_db_id=notion_db_id,
            settings=settings,
            time_label=time_label,
        )
    except Exception as e:
        print(f"[스케줄] 오류 user_id={user_id}: {e}")

def add_user_jobs(user_id: int):
    scheduler = get_scheduler()
    remove_user_jobs(user_id)
    scheduler.add_job(
        _crawl_job,
        trigger=CronTrigger(hour=7, minute=0, timezone=KST),
        args=[user_id], id=f"{user_id}_morning", replace_existing=True,
    )
    scheduler.add_job(
        _crawl_job,
        trigger=CronTrigger(hour=20, minute=0, timezone=KST),
        args=[user_id], id=f"{user_id}_evening", replace_existing=True,
    )
    print(f"✅ 스케줄 등록: user_id={user_id}")

def remove_user_jobs(user_id: int):
    scheduler = get_scheduler()
    for suffix in ("_morning", "_evening"):
        job_id = f"{user_id}{suffix}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

def sync_all_user_jobs():
    from db import get_conn
    import psycopg2.extras
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT u.user_id FROM users u
                JOIN user_settings s ON u.user_id = s.user_id
                WHERE s.auto_enabled = TRUE
                  AND u.notion_token_enc IS NOT NULL
                  AND u.notion_db_id IS NOT NULL
            """)
            rows = cur.fetchall()
        for row in rows:
            add_user_jobs(row["user_id"])
        print(f"✅ 자동화 유저 {len(rows)}명 스케줄 복원")
    except Exception as e:
        print(f"스케줄 복원 실패: {e}")
