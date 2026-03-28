import subprocess
import threading
import time
import os
from scheduler import start_scheduler_thread

def run_streamlit():
    port = os.environ.get("PORT", "8501")
    subprocess.run([
        "streamlit", "run", "app.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ])

if __name__ == "__main__":
    print("🚀 경제뉴스 자동화 시스템 시작!")
    
    # 스케줄러 백그라운드 실행
    start_scheduler_thread()
    print("✅ 스케줄러 백그라운드 실행 중...")
    
    # Streamlit 웹앱 실행
    print("✅ 웹앱 시작 중...")
    run_streamlit()
