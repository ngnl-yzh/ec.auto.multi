import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
import json
import os
import re
from openai import OpenAI
from notion_client import Client as NotionClient

# ─── 환경변수 ───────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID")
KEYWORDS_FILE = "keywords.json"

# ─── 뉴스 소스 ──────────────────────────────────────────
NEWS_SOURCES = [
    {
        "name": "매일경제",
        "url": "https://www.mk.co.kr/news/economy/",
        "pattern": r"https://www\.mk\.co\.kr/news/economy/\d+",
    },
    {
        "name": "한국경제",
        "url": "https://www.hankyung.com/economy",
        "pattern": r"https://www\.hankyung\.com/article/\d+",
    },
]

# ─── 키워드 로드/저장 ────────────────────────────────────
def load_keywords():
    if os.path.exists(KEYWORDS_FILE):
        with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"keywords": [], "use_filter": False}

def save_keywords(data):
    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── URL 크롤링 ──────────────────────────────────────────
def get_article_urls(source):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(source["url"], headers=headers, timeout=10)
        urls = re.findall(source["pattern"], res.text)
        # 중복 제거
        return list(dict.fromkeys(urls))
    except Exception as e:
        print(f"[{source['name']}] URL 크롤링 실패: {e}")
        return []

# ─── 기사 본문 크롤링 ────────────────────────────────────
def get_article_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        # 제목
        title = soup.find("title")
        title = title.text.strip() if title else "제목 없음"
        title = title.replace(" - 매일경제", "").replace(" | 한국경제", "").strip()

        # 본문
        content = ""
        for selector in ["div.news_cnt_detail_wrap", "div#newsDetailDiv", "div.article-body", "div#articlebody"]:
            body = soup.select_one(selector)
            if body:
                content = body.get_text(separator="\n").strip()
                break

        if not content:
            # 일반적인 p 태그에서 추출
            paragraphs = soup.find_all("p")
            content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50])

        return title, content[:3000]  # 최대 3000자
    except Exception as e:
        print(f"기사 크롤링 실패 ({url}): {e}")
        return None, None

# ─── 키워드 필터 ─────────────────────────────────────────
def matches_keywords(title, content, keywords):
    if not keywords:
        return True
    text = (title + " " + content).lower()
    return any(kw.lower() in text for kw in keywords)

# ─── AI 요약 ─────────────────────────────────────────────
def summarize_article(title, content):
    try:
        import httpx
        client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 경제 뉴스 전문 요약가입니다. 기사를 읽고 다음 형식으로 요약해주세요:

📌 핵심 요약 (2~3줄)

💡 주요 내용
- 포인트 1
- 포인트 2
- 포인트 3

📈 투자/경제 시사점
- 시사점 1
- 시사점 2

쉽고 명확하게 작성해주세요."""
                },
                {
                    "role": "user",
                    "content": f"제목: {title}\n\n본문: {content}"
                }
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 요약 실패: {e}")
        return "요약 실패"

# ─── Notion 저장 ─────────────────────────────────────────
def save_to_notion(title, url, summary, source_name):
    try:
        notion = NotionClient(auth=NOTION_TOKEN)
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "이름": {
                    "title": [{"text": {"content": title}}]
                },
                "URL": {
                    "url": url
                },
                "날짜": {
                    "date": {"start": date.today().isoformat()}
                },
                "상태": {
                    "status": {"name": "읽기 전"}
                },
                "요약": {
                    "rich_text": [{"text": {"content": summary[:2000]}}]
                },
            }
        )
        print(f"✅ Notion 저장 완료: {title[:30]}...")
    except Exception as e:
        print(f"❌ Notion 저장 실패: {e}")

# ─── 메인 실행 ───────────────────────────────────────────
def run_crawler(time_label="오전"):
    print(f"\n{'='*50}")
    print(f"📰 경제뉴스 자동화 시작 [{time_label}] - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # 키워드 설정 로드
    config = load_keywords()
    keywords = config.get("keywords", [])
    use_filter = config.get("use_filter", False)

    if use_filter and keywords:
        print(f"🔍 관심 키워드 필터: {', '.join(keywords)}\n")
    else:
        print("🔍 키워드 필터 없음 (전체 기사)\n")

    total_saved = 0

    for source in NEWS_SOURCES:
        print(f"📡 [{source['name']}] 크롤링 중...")
        urls = get_article_urls(source)
        print(f"   → {len(urls)}개 URL 발견")

        for url in urls[:10]:  # 소스당 최대 10개
            title, content = get_article_content(url)
            if not title or not content:
                continue

            # 키워드 필터 적용
            if use_filter and keywords:
                if not matches_keywords(title, content, keywords):
                    continue

            print(f"   📄 처리 중: {title[:40]}...")
            summary = summarize_article(title, content)
            save_to_notion(title, url, summary, source["name"])
            total_saved += 1

    print(f"\n✅ 완료! 총 {total_saved}개 기사 저장됨")

if __name__ == "__main__":
    run_crawler()
