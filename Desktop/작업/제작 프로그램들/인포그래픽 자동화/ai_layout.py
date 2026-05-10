import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM_PROMPT = """당신은 인포그래픽 레이아웃 전문가입니다.
사용자의 입력을 분석해 적절한 레이아웃 타입과 섹션 구조를 JSON으로만 반환하세요.

레이아웃 타입 규칙:
- timeline: 순서, 단계, 연혁, 과정, 역사, 절차 키워드
- compare: 비교, vs, 차이, 장단점, 비교분석 키워드
- flow: 프로세스, 흐름, 절차, 워크플로우, 방법 키워드
- stats: 통계, 수치, 매출, 현황, 결과, 데이터, 성과 키워드
- report: 보고서, 결과보고, 행사, 회의, 결과물 키워드
- list: 목록, 항목, 특징, 종류, 유형, 리스트 키워드

반환 형식 (JSON만, 다른 텍스트 없음):
{
  "layout_type": "stats",
  "title_placeholder": "제목을 입력하세요",
  "sections": [
    {"id": "section_1", "label": "섹션 이름", "type": "number|text|list|chart"},
    ...
  ],
  "color_theme": "blue|green|orange|purple|red|teal"
}

섹션 타입:
- number: 숫자/수치 입력
- text: 텍스트 설명 입력
- list: 여러 항목 목록 입력
- chart: 차트 데이터 입력 (레이블,값 형태)

규칙:
- 섹션은 최소 2개, 최대 8개
- 섹션 이름은 사용자 입력 내용에 맞게 구체적으로
- 내용 자체는 절대 생성하지 말고 구조만 반환
- JSON 외 어떤 텍스트도 출력하지 말 것"""


def classify_layout(user_input: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content)
    return _validate_and_normalize(result)


def _validate_and_normalize(data: dict) -> dict:
    valid_layouts = {"timeline", "compare", "flow", "stats", "report", "list"}
    valid_types = {"number", "text", "list", "chart"}
    valid_themes = {"blue", "green", "orange", "purple", "red", "teal"}

    if data.get("layout_type") not in valid_layouts:
        data["layout_type"] = "list"

    if "title_placeholder" not in data:
        data["title_placeholder"] = "제목을 입력하세요"

    if "color_theme" not in data or data["color_theme"] not in valid_themes:
        data["color_theme"] = "blue"

    sections = data.get("sections", [])
    normalized = []
    for i, sec in enumerate(sections[:8]):
        normalized.append({
            "id": sec.get("id", f"section_{i+1}"),
            "label": sec.get("label", f"섹션 {i+1}"),
            "type": sec.get("type", "text") if sec.get("type") in valid_types else "text"
        })
    if not normalized:
        normalized = [
            {"id": "section_1", "label": "항목 1", "type": "text"},
            {"id": "section_2", "label": "항목 2", "type": "text"}
        ]
    data["sections"] = normalized
    return data
