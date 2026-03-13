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
# 2. 통합 전문가 프롬프트 (Rule 1~27 완결판)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오.

[⚠️ 업로드 자료 가변성에 따른 검토 지침]
- 사용자가 시안 이미지나 문서를 전부 또는 일부 생략할 수 있습니다.
- 업로드되지 않은 자료를 지어내어(환각) 평가하지 마십시오.

---
[⚠️ 검토 대원칙: 27대 특수 지침 (Full Version)]

✅ **Rule 1~20, 22, 24, 25, 26.** (기존 룰 동일 유지)
🔥 **Rule 23.** 트랜스지방 '0.5g' 표기 시 부적합 강제 및 AI 자체 역산 절대 금지.
🔥 **Rule 27.** 당류/지방 등 제한 영양성분 100kcal 적용 절대 금지.

🔥 **Rule 21. [권장 영양성분 4중 조건 구제 룰 및 단백질 절대 수치 강제]**
   - **[절대 금지]** AI 당신이 임의로 법적 수치를 지어내지 마십시오. (예: 100g당 6g, 100kcal당 3g 등은 완벽한 거짓말입니다.)
   - **단백질의 '고/풍부' 강조표시 절대 커트라인 (1일 기준치 55g 적용):**
     1) **100g당 (고체)**: **11g 이상**
     2) **100mL당 (액체)**: **5.5g 이상**
     3) **100kcal당**: **5.5g 이상**
     4) **1회 섭취참고량당**: **11g 이상**
   - 위 4가지 기준 중 단 하나라도 충족하면 ✅적합으로 판정하십시오. 단백질 함량이 위 수치에 미달하는데 '고단백'을 썼을 때만 부적합 처리하십시오.

---
[📝 결과 보고서 5단계 작성 양식]
## 1️⃣ [주표시면 및 기타면]
## 2️⃣ [영양표시] (묶음 포장인 경우 1개당/총량 기준 명시)
- 📊 **영양성분 팩트 체크 표**
## 3️⃣ [정보표시면]
## 4️⃣ [기타사항]
## 5️⃣ [종합의견]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (Rule 1~27 완결판)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 분할 이미지 (모두 선택사항)")
        main_img = st.file_uploader("1. 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
        extra_img = st.file_uploader("4. 기타면 (측면/효능 등)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서 (모두 선택사항)")
        lab_report = st.file_uploader("5. 시험성적서", type=["pdf"])
        recipe_doc = st.file_uploader("6. 원재료 명세서/배합비", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 QC 정밀 진단 시작", type="primary"):
        if not any([main_img, info_img, nutri_img, extra_img, lab_report, recipe_doc]):
            st.warning("⚠️ 검토할 자료(이미지 또는 문서)를 최소 1개 이상 업로드해주세요!")
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

        with st.spinner("업로드된 자료를 분석하여 맞춤형 QC를 진행합니다..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(extra_img, "기타면")
            add_file(lab_report, "시험성적서")
            add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            업로드된 자료만 가지고 평가해라.
            특히 영양강조표시를 검토할 때 Rule 21에 명시된 단백질 절대 수치(11g, 5.5g)를 반드시 기준으로 삼아서 평가하고, 절대 임의로 다른 숫자를 지어내지 마라.
            """
            
            pdf_refs = []
            for pf in glob.glob("*.pdf"):
                if "temp_" not in pf:
                    ref = genai.upload_file(pf)
                    while ref.state.name == "PROCESSING": time.sleep(1); ref = genai.get_file(ref.name)
                    pdf_refs.append(ref)

            response = model.generate_content(pdf_refs + user_content + [final_prompt])
            
            st.markdown("### 📋 AI 정밀 QC 검토 리포트")
            st.markdown(response.text)
            
            for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password():
        main()
