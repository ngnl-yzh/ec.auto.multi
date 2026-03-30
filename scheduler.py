from datetime import datetime, timedelta
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


def _get_time_range_for_schedule(schedules: list, current_hour: int, current_minute: int):
    """
    스케줄 목록에서 현재 시간의 수집 범위 계산.
    이전 활성 스케줄 ~ 현재 스케줄 시간.
    """
    now = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)
    today = now.date()
    yesterday = today - timedelta(days=1)

    # 활성화된 스케줄만 시간순 정렬
    active = sorted(
        [s for s in schedules if s.get("enabled", True)],
        key=lambda x: x["hour"] * 60 + x["minute"]
    )

    if not active:
        # 활성 스케줄 없으면 기본 6시간
        return now - timedelta(hours=6), now

    # 현재 스케줄 인덱스 찾기
    cur_idx = None
    for i, s in enumerate(active):
        if s["hour"] == current_hour and s["minute"] == current_minute:
            cur_idx = i
            break

    if cur_idx is None:
        return now - timedelta(hours=6), now

    # 끝 시간 = 현재 스케줄 시간
    end = datetime(today.year, today.month, today.day, current_hour, current_minute, 0)

    # 시작 시간 = 이전 활성 스케줄 시간
    if cur_idx == 0:
        # 첫 번째 스케줄 → 전날 마지막 스케줄 시간부터
        last = active[-1]
        start = datetime(yesterday.year, yesterday.month, yesterday.day, last["hour"], last["minute"], 0)
    else:
        prev = active[cur_idx - 1]
        start = datetime(today.year, today.month, today.day, prev["hour"], prev["minute"], 0)

    return start, end


def _crawl_job(user_id: int, hour: int, minute: int):
    from db import get_user_by_id, get_settings
    from crawler import run_crawler, NEWS_SOURCES, get_time_slot_label
    from security import decrypt_token
    import json

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
            return

        notion_token = decrypt_token(notion_token_enc)

        # 스케줄 목록 로드
        schedules = settings.get("custom_schedules") or []
        if isinstance(schedules, str):
            schedules = json.loads(schedules)

        # 기본값이 없으면 추가
        if not schedules:
            schedules = [
                {"hour": 7,  "minute": 0, "enabled": True, "is_default": True},
                {"hour": 20, "minute": 0, "enabled": True, "is_default": True},
            ]

        # 수집 범위 계산
        start_time, end_time = _get_time_range_for_schedule(schedules, hour, minute)

        # 시간대 레이블
        time_slot = f"{datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d')} {hour:02d}:{minute:02d} ({start_time.strftime('%m/%d %H:%M')} ~ {end_time.strftime('%m/%d %H:%M')})"

        print(f"\n⏰ 자동 실행 [{hour:02d}:{minute:02d}] - user_id={user_id} ({user.get('email','')})")
        print(f"   수집 범위: {start_time.strftime('%m/%d %H:%M')} ~ {end_time.strftime('%m/%d %H:%M')}")

        if not settings.get("enabled_sources"):
            settings["enabled_sources"] = [s["name"] for s in NEWS_SOURCES]

        run_crawler(
            notion_token=notion_token,
            notion_db_id=notion_db_id,
            settings=settings,
            time_label="custom",
            start_time=start_time,
            end_time=end_time,
            time_slot=time_slot,
        )
    except Exception as e:
        print(f"[스케줄] 오류 user_id={user_id}: {e}")


def add_user_jobs(user_id: int, custom_schedules: list = None):
    scheduler = get_scheduler()
    remove_user_jobs(user_id)

    if not custom_schedules:
        custom_schedules = [
            {"hour": 7,  "minute": 0, "enabled": True, "is_default": True},
            {"hour": 20, "minute": 0, "enabled": True, "is_default": True},
        ]

    count = 0
    for i, sch in enumerate(custom_schedules):
        if not sch.get("enabled", True):
            continue
        hour   = sch["hour"]
        minute = sch["minute"]
        scheduler.add_job(
            _crawl_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=KST),
            args=[user_id, hour, minute],
            id=f"{user_id}_sch_{i}", replace_existing=True,
        )
        count += 1

    print(f"✅ 스케줄 등록: user_id={user_id} ({count}개 활성)")


def remove_user_jobs(user_id: int):
    scheduler = get_scheduler()
    # 기존 방식 호환
    for suffix in ("_morning", "_evening"):
        job_id = f"{user_id}{suffix}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    # 새 방식
    for i in range(20):
        job_id = f"{user_id}_sch_{i}"
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
