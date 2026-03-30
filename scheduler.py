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

def _crawl_job(user_id: int, time_label: str = None, hours: int = None):
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

        if not time_label:
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
            hours=hours,
        )
    except Exception as e:
        print(f"[스케줄] 오류 user_id={user_id}: {e}")


def add_user_jobs(user_id: int, custom_schedules: list = None):
    """
    기본 스케줄(오전 7시, 오후 8시) + 커스텀 스케줄 등록
    custom_schedules: [{"hour": 12, "minute": 30}, ...]
    """
    scheduler = get_scheduler()
    remove_user_jobs(user_id)

    # 기본 스케줄
    scheduler.add_job(
        _crawl_job,
        trigger=CronTrigger(hour=7, minute=0, timezone=KST),
        args=[user_id, "오전"],
        id=f"{user_id}_morning", replace_existing=True,
    )
    scheduler.add_job(
        _crawl_job,
        trigger=CronTrigger(hour=20, minute=0, timezone=KST),
        args=[user_id, "오후"],
        id=f"{user_id}_evening", replace_existing=True,
    )

    # 커스텀 스케줄
    if custom_schedules:
        for i, sch in enumerate(custom_schedules):
            hour        = sch.get("hour", 0)
            minute      = sch.get("minute", 0)
            range_hours = sch.get("range_hours", 5)
            scheduler.add_job(
                _crawl_job,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=KST),
                args=[user_id, "수동", range_hours],
                id=f"{user_id}_custom_{i}", replace_existing=True,
            )

    print(f"✅ 스케줄 등록: user_id={user_id} (기본 2개 + 커스텀 {len(custom_schedules or [])}개)")


def remove_user_jobs(user_id: int):
    scheduler = get_scheduler()
    # 기본 job 제거
    for suffix in ("_morning", "_evening"):
        job_id = f"{user_id}{suffix}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    # 커스텀 job 제거 (최대 10개)
    for i in range(10):
        job_id = f"{user_id}_custom_{i}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)


def sync_all_user_jobs():
    from db import get_conn
    import psycopg2.extras
    import json
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT u.user_id, s.custom_schedules
                FROM users u
                JOIN user_settings s ON u.user_id = s.user_id
                WHERE s.auto_enabled = TRUE
                  AND u.notion_token_enc IS NOT NULL
                  AND u.notion_db_id IS NOT NULL
            """)
            rows = cur.fetchall()
        for row in rows:
            custom = row.get("custom_schedules") or []
            if isinstance(custom, str):
                custom = json.loads(custom)
            add_user_jobs(row["user_id"], custom_schedules=custom)
        print(f"✅ 자동화 유저 {len(rows)}명 스케줄 복원")
    except Exception as e:
        print(f"스케줄 복원 실패: {e}")
