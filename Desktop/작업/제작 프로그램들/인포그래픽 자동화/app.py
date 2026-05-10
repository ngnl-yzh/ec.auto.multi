import os
import io
import json
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from ai_layout import classify_layout
from wireframe import generate_wireframe
from pdf_renderer import render_infographic, export_pdf

# DB는 선택적으로 연결 (환경변수 없으면 비활성화)
DB_ENABLED = bool(os.environ.get("DATABASE_URL"))
if DB_ENABLED:
    try:
        from db import init_db, save_template, load_templates, save_history, delete_template
        init_db()
    except Exception as e:
        DB_ENABLED = False
        st.warning(f"DB 연결 실패: {e}")

LAYOUT_LABELS = {
    "timeline": "타임라인",
    "compare":  "비교",
    "flow":     "플로우",
    "stats":    "통계/수치",
    "report":   "보고서",
    "list":     "목록",
}

# ──────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="인포그래픽 자동화 툴",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stButton > button { border-radius: 8px; font-weight: 600; }
.step-badge {
    background: #1565C0; color: white; border-radius: 50%;
    width: 28px; height: 28px; display: inline-flex;
    align-items: center; justify-content: center;
    font-weight: bold; font-size: 14px; margin-right: 8px;
}
.section-card {
    background: #F8FBFF; border: 1px solid #90CAF9;
    border-radius: 8px; padding: 12px; margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 세션 상태 초기화
# ──────────────────────────────────────────────
def _init_state():
    defaults = {
        "step": 1,
        "layout_result": None,
        "wireframe_png": None,
        "user_data": {},
        "final_png": None,
        "input_text": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ──────────────────────────────────────────────
# 사이드바: 템플릿 관리
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("📊 인포그래픽 툴")
    st.divider()

    if st.button("🔄 처음부터 시작", use_container_width=True):
        for k in ["step", "layout_result", "wireframe_png", "user_data", "final_png", "input_text"]:
            st.session_state[k] = {"step": 1, "layout_result": None, "wireframe_png": None,
                                    "user_data": {}, "final_png": None, "input_text": ""}.get(k)
        st.rerun()

    st.divider()

    # 진행 단계 표시
    step = st.session_state.step
    steps = [
        ("1단계", "레이아웃 선택"),
        ("2단계", "데이터 입력"),
        ("3단계", "완성 및 다운로드"),
    ]
    for i, (s, desc) in enumerate(steps, 1):
        icon = "✅" if step > i else ("🔵" if step == i else "⚪")
        st.markdown(f"{icon} **{s}** — {desc}")

    st.divider()

    # 저장된 템플릿 불러오기
    if DB_ENABLED:
        st.subheader("📁 저장된 템플릿")
        templates = load_templates()
        if templates:
            for tmpl in templates:
                cols = st.columns([3, 1])
                with cols[0]:
                    if st.button(f"📋 {tmpl['name']}", key=f"tmpl_{tmpl['id']}", use_container_width=True):
                        st.session_state.layout_result = tmpl["section_structure"]
                        st.session_state.layout_result["layout_type"] = tmpl["layout_type"]
                        st.session_state.layout_result["color_theme"] = tmpl["color_theme"]
                        png = generate_wireframe(
                            tmpl["layout_type"],
                            tmpl["section_structure"].get("sections", []),
                            tmpl["color_theme"]
                        )
                        st.session_state.wireframe_png = png
                        st.session_state.step = 2
                        st.rerun()
                with cols[1]:
                    if st.button("🗑", key=f"del_{tmpl['id']}"):
                        delete_template(tmpl["id"])
                        st.rerun()
        else:
            st.caption("저장된 템플릿 없음")
    else:
        st.caption("DB 미연결 — 템플릿 저장 비활성화")


# ──────────────────────────────────────────────
# STEP 1: 입력 → 와이어프레임 미리보기
# ──────────────────────────────────────────────
def step1_ui():
    st.markdown("## <span class='step-badge'>1</span> 인포그래픽 유형 선택", unsafe_allow_html=True)
    st.caption("만들고 싶은 인포그래픽을 자유롭게 설명하세요. AI가 최적의 레이아웃을 추천합니다.")

    col_input, col_preview = st.columns([1, 1], gap="large")

    with col_input:
        user_text = st.text_area(
            "인포그래픽 설명 입력",
            value=st.session_state.input_text,
            placeholder="예) 우리 회사의 2024년 분기별 매출 현황을 보여주는 인포그래픽 만들어줘",
            height=120,
            key="input_text_area"
        )

        color_theme = st.selectbox(
            "색상 테마",
            options=["blue", "green", "orange", "purple", "red", "teal"],
            format_func=lambda x: {"blue": "파랑", "green": "초록", "orange": "주황",
                                    "purple": "보라", "red": "빨강", "teal": "청록"}[x]
        )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            generate_btn = st.button("✨ 레이아웃 생성", type="primary", use_container_width=True)
        with btn_col2:
            regen_btn = st.button("🔄 다른 형태로", use_container_width=True,
                                   disabled=st.session_state.layout_result is None)

        if generate_btn or regen_btn:
            if not user_text.strip():
                st.error("인포그래픽 설명을 입력해주세요.")
                return
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
                return
            st.session_state.input_text = user_text

            with st.spinner("AI가 레이아웃을 분석하는 중..."):
                try:
                    result = classify_layout(user_text)
                    result["color_theme"] = color_theme
                    st.session_state.layout_result = result
                    png = generate_wireframe(result["layout_type"], result["sections"], color_theme)
                    st.session_state.wireframe_png = png
                except Exception as e:
                    st.error(f"오류 발생: {e}")
                    return

        # 레이아웃 정보 표시
        if st.session_state.layout_result:
            r = st.session_state.layout_result
            st.success(f"**레이아웃 타입:** {LAYOUT_LABELS.get(r['layout_type'], r['layout_type'])}")
            with st.expander("섹션 구조 상세"):
                for sec in r.get("sections", []):
                    st.markdown(f"- `{sec['id']}` **{sec['label']}** ({sec['type']})")

            if st.button("✅ 이 레이아웃으로 진행하기", type="primary", use_container_width=True):
                st.session_state.step = 2
                st.rerun()

    with col_preview:
        st.subheader("와이어프레임 미리보기")
        if st.session_state.wireframe_png:
            st.image(st.session_state.wireframe_png, use_container_width=True)
        else:
            st.info("설명을 입력하고 '레이아웃 생성' 버튼을 눌러주세요.")


# ──────────────────────────────────────────────
# STEP 2: 데이터 입력 폼
# ──────────────────────────────────────────────
def _parse_uploaded_file(uploaded_file) -> dict:
    """CSV/Excel에서 첫 번째 컬럼=섹션ID, 두 번째=값으로 파싱."""
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        result = {}
        if len(df.columns) >= 2:
            for _, row in df.iterrows():
                key = str(row.iloc[0]).strip()
                val = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
                result[key] = val
        return result
    except Exception as e:
        st.warning(f"파일 파싱 오류: {e}")
        return {}


def _build_form(layout_result: dict, user_data: dict) -> dict:
    """레이아웃 구조에 맞게 동적 입력 폼 생성. 변경된 데이터 반환."""
    sections = layout_result.get("sections", [])
    layout_type = layout_result.get("layout_type", "list")
    new_data = dict(user_data)

    if layout_type == "compare":
        c1, c2 = st.columns(2)
        with c1:
            new_data["col_a_label"] = st.text_input("왼쪽 열 이름",
                value=user_data.get("col_a_label", "항목 A"), key="col_a_label")
        with c2:
            new_data["col_b_label"] = st.text_input("오른쪽 열 이름",
                value=user_data.get("col_b_label", "항목 B"), key="col_b_label")

    if layout_type == "report":
        new_data["summary"] = st.text_area("요약 / 핵심 내용",
            value=user_data.get("summary", ""), height=80, key="summary_field")

    for sec in sections:
        sid = sec["id"]
        label = sec["label"]
        stype = sec["type"]

        st.markdown(f'<div class="section-card">', unsafe_allow_html=True)

        if layout_type == "compare":
            c1, c2 = st.columns(2)
            with c1:
                new_data[f"{sid}_a"] = st.text_area(
                    f"{label} (왼쪽)",
                    value=user_data.get(f"{sid}_a", ""),
                    height=80, key=f"{sid}_a"
                )
            with c2:
                new_data[f"{sid}_b"] = st.text_area(
                    f"{label} (오른쪽)",
                    value=user_data.get(f"{sid}_b", ""),
                    height=80, key=f"{sid}_b"
                )
        elif stype == "number":
            new_data[sid] = st.text_input(
                f"📊 {label}", value=user_data.get(sid, ""), key=f"input_{sid}",
                placeholder="숫자 또는 수치 입력"
            )
        elif stype == "chart":
            st.caption(f"📈 {label} — 각 줄에 `레이블,값` 형식으로 입력")
            new_data[sid] = st.text_area(
                label, value=user_data.get(sid, ""),
                height=120, key=f"input_{sid}",
                placeholder="1월,100\n2월,150\n3월,200"
            )
        elif stype == "list":
            st.caption(f"📋 {label} — 줄바꿈으로 항목 구분")
            new_data[sid] = st.text_area(
                label, value=user_data.get(sid, ""),
                height=120, key=f"input_{sid}",
                placeholder="항목1\n항목2\n항목3"
            )
        else:
            new_data[sid] = st.text_area(
                f"📝 {label}", value=user_data.get(sid, ""),
                height=100, key=f"input_{sid}"
            )

        st.markdown('</div>', unsafe_allow_html=True)

    return new_data


def step2_ui():
    st.markdown("## <span class='step-badge'>2</span> 데이터 입력", unsafe_allow_html=True)

    layout_result = st.session_state.layout_result
    if not layout_result:
        st.warning("먼저 레이아웃을 선택해주세요.")
        st.session_state.step = 1
        st.rerun()
        return

    col_form, col_preview = st.columns([1, 1], gap="large")

    with col_form:
        r = layout_result
        st.info(f"**레이아웃:** {LAYOUT_LABELS.get(r['layout_type'], r['layout_type'])}  |  "
                f"**색상:** {r.get('color_theme', 'blue')}")

        # 제목 입력
        st.session_state.user_data["__title__"] = st.text_input(
            "📌 인포그래픽 제목",
            value=st.session_state.user_data.get("__title__", ""),
            placeholder=layout_result.get("title_placeholder", "제목을 입력하세요")
        )

        # CSV/Excel 업로드
        with st.expander("📂 파일로 데이터 불러오기 (CSV / Excel)"):
            st.caption("첫 번째 열: 섹션 ID, 두 번째 열: 값")
            uploaded = st.file_uploader("파일 선택", type=["csv", "xlsx", "xls"])
            if uploaded:
                parsed = _parse_uploaded_file(uploaded)
                if parsed:
                    for k, v in parsed.items():
                        st.session_state.user_data[k] = v
                    st.success(f"{len(parsed)}개 항목 불러옴")

        st.divider()

        # 동적 입력 폼
        new_data = _build_form(layout_result, st.session_state.user_data)
        st.session_state.user_data = new_data

        st.divider()
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("◀ 레이아웃 변경", use_container_width=True):
                st.session_state.step = 1
                st.rerun()
        with btn_col2:
            if st.button("미리보기 업데이트 🔄", use_container_width=True):
                _update_preview()

        if st.button("✅ 인포그래픽 완성하기", type="primary", use_container_width=True):
            _update_preview()
            st.session_state.step = 3
            st.rerun()

    with col_preview:
        st.subheader("실시간 미리보기")
        if st.session_state.final_png:
            st.image(st.session_state.final_png, use_container_width=True)
        elif st.session_state.wireframe_png:
            st.image(st.session_state.wireframe_png, use_container_width=True, caption="와이어프레임")
        else:
            st.info("데이터를 입력하면 미리보기가 업데이트됩니다.")


def _update_preview():
    r = st.session_state.layout_result
    if not r:
        return
    with st.spinner("미리보기 생성 중..."):
        png = render_infographic(
            layout_type=r["layout_type"],
            title=st.session_state.user_data.get("__title__", ""),
            sections=r["sections"],
            user_data=st.session_state.user_data,
            color_theme=r.get("color_theme", "blue")
        )
        st.session_state.final_png = png


# ──────────────────────────────────────────────
# STEP 3: 완성 및 다운로드
# ──────────────────────────────────────────────
def step3_ui():
    st.markdown("## <span class='step-badge'>3</span> 완성 및 다운로드", unsafe_allow_html=True)

    if not st.session_state.final_png:
        _update_preview()

    if st.session_state.final_png:
        col_img, col_actions = st.columns([2, 1], gap="large")

        with col_img:
            st.image(st.session_state.final_png, use_container_width=True)

        with col_actions:
            st.subheader("다운로드")

            # PNG 다운로드
            st.download_button(
                label="⬇️ PNG 다운로드",
                data=st.session_state.final_png,
                file_name="infographic.png",
                mime="image/png",
                use_container_width=True
            )

            # PDF 다운로드
            with st.spinner("PDF 변환 중..."):
                pdf_data = export_pdf(st.session_state.final_png)

            if pdf_data != st.session_state.final_png:
                st.download_button(
                    label="⬇️ PDF 다운로드",
                    data=pdf_data,
                    file_name="infographic.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.info("WeasyPrint 미설치 — PNG만 다운로드 가능")

            st.divider()

            # 템플릿 저장
            if DB_ENABLED:
                st.subheader("템플릿 저장")
                tmpl_name = st.text_input("템플릿 이름", placeholder="예) 분기 매출 보고서")
                if st.button("💾 템플릿으로 저장", use_container_width=True):
                    if tmpl_name.strip():
                        r = st.session_state.layout_result
                        save_template(
                            name=tmpl_name,
                            layout_type=r["layout_type"],
                            section_structure=r,
                            color_theme=r.get("color_theme", "blue")
                        )
                        if st.session_state.input_text:
                            save_history(
                                input_text=st.session_state.input_text,
                                data_json=st.session_state.user_data
                            )
                        st.success("저장 완료!")
                    else:
                        st.warning("템플릿 이름을 입력해주세요.")
            else:
                st.caption("DB 미연결 — 템플릿 저장 비활성화")

            st.divider()
            if st.button("🔄 새 인포그래픽 만들기", use_container_width=True):
                for k in ["step", "layout_result", "wireframe_png", "user_data", "final_png", "input_text"]:
                    st.session_state.pop(k, None)
                _init_state()
                st.rerun()
    else:
        st.warning("먼저 데이터를 입력해주세요.")
        if st.button("◀ 데이터 입력으로"):
            st.session_state.step = 2
            st.rerun()


# ──────────────────────────────────────────────
# 라우팅
# ──────────────────────────────────────────────
step = st.session_state.step

if step == 1:
    step1_ui()
elif step == 2:
    step2_ui()
elif step == 3:
    step3_ui()
