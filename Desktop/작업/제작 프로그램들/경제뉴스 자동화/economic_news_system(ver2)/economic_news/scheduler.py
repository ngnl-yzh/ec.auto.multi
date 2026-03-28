import schedule
import time
import threading
from datetime import datetime
from crawler import run_crawler

def job_morning():
    print(f"\n⏰ 오전 7시 자동 실행 - {datetime.now()}")
    run_crawler(time_label="오전")

def job_evening():
    print(f"\n⏰ 오후 8시 자동 실행 - {datetime.now()}")
    run_crawler(time_label="오후")

def run_scheduler():
    schedule.every().day.at("07:00").do(job_morning)
    schedule.every().day.at("20:00").do(job_evening)

    print("✅ 스케줄러 시작!")
    print("   - 오전 7:00 자동 실행")
    print("   - 오후 8:00 자동 실행")

    while True:
        schedule.run_pending()
        time.sleep(60)

def start_scheduler_thread():
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    run_scheduler()
