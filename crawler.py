import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import os
import re
from openai import OpenAI
import httpx
from notion_client import Client as NotionClient
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# ─── 뉴스 소스 ──────────────────────────────────────────
NEWS_SOURCES = [
    {
        "name": "연합뉴스",
        "url": "https://www.yna.co.kr/economy/all",
        "pattern": r"https://www\.yna\.co\.kr/view/AK[A-Z0-9]+",
        "enabled": True,
    },
    {
        "name": "한국경제",
        "url": "https://www.hankyung.com/economy",
        "pattern": r"https://www\.hankyung\.com/article/[0-9]+",
        "enabled": True,
    },
    {
        "name": "매일경제",
        "url": "https://www.mk.co.kr/news/economy/",
        "pattern": r"https://www\.mk\.co\.kr/news/economy/[0-9]+",
        "enabled": True,
    },
    {
        "name": "서울경제",
        "url": "https://www.sedaily.com/NewsList/GE",
        "pattern": r"https://www\.sedaily\.com/NewsView/[A-Z0-9]+",
        "enabled": True,
    },
    {
        "name": "이데일리",
        "url": "https://www.edaily.co.kr/economy/macro",
        "pattern": r"https://www\.edaily\.co\.kr/news/read\?newsId=[0-9]+",
        "enabled": True,
    },
    {
        "name": "아시아경제",
        "url": "https://www.asiae.co.kr/list/economy",
        "pattern": r"https://www\.asiae\.co\.kr/article/[0-9]+",
        "enabled": True,
    },
    {
        "name": "조선일보",
        "url": "https://www.chosun.com/economy/",
        "pattern": r"https://www\.chosun\.com/economy/[a-z_]+/\d{4}/\d{2}/\d{2}/[A-Z0-9]+/",
        "enabled": True,
    },
    {
        "name": "중앙일보",
        "url": "https://www.joongang.co.kr/money",
        "pattern": r"https://www\.joongang\.co\.kr/article/[0-9]+",
        "enabled": True,
    },
    {
        "name": "동아일보",
        "url": "https://www.donga.com/news/Economy",
        "pattern": r"https://www\.donga\.com/news/Economy/article/all/\d+/[0-9]+/1",
        "enabled": True,
    },
]

# ─── 요약 프롬프트 ───────────────────────────────────────
PROMPT_STANDARD = """당신은 경제 뉴스 전문 요약가입니다. 기사를 읽고 다음 형식으로 간결하게 요약해주세요:

📌 핵심 요약 (2~3줄)

💡 주요 내용
- 포인트 1
- 포인트 2
- 포인트 3

📈 투자/경제 시사점
- 시사점 1
- 시사점 2

쉽고 명확하게 작성해주세요."""

PROMPT_DETAILED = """당신은 경제 뉴스 전문 분석가입니다. 기사를 읽고 다음 형식으로 상세하게 분석해주세요:

📌 핵심 요약 (3~4줄, 배경과 맥락 포함)

💡 주요 내용
- 포인트 1 (구체적 수치/사실 포함)
- 포인트 2 (구체적 수치/사실 포함)
- 포인트 3 (구체적 수치/사실 포함)
- 포인트 4
- 포인트 5

🔍 심층 분석
- 이 뉴스의 배경과 원인
- 관련 산업/시장에 미치는 영향
- 향후 전망

📈 투자/경제 시사점
- 단기 시사점
- 중장기 시사점
- 주목할 리스크 요인

🏢 관련 기업/섹터
- 직접 영향: (관련 기업 또는 섹터)
- 간접 영향: (연관 기업 또는 섹터)

전문적이고 구체적으로 작성해주세요."""

# ─── 시간대 레이블 ───────────────────────────────────────
def get_time_slot_label(time_label, hours=None):
    now = datetime.now(KST)
    today = now.date()
    yesterday = today - timedelta(days=1)

    if time_label == "오전":
        return (f"{today.strftime('%Y-%m-%d')} 오전 "
                f"({yesterday.strftime('%m/%d')} 20:00 ~ {today.strftime('%m/%d')} 07:00)")
    elif time_label == "오후":
        return (f"{today.strftime('%Y-%m-%d')} 오후 "
                f"({today.strftime('%m/%d')} 07:00 ~ {today.strftime('%m/%d')} 20:00)")
    else:
        h = int(hours) if hours else 24
        return f"수동 {now.strftime('%-m/%d일 %H:%M')} (최근 {h}시간)"

