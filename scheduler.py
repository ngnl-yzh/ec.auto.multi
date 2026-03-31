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


def _get_time_range_for_schedule(all_schedules: list, current_hour: int, current_minute: int):
    """이전 활성 스케줄 ~ 현재 스케줄 시간 범위 계산"""
    now   = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)
    today = now.date()
    yesterday = today - timedelta(days=1)

    active = sorted(
        [s for s in all_schedules if s.get("enabled", True)],
        key=lambda x: x["hour"] * 60 + x["minute"]
    )

    if not active:
        return now - timedelta(hours=6), now

    cur_idx = next(
        (i for i, s in enumerate(active) if s["hour"] == current_hour and s["minute"] == current_minute),
        None
    )
    if cur_idx is None:
        return now - timedelta(hours=6), now

    end = datetime(today.year, today.month, today.day, current_hour, current_minute, 0)

    if cur_idx == 0:
        last  = active[-1]
        start = datetime(yesterday.year, yesterday.month, yesterday.day, last["hour"], last["minute"], 0)
    else:
        prev  = active[cur_idx - 1]
        start = datetime(today.year, today.month, today.day, prev["hour"], prev["minute"], 0)

    return start, end


def _crawl_job(user_id: int, hour: int, minute: int, job_type: str = "default", range_hours: int = None):
    """
    job_type: 'default' = 기본 스케줄, 'custom' = 커스텀 스케줄
    range_hours: 커스텀 스케줄의 수집 범위 (시간 단위, 직접 지정)
    """
    from db import get_user_by_id, get_settings
    from crawler import run_crawler, NEWS_SOURCES
    from security import decrypt_token
    import json

    try:
        user = get_user_by_id(user_id)
        if not user:
            return

        settings = get_settings(user_id)

        # 활성화 여부 확인 (job_type별로 분리)
        if job_type == "default" and not settings.get("auto_enabled_default", False):
            print(f"[스케줄] 기본 스케줄 비활성 user_id={user_id}")
            return
        if job_type == "custom" and not settings.get("auto_enabled_custom", False):
            print(f"[스케줄] 커스텀 스케줄 비활성 user_id={user_id}")
            return

        notion_token_enc = user.get("notion_token_enc")
        notion_db_id     = user.get("notion_db_id")
        if not notion_token_enc or not notion_db_id:
            print(f"[스케줄] Notion 미설정 user_id={user_id} email={user.get('email','')}")
            return

        notion_token = decrypt_token(notion_token_enc)
        now = datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)

        if job_type == "default":
            # 기본 스케줄: 7시/20시 → 이전 기본 스케줄 시간부터
            default_schedules = [
                {"hour": 7,  "minute": 0, "enabled": True, "is_default": True},
                {"hour": 20, "minute": 0, "enabled": True, "is_default": True},
            ]
            start_time, end_time = _get_time_range_for_schedule(default_schedules, hour, minute)
        else:
            # 커스텀 스케줄: range_hours 설정값 직접 사용 (겹침 무관)
            h = range_hours if range_hours else 6
            end_time   = now
            start_time = now - timedelta(hours=h)

        job_label = "기본 자동" if job_type == "default" else "커스텀 자동"
        time_slot = (
            f"자동 {datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d')} "
            f"{hour:02d}:{minute:02d} "
            f"({start_time.strftime('%m/%d %H:%M')} ~ {end_time.strftime('%m/%d %H:%M')})"
        )

        print(f"\n⏰ [{job_label}] {hour:02d}:{minute:02d} user_id={user_id} email={user.get('email','')}")
        print(f"   수집 범위: {start_time.strftime('%m/%d %H:%M')} ~ {end_time.strftime('%m/%d %H:%M')}")

        if not settings.get("enabled_sources"):
            settings["enabled_sources"] = [s["name"] for s in NEWS_SOURCES]

        summary_mode = settings.get("summary_mode_auto", "standard")

        saved, skipped = run_crawler(
            notion_token=notion_token,
            notion_db_id=notion_db_id,
            settings={**settings, "summary_mode": summary_mode},
            time_label="자동",
            start_time=start_time,
            end_time=end_time,
            time_slot=time_slot,
            user_email=user.get("email", ""),
        )

        # 자동 상세 요약 횟수 기록
        if summary_mode == "detailed" and saved > 0:
            from db import record_detail_crawl
            for _ in range(saved):
                record_detail_crawl(user_id, crawl_type="auto")
        print(f"   ✅ 완료: {saved}개 저장, {skipped}개 중복 건너뜀")
    except Exception as e:
        print(f"[스케줄] 오류 user_id={user_id}: {e}")


