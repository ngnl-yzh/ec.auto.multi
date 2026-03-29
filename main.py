import subprocess
import os
from db import init_db, cleanup_expired_sessions
from scheduler import sync_all_user_jobs

if __name__ == "__main__":
    print("🚀 경제뉴스 자동화 (멀티버전) 시작!")

    # 필수 환경변수 체크
    required = ["DATABASE_URL", "OPENAI_API_KEY", "ENCRYPTION_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"❌ 필수 환경변수 누락: {', '.join(missing)}")
        exit(1)

    print("📦 DB 초기화 중...")
    init_db()
    print("✅ DB 초기화 완료")

    print("🧹 만료 세션 정리 중...")
    cleanup_expired_sessions()

    print("⏰ 스케줄 복원 중...")
    sync_all_user_jobs()

    port = os.environ.get("PORT", "8501")
    print(f"🌐 웹앱 시작 (port={port})")
    subprocess.run([
        "streamlit", "run", "app.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
    ])