# ─── 시간 범위 계산 ──────────────────────────────────────
def get_time_range(time_label, hours=None):
    now = datetime.now(KST).replace(tzinfo=None)
    today = now.date()
    yesterday = today - timedelta(days=1)

    if time_label == "오전":
        start = datetime(yesterday.year, yesterday.month, yesterday.day, 20, 0, 0)
        end = datetime(today.year, today.month, today.day, 7, 0, 0)
    elif time_label == "오후":
        start = datetime(today.year, today.month, today.day, 7, 0, 0)
        end = datetime(today.year, today.month, today.day, 20, 0, 0)
    else:
        h = int(hours) if hours else 24
        start = now - timedelta(hours=h)
        end = now

    return start, end

# ─── Notion 기존 URL 조회 ────────────────────────────────
def get_existing_urls(notion_token, notion_db_id):
    try:
        notion = NotionClient(auth=notion_token)
        existing_urls = set()
        results = notion.databases.query(
            database_id=notion_db_id,
            filter={
                "property": "날짜",
                "date": {"on_or_after": (date.today() - timedelta(days=2)).isoformat()}
            }
        )
        for page in results.get("results", []):
            url = page.get("properties", {}).get("URL", {}).get("url", "")
            if url:
                existing_urls.add(url)
        return existing_urls
    except Exception as e:
        print(f"기존 URL 조회 실패: {e}")
        return set()

# ─── URL 크롤링 ──────────────────────────────────────────
def get_article_urls(source):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(source["url"], headers=headers, timeout=10)
        urls = re.findall(source["pattern"], res.text)
        return list(dict.fromkeys(urls))
    except Exception as e:
        print(f"[{source['name']}] URL 크롤링 실패: {e}")
        return []

# ─── 기사 본문 크롤링 ────────────────────────────────────
def get_article_content(url, summary_mode="standard"):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        title = soup.find("title")
        title = title.text.strip() if title else "제목 없음"
        for suffix in [" - 매일경제", " | 한국경제", " - 서울경제", " - 이데일리",
                       " - 아시아경제", " - 조선일보", " | 중앙일보", " - 동아일보", " - 연합뉴스"]:
            title = title.replace(suffix, "")
        title = title.strip()

        error_keywords = ["페이지를 찾을 수 없", "404", "존재하지 않는", "삭제된 기사"]
        if any(kw in title for kw in error_keywords):
            return None, None, None

        article_date = None
        for selector in ["meta[property='article:published_time']", "meta[name='date']", "time"]:
            el = soup.select_one(selector)
            if el:
                date_str = el.get("content") or el.get("datetime") or el.text
                if date_str:
                    try:
                        article_date = datetime.fromisoformat(date_str[:19])
                        break
                    except Exception:
                        pass

        content = ""
        for selector in [
            "div.news_cnt_detail_wrap", "div#newsDetailDiv", "div.article-body",
            "div#articlebody", "div.article_body", "div#articleBody",
            "section.article-body", "div#article_body", "div.article_txt",
        ]:
            body = soup.select_one(selector)
            if body:
                content = body.get_text(separator="\n").strip()
                break

        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50])

        if len(content) < 100:
            return None, None, None

        max_len = 5000 if summary_mode == "detailed" else 3000
        return title, content[:max_len], article_date

    except Exception as e:
        print(f"기사 크롤링 실패 ({url}): {e}")
        return None, None, None

# ─── 키워드 필터 ─────────────────────────────────────────
def matches_keywords(title, content, keywords):
    if not keywords:
        return True
    text = (title + " " + content).lower()
    return any(kw.lower() in text for kw in keywords)

# ─── AI 경제 기사 분류 ────────────────────────────────────
def is_economy_article(title, content):
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 뉴스 분류 전문가입니다. "
                        "주어진 기사가 경제/금융/산업/기업/부동산/주식/환율/무역 등 "
                        "경제 관련 기사이면 'Y', 정치/사회/문화/스포츠/연예 등 "
                        "비경제 기사이면 'N'만 답하세요. 다른 말은 하지 마세요."
                    )
                },
                {"role": "user", "content": f"제목: {title}\n\n본문 앞부분: {content[:500]}"}
            ],
            max_tokens=5
        )
        return response.choices[0].message.content.strip().upper().startswith("Y")
    except Exception as e:
        print(f"AI 분류 실패 ({e}), 기본 통과")
        return True

