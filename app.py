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

✅ **Rule 1~10. 기본 검증 룰** (원산지 예외, 향료, 영양/강조 이원화, 5%룰, 식품유형 등)
✅ **Rule 11. 영양정보 팩트 체크 및 고시 세부 단위 절대 법칙**
✅ **Rule 12. 배합비 대조 검증 및 생략 코칭**
✅ **Rule 13, 14, 15. 알레르기, 용도명, 강조표시 연쇄 불합격 스캔**
🆕 **Rule 16~20. 원산지/첨가물/명칭/무당/재질명 룰**
🆕 **Rule 22. [다국어 폰트 크기]** 영문이 한글보다 크면 부적합 코칭.
🔥 **Rule 23. [영양성분 0 표기 특수 룰]** 트랜스지방 0.5g 미만 강제, 묶음 역산 주의.
🔥 **Rule 24. [제로 마케팅 방지법]** 무가당 강조 시 열량 문구 의무 표기.
🔥 **Rule 25. [다중 포장 듀얼 스캔]** 1개당/총량 혼동 금지.
🔥 **Rule 26. [고체(g) vs 액체(mL) 단위 엄격 구분]**

🔥 **Rule 21. [권장 영양성분(단백질/비타민/무기질/식이섬유) 4중 조건 구제 룰]**
   - **단백질, 식이섬유, 비타민, 무기질**의 '고/풍부/함유/급원' 강조표시를 검토할 때는 다음 4가지 기준(100g당, 100mL당, 100kcal당, 1회섭취참고량당)을 모두 계산하십시오.
   - 단 하나라도 충족하면 ✅적합으로 판정하고, 어떤 기준으로 합격했는지 명시하십시오. (예: 100kcal 환산 기준 충족)

🔥 **Rule 27. [제한 영양성분(당류/지방/나트륨 등) 100kcal 적용 절대 금지 룰]**
   - **당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨**의 '무(Free)' 또는 '저(Low)' 강조표시를 검토할 때는 **절대 100kcal 기준이나 1회 섭취량 기준을 적용하지 마십시오.**
   - 오직 해당 식품의 제형에 맞춰 **100g당(고체) 또는 100mL당(액체)** 기준만 매우 엄격하게 적용하여 초과 시 🚨부적합 처리하십시오.

---
[📝 결과 보고서 5단계 작성 양식]
## 1️⃣ [주표시면 및 기타면]
## 2️⃣ [영양표시]
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
            특히 영양강조표시를 검토할 때 Rule 21(단백질 등은 100kcal 허용)과 Rule 27(당/지방 등은 100kcal 허용 불가)을 명확하게 분리해서 똑똑하게 계산해라.
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
