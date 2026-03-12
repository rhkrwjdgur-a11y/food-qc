import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

# ==========================================
# [보안] 비밀번호 설정
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == "2082":  
            st.session_state["password_correct"] = True
            del st.session_state["password"]  
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("🔒 관계자 외 접속 금지 (비밀번호 입력)", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 비밀번호가 틀렸습니다. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

# ==========================================
# 1. API 키 설정
# ==========================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 2. 통합 전문가 프롬프트 (조건부 검토 로직 추가)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오.

---

[⚠️ 상황별 맞춤 검토 대원칙]
**중요:** 사용자가 [시험성적서]나 [배합비]를 업로드하지 않은 경우, 환산 및 대조 작업은 생략하고 **오직 업로드된 '시안 이미지' 자체의 법적 표기 형식, 오타, 표시기준 위반 여부(예: 알레르기 음영 누락, 용도명 누락 등)**에만 집중하여 검토하십시오.

[⚠️ 영양성분 및 원재료 검증 절대 법칙 (Rule 11 ~ 15)]
✅ **Rule 11. 영양정보 팩트 체크 (성적서 제공 시에만 2~3단계 수행)**
   - **[1단계]** 영양성분표 이미지의 픽셀을 판독하여 함량과 비율(%) 추출.
   - **[2단계]** 성적서가 있다면, 열량(5kcal 단위), 나트륨(120mg 이하 5mg 단위), 탄/당/단/지(0.5g 미만 0) 등 법적 단위로 환산.
   - **[3단계]** 비타민·무기질은 80% 허용오차 내 보수적 표기(하향 표기) 시 ✅적합 판정.
   - **[4단계]** 비율(%)은 시안의 표기 함량 기준으로 수학적으로 오차 없이 정확히 계산되어야 함.

✅ **Rule 12. 배합비 대조 (배합비 제공 시에만 수행)**
   - 5% 미만 복합원재료 하위 원재료 생략 가능 코칭. 단, 알레르기(우유)는 필수 표기.

✅ **Rule 13. 알레르기 텍스트+디자인(음영)**
   - 시안에서 'OO 함유' 글자 확인 및 바탕색/테두리 스캔 (항상 필수).

✅ **Rule 14. 첨가물 용도명 병기**
   - 감미료 옆 '(감미료)' 명시 확인 (항상 필수).

✅ **Rule 15. 강조표시 및 과대광고 연쇄 검증 (기타면 포함)**
   - 영양표 수치가 0이 아닌데 'ZERO'라고 적혀있으면 🚨부적합.
   - 기타면(측면)에 건강기능식품으로 오인할 수 있는 과대광고(질병 예방/치료 등)가 있는지 스캔.

---
[📝 결과 보고서 5단계 작성 양식]
## 1️⃣ [주표시면 및 기타면]
- 강조표시(ZERO 등) 및 기타면의 효능/기능성 마케팅 문구 적정성 검토.

## 2️⃣ [영양표시]
- 📊 **영양성분 팩트 체크 표** (7컬럼 유지. 성적서 미제공 시 성적서/환산값/법적정답 칸은 '-'로 표기하고 시안 표기 형식 위주로 점검)
| 성분명 | 성적서 | 환산값 | 법적 단위 적용 정답 | 시안 표기값 | 판정 | 비고 |
- 세부 분석.

## 3️⃣ [정보표시면]
- 식품유형, 알레르기 표시 양식, 첨가물 용도명 위주로 검토 (배합비 미제공 시 대조 생략 안내).

## 4️⃣ [기타사항]
- 기타 의무 표시사항 검토.

## 5️⃣ [종합의견]
- 종합 적합 여부 및 최우선 수정 지시사항.
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (문서 선택형 업로드)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 분할 이미지 (필수)")
        main_img = st.file_uploader("1. 주표시면 (앞면) - 필수", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면) - 필수", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대 컷) - 필수", type=["jpg", "png", "jpeg"])
        extra_img = st.file_uploader("4. 기타면 (측면/효능 등) - 선택", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서 (선택)")
        st.info("💡 액상차, 우유류 등 성적서/배합비가 불필요한 경우 생략 가능합니다.")
        lab_report = st.file_uploader("5. 시험성적서 - 선택", type=["pdf"])
        recipe_doc = st.file_uploader("6. 원재료 명세서/배합비 - 선택", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 QC 정밀 진단 시작", type="primary"):
        # 필수 항목(시안 3종)만 체크
        if not (main_img and info_img and nutri_img):
            st.warning("⚠️ 정확한 분석을 위해 최소한 시안 3장(주표시, 정보표시, 영양표시)은 필수로 업로드해주세요!")
            return

        user_content = []
        def add_file(f, label):
            if f:
                if f.type.startswith("image"):
                    user_content.append(f"<{label} 이미지>")
                    user_content.append(Image.open(f))
                else:
                    temp = f"temp_{f.name}"
                    with open(temp, "wb") as file: file.write(f.getbuffer())
                    uploaded = genai.upload_file(temp)
                    while uploaded.state.name == "PROCESSING": time.sleep(1); uploaded = genai.get_file(uploaded.name)
                    user_content.append(f"<{label} 문서>")
                    user_content.append(uploaded)

        with st.spinner("업로드된 자료 기반으로 전방위 교차 검증 중..."):
            # 필수
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            # 선택
            if extra_img: add_file(extra_img, "기타면")
            if lab_report: add_file(lab_report, "시험성적서")
            if recipe_doc: add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            업로드된 시안과 문서를 교차 검증하라.
            만약 시험성적서나 배합비가 없다면, 없는 문서에 대해 환각(지어내기)을 일으키지 말고 "자료 미제공으로 대조 검증 생략"이라고 명시해라.
            이 경우 제공된 시안 이미지 자체의 법적 흠결(강조표시 기준 위반, 알레르기 음영 누락, 첨가물 용도명 누락 등)만 집중적으로 점검하여 5단계 보고서를 완성해라.
            """
            
            pdf_refs = []
            for pf in glob.glob("*.pdf"):
                if "temp_" not in pf:
                    ref = genai.upload_file(pf)
                    while ref.state.name == "PROCESSING": time.sleep(1); ref = genai.get_file(ref.name)
                    pdf_refs.append(ref)

            response = model.generate_content(pdf_refs + user_content + [final_prompt])
            
            st.success("분석 완료!")
            st.markdown(response.text)
            
            for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password():
        main()