# ─── AI 요약 ─────────────────────────────────────────────
def summarize_article(title, content, summary_mode="standard"):
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())
        system_prompt = PROMPT_DETAILED if summary_mode == "detailed" else PROMPT_STANDARD
        max_tokens = 1800 if summary_mode == "detailed" else 1000

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"제목: {title}\n\n본문: {content}"}
            ],
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 요약 실패: {e}")
        return "요약 실패"

# ─── Notion 저장 ─────────────────────────────────────────
def save_to_notion(title, url, summary, source_name, time_slot, notion_token, notion_db_id):
    notion = NotionClient(auth=notion_token)
    base_props = {
        "이름":  {"title": [{"text": {"content": title}}]},
        "URL":   {"url": url},
        "날짜":  {"date": {"start": date.today().isoformat()}},
        "요약":  {"rich_text": [{"text": {"content": summary[:2000]}}]},
        "시간대": {"rich_text": [{"text": {"content": time_slot}}]},
    }
    try:
        notion.pages.create(
            parent={"database_id": notion_db_id},
            properties={**base_props, "상태": {"status": {"name": "읽기 전"}}}
        )
        print(f"✅ Notion 저장 완료: {title[:30]}...")
    except Exception:
        try:
            notion.pages.create(
                parent={"database_id": notion_db_id},
                properties=base_props
            )
            print(f"✅ Notion 저장 완료 (상태 제외): {title[:30]}...")
        except Exception as e:
            print(f"❌ Notion 저장 실패: {e}")

# ─── 메인 실행 ───────────────────────────────────────────
def run_crawler(notion_token, notion_db_id, settings: dict, time_label="오전", hours=None):
    """
    notion_token  : 유저의 Notion access_token
    notion_db_id  : 유저의 Notion DB ID
    settings      : user_settings dict (keywords, use_filter, summary_mode, enabled_sources)
    """
    print(f"\n{'='*50}")
    print(f"📰 경제뉴스 수집 시작 [{time_label}] - {datetime.now(KST).strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    start_time, end_time = get_time_range(time_label, hours=hours)
    time_slot = get_time_slot_label(time_label, hours=hours)

    keywords        = settings.get("keywords", [])
    use_filter      = settings.get("use_filter", False)
    summary_mode    = settings.get("summary_mode", "standard")
    enabled_sources = settings.get("enabled_sources", [s["name"] for s in NEWS_SOURCES])

    print(f"⏰ 수집 범위: {start_time.strftime('%m/%d %H:%M')} ~ {end_time.strftime('%m/%d %H:%M')}")
    print(f"📝 요약 모드: {'상세 분석' if summary_mode == 'detailed' else '기본 요약'}")
    print(f"📡 활성 소스: {', '.join(enabled_sources)}\n")

    if use_filter and keywords:
        print(f"🔍 키워드 필터: {', '.join(keywords)}\n")
    else:
        print("🔍 키워드 필터 없음 (전체 기사)\n")

    existing_urls = get_existing_urls(notion_token, notion_db_id)
    print(f"🔄 기존 저장된 URL: {len(existing_urls)}개\n")

    total_saved = 0
    total_skipped = 0

    for source in NEWS_SOURCES:
        if source["name"] not in enabled_sources:
            print(f"⏭ [{source['name']}] 비활성화됨")
            continue

        print(f"📡 [{source['name']}] 크롤링 중...")
        urls = get_article_urls(source)
        print(f"   → {len(urls)}개 URL 발견")

        for url in urls[:15]:
            if url in existing_urls:
                total_skipped += 1
                continue

            title, content, article_date = get_article_content(url, summary_mode=summary_mode)
            if not title or not content:
                continue

            if article_date:
                if not (start_time <= article_date <= end_time):
                    print(f"   ⏭ 시간 범위 밖: {title[:30]}...")
                    continue

            if use_filter and keywords:
                if not matches_keywords(title, content, keywords):
                    continue

            if not is_economy_article(title, content):
                print(f"   🚫 비경제 기사 스킵: {title[:30]}...")
                continue

            print(f"   📄 처리 중: {title[:40]}...")
            summary = summarize_article(title, content, summary_mode=summary_mode)
            save_to_notion(title, url, summary, source["name"], time_slot, notion_token, notion_db_id)
            existing_urls.add(url)
            total_saved += 1

    print(f"\n✅ 완료! 총 {total_saved}개 저장, {total_skipped}개 중복 건너뜀")
    return total_saved, total_skipped
