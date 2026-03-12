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
# 2. 통합 전문가 프롬프트 (보고서 양식 및 칼로리 로직 강화)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령과 사용자가 업로드한 시안(주표시, 정보표시, 영양표시), 성적서, 배합비를 교차 검증하여 보고서를 작성하십시오.

---

[⚠️ 영양성분 검증 및 칼로리 절대 법칙 (Rule 11 & 15)]

1. **칼로리 환산 및 반올림 (환각 방지):**
   - 100mL당 성적서 수치를 **제품의 총 내용량(예: 190mL)**으로 환산한 결과가 **5kcal 이상**이라면, 절대로 '0'으로 표시할 수 없습니다.
   - 예: 환산값 6.954 kcal -> 법적 정답은 **5 kcal**입니다. (10단위 반올림이 아니라 5단위로 가장 가까운 값인 5로 표기)
   - 만약 환산값이 5kcal 이상인데 시안에 '0'으로 적혀 있거나 주표시면에 'ZERO'라고 강조되어 있다면 무조건 **🚨부적합**으로 판정하고 강조문구 삭제를 권고하십시오.

2. **나트륨 표시 단위:**
   - 120mg 이하: 가장 가까운 **5mg 단위**로 표시.
   - 120mg 초과: 가장 가까운 **10mg 단위**로 표시.
   - 5mg 미만일 때만 "0" 표시 가능.

3. **비율(%) 산출:**
   - 반드시 [법적 반올림이 완료된 최종 함량 숫자]를 기준치로 나누어 정수로 반올림하십시오.

---

[📝 결과 보고서 작성 양식 - 반드시 이 순서를 지킬 것]

## 1️⃣ [주표시면]
- 제품명, 내용량, 강조표시(ZERO, 고칼슘 등)의 법적 적정성 검토.
- **Rule 15:** 영양성분표 수치가 0이 아닌데 'ZERO'라고 표시했는지 여부 집중 확인.

## 2️⃣ [영양표시]
- 📊 **영양성분 팩트 체크 표** (반드시 아래 7컬럼 포함)
| 성분명 | 성적서 (100mL) | 환산값 (총량) | 법적 단위 적용 정답 (함량 / %) | 시안 표기값 (함량 / %) | 판정 | 비고 (적용 법규) |
- 위 표를 바탕으로 한 세부 분석 내용.

## 3️⃣ [정보표시면]
- 식품유형, 원재료명 기재 순서(배합비 대조), 알레르기 음영 강조(우유 함유 등), 첨가물 용도명 병기 여부.

## 4️⃣ [기타사항]
- 보관방법, 주의사항, 제조원 정보 등 기타 법적 의무사항 검토.

## 5️⃣ [종합의견]
- 전체적인 적합 여부 요약 및 우선 수정 순위 제안.
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터 (Professional)", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (완성형 보고서 양식)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 이미지 업로드")
        main_img = st.file_uploader("1. 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서 업로드")
        lab_report = st.file_uploader("4. 시험성적서 (필수)", type=["pdf"])
        recipe_doc = st.file_uploader("5. 원재료 명세서/배합비", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 정밀 QC 진단 시작", type="primary"):
        if not (main_img and info_img and nutri_img and lab_report):
            st.warning("⚠️ 정확한 분석을 위해 시안 3장과 성적서는 꼭 올려주세요.")
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

        with st.spinner("이미지 판독 및 보고서 작성 중..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(lab_report, "시험성적서")
            if recipe_doc: add_file(recipe_doc, "원재료명세서")

            # 법령 파일 로드
            pdf_refs = []
            for pf in glob.glob("*.pdf"):
                if "temp_" not in pf:
                    ref = genai.upload_file(pf)
                    while ref.state.name == "PROCESSING": time.sleep(1); ref = genai.get_file(ref.name)
                    pdf_refs.append(ref)

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            업로드된 자료를 바탕으로 보고서 양식에 맞춰 작성해.
            특히 영양표시 팩트체크 시 칼로리 환산값이 6.954kcal라면 정답은 '5kcal'다. 
            만약 시안에 0kcal라고 적혀있다면 '🚨부적합'으로 판정하고, 주표시면의 'ZERO' 표시도 허위표시로 지적해라.
            모든 분석은 성적서가 아닌 [영양성분표 이미지]에서 직접 읽은 실제 숫자를 시안 표기값으로 적어야 한다.
            """
            
            response = model.generate_content(pdf_refs + user_content + [final_prompt])
            
            st.success("분석 완료!")
            st.markdown(response.text)
            
            for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password():
        main()
