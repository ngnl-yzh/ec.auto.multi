@echo off
echo 인포그래픽 자동화 툴 실행 중...
cd /d %~dp0
streamlit run app.py --server.port 8501
pause
