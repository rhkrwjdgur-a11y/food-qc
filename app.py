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
# 2. 통합 전문가 프롬프트 (실무적 하향 표기 로직 추가)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
사용자가 각 항목별로 업로드한 이미지와 문서를 교차 검증하십시오.

---

[⚠️ 검토 대원칙: 15대 특수 지침 (Final Version)]

✅ Rule 1 ~ 10 (생략: 기존과 동일 유지)

🆕 **Rule 11. 영양성분 교차 검증 (실무적 하향 표기 및 0 표기 절대 룰)**
   - **[비타민·무기질 실무 허용 룰]:** 비타민과 무기질은 수학적 반올림(예: 1.197 -> 1.2)보다 더 낮은 수치(예: 1.0)로 표시하는 것을 **'보수적 적합'**으로 판정하십시오.
     * 사유: 실제 함량보다 낮게 표시하는 것은 법적 허용오차(측정값 80% 이상)를 준수하는 데 유리하며, 기준치와 단위를 맞추기 위한 실무적 판단입니다.
     * 판토텐산 환산값이 1.197mg일 때 시안이 1.0mg(20%)으로 적혀 있다면 "불일치"가 아닌 **"보수적 표기 및 기준치 단위 통일에 따른 적합"**으로 판정하십시오.
   
   - **[영양성분 0g 표시 절대 기준]:**
     * 열량: 5kcal 미만은 '0' 표시 가능.
     * 탄수화물, 당류, 지방, 단백질: **0.5g 미만은 무조건 '0g'** 표시 가능 (0.114g 등은 0g 적합).
     * 나트륨: 5mg 미만은 '0mg' 표시 가능.

   - **[시안 강제 읽기]:** 성적서를 베껴 쓰지 말고, 시안 이미지 속 영양정보표 숫자를 직접 읽으십시오.

✅ Rule 12 ~ 14 (생략: 기존과 동일 유지)

✅ **Rule 15. 강조표시 연쇄 불합격 팩트 폭격 룰**
   - 앞면에 'ZERO'나 '무'로 강조된 성분이 있다면, Rule 11의 기준에 따라 환산된 최종값이 진짜 '0'인지 대조하십시오.
   - 열량 환산값이 5kcal 이상(예: 6.95kcal)이라면 시안의 0kcal 표기와 앞면의 ZERO 강조표시는 모두 **🚨부적합**입니다.

---
[📝 결과 보고서 작성 양식]
## 0️⃣ [시험성적서 및 원재료 명세서 교차 검증]
   - 📊 영양성분 팩트 체크 표 (시안 실제 표기값 vs 법적 정답 vs 실무적 적합 판정)
## 1️⃣ 주표시면 검토
## 2️⃣ 정보표시면 검토
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터 (Professional)", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (실무 최적화 버전)")
    st.markdown("---")

    # 업로드 섹션 분리
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 이미지")
        main_img = st.file_uploader("1. 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서")
        lab_report = st.file_uploader("4. 시험성적서 (PDF)", type=["pdf"])
        recipe_doc = st.file_uploader("5. 원재료 명세서 (PDF/Excel)", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 정밀 QC 진단 시작", type="primary"):
        if not (main_img and info_img and nutri_img and lab_report):
            st.warning("⚠️ 필수 파일을 모두 업로드해주세요.")
            return

        user_content = []
        # 파일들을 순차적으로 user_content에 추가 (레이블 포함)
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

        with st.spinner("법규 및 실무 기준 대조 중..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(lab_report, "시험성적서")
            if recipe_doc: add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            prompt = """
            업로드된 파일들을 종합적으로 검토해.
            특히 비타민/무기질의 경우, 환산값보다 낮게 표시(예: 1.197 -> 1.0)한 것은 실무적으로 안전한 관리이므로 '적합'으로 판정해라. 
            단, 지방/탄수화물 등 0.5g 미만이 아닌데 0g으로 적은 것은 엄격히 지적해.
            모든 분석의 기준은 성적서가 아니라 '시안 이미지 속 실제 숫자'여야 한다.
            """
            
            # 법령 파일 로드 로직 (생략: 기존 방식과 동일하게 refs 추가 가능)
            response = model.generate_content(user_content + [prompt])
            
            st.success("분석 완료!")
            st.markdown(response.text)
            
            for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password():
        main()
