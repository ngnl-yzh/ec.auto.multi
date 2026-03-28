# 📰 경제뉴스 자동화 시스템

매일경제, 한국경제 뉴스를 AI로 요약해서 Notion에 자동 저장하는 시스템입니다.

## 기능
- 매일 오전 7시, 오후 8시 자동 크롤링
- OpenAI gpt-4o-mini로 AI 요약
- 관심 종목 키워드 필터링
- Notion DB 자동 저장
- Streamlit 웹 UI로 설정 관리

## 배포 방법 (Railway)

### 1. GitHub에 올리기
```bash
git init
git add .
git commit -m "초기 커밋"
git remote add origin https://github.com/YOUR_REPO
git push -u origin main
```

### 2. Railway 배포
1. railway.app 접속
2. "New Project" → "Deploy from GitHub repo"
3. 저장소 선택

### 3. 환경변수 설정 (Railway Variables)
```
OPENAI_API_KEY=sk-...
NOTION_TOKEN=secret_...
NOTION_DB_ID=331dd1eacfe6802795bdda03ded3e380
```

### 4. 완료!
Railway URL로 접속하면 웹 UI 사용 가능

## 로컬 실행
```bash
pip install -r requirements.txt
cp .env.example .env
# .env 파일에 API 키 입력
python main.py
```