def add_user_jobs(user_id: int, settings: dict = None):
    """settings를 받아 기본/커스텀 스케줄 모두 등록"""
    import json
    scheduler = get_scheduler()
    remove_user_jobs(user_id)

    if settings is None:
        from db import get_settings
        settings = get_settings(user_id)

    count = 0

    # 기본 스케줄 (7시, 20시)
    if settings.get("auto_enabled_default", False):
        for hour, minute in [(7, 0), (20, 0)]:
            scheduler.add_job(
                _crawl_job,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=KST),
                args=[user_id, hour, minute, "default"],
                id=f"{user_id}_default_{hour}_{minute}", replace_existing=True,
            )
            count += 1

    # 커스텀 스케줄
    if settings.get("auto_enabled_custom", False):
        custom_schedules = settings.get("custom_schedules") or []
        if isinstance(custom_schedules, str):
            custom_schedules = json.loads(custom_schedules)

        for i, sch in enumerate(custom_schedules):
            if not sch.get("enabled", True):
                continue
            hour       = sch["hour"]
            minute     = sch["minute"]
            rng_hours  = sch.get("range_hours", 6)
            scheduler.add_job(
                _crawl_job,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=KST),
                args=[user_id, hour, minute, "custom", rng_hours],
                id=f"{user_id}_custom_{i}", replace_existing=True,
            )
            count += 1

    print(f"✅ 스케줄 등록 user_id={user_id} ({count}개 활성)")


def remove_user_jobs(user_id: int):
    scheduler = get_scheduler()
    # 구버전 호환
    for suffix in ("_morning", "_evening"):
        jid = f"{user_id}{suffix}"
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
    # 신버전
    for hour, minute in [(7, 0), (20, 0)]:
        jid = f"{user_id}_default_{hour}_{minute}"
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
    for i in range(20):
        jid = f"{user_id}_custom_{i}"
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
    # 구버전 sch 방식 호환
    for i in range(20):
        jid = f"{user_id}_sch_{i}"
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)


def _weekly_bonus_reset_job():
    """매주 월요일 KST 00:05 보너스 리셋"""
    from db import reset_weekly_bonuses
    try:
        reset_weekly_bonuses()
    except Exception as e:
        print(f"[보너스 리셋] 오류: {e}")


def _daily_session_cleanup_job():
    """매일 새벽 3시 KST 만료 세션 정리"""
    from db import cleanup_expired_sessions
    try:
        cleanup_expired_sessions()
        print("✅ 만료 세션 정리 완료")
    except Exception as e:
        print(f"[세션 정리] 오류: {e}")


def sync_all_user_jobs():
    from db import get_conn, get_settings
    import psycopg2.extras
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT u.user_id FROM users u
                JOIN user_settings s ON u.user_id = s.user_id
                WHERE (s.auto_enabled_default = TRUE OR s.auto_enabled_custom = TRUE)
                  AND u.notion_token_enc IS NOT NULL
                  AND u.notion_db_id IS NOT NULL
            """)
            rows = cur.fetchall()
        for row in rows:
            settings = get_settings(row["user_id"])
            add_user_jobs(row["user_id"], settings=settings)
        print(f"✅ 자동화 유저 {len(rows)}명 스케줄 복원")

        # 시스템 job 등록 (보너스 리셋, 세션 정리)
        scheduler = get_scheduler()
        scheduler.add_job(
            _weekly_bonus_reset_job,
            trigger=CronTrigger(day_of_week='mon', hour=0, minute=5, timezone=KST),
            id="system_bonus_reset", replace_existing=True,
        )
        scheduler.add_job(
            _daily_session_cleanup_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=KST),
            id="system_session_cleanup", replace_existing=True,
        )
        print("✅ 시스템 job 등록 (보너스 리셋, 세션 정리)")
    except Exception as e:
        print(f"스케줄 복원 실패: {e}")
