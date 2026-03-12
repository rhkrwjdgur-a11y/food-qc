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
# 2. 통합 전문가 프롬프트 (고시 전문 세부 단위 적용)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
업로드된 [식품등의 표시기준] 고시 전문과 [시험성적서], [시안]을 대조하여 오차 없는 보고서를 작성하십시오.

---

[⚠️ Rule 11. 성분별 고시 전문 세부 표시 단위 및 반올림 기준]

당신은 수학적 반올림이 아닌, 대한민국 법령이 정한 아래의 '단위'를 반드시 지켜야 합니다:

1. **열량:** 5kcal 단위로 표시 (5kcal 미만은 "0").
2. **나트륨:** - 120mg 이하: 가장 가까운 **5mg 단위**로 표시 (예: 43.1mg -> 45mg).
   - 120mg 초과: 가장 가까운 **10mg 단위**로 표시.
   - 5mg 미만은 "0" 표시 가능.
3. **탄수화물, 당류, 단백질:** 1g 단위로 표시 (0.5g 미만은 "0").
4. **지방, 포화지방:** 5g 이하 0.1g 단위 / 5g 초과 1g 단위 (0.5g 미만은 "0").
5. **트랜스지방:** 0.2g 미만은 "0" 표시 가능.
6. **콜레스테롤:** 5mg 단위로 표시 (2mg 미만은 "0").
7. **비타민, 무기질:** - 그대로 표시하거나 유효숫자 3자리 또는 소수점 첫째 자리까지 표시 가능.
   - 단, 실무적 판단에 따라 하향 표기(1.2 -> 1.0)하는 '보수적 표기'는 적합 판정.

✅ **중요 검증 로직:**
- (시안의 함량 숫자)가 위 '단위'에 맞게 적혔는지 확인.
- (시안의 % 비율)이 [반올림된 최종 함량 ÷ 기준치] 계산 결과와 일치하는지 확인.
- 영양표의 값이 '0'이 아닌데 주표시면에 'ZERO' 강조가 있다면 무조건 🚨부적합.

---
[📝 결과 보고서 작성 양식]
| 성분명 | 성적서(100mL) | 환산값(총량) | 법적 단위 적용 정답(함량/%) | 시안 표기값(함량/%) | 판정 | 비고(적용 법규) |
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터 (Professional)", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (고시 전문 단위 완벽 적용)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 이미지")
        main_img = st.file_uploader("1. 주표시면 (ZERO 강조 확인)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (원재료/음영 확인)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (수치/비율 정밀 판독)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서")
        lab_report = st.file_uploader("4. 시험성적서 (필수)", type=["pdf"])
        recipe_doc = st.file_uploader("5. 원재료 명세서/배합비 (선택)", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 고시 기준 정밀 진단 시작", type="primary"):
        if not (main_img and info_img and nutri_img and lab_report):
            st.warning("⚠️ 정확한 분석을 위해 파일을 모두 업로드해주세요.")
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

        with st.spinner("성분별 세부 법적 단위(나트륨 5mg 단위 등) 적용 중..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(lab_report, "시험성적서")
            if recipe_doc: add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            업로드된 고시 전문(PDF)과 성적서를 대조해.
            나트륨이 120mg 이하인데 5mg 단위로 끊지 않았거나, 칼로리가 5단위가 아니거나, 
            시안의 % 비율이 최종 반올림 함량 기준으로 계산되지 않았다면 강력하게 지적해라.
            모든 분석의 출발점은 [영양성분표 이미지]에서 직접 읽은 실제 숫자여야 한다.
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
