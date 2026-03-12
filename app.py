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
# 2. 통합 전문가 프롬프트 (기타면 추가 및 듀얼 정답 로직 유지)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 시안(주표시, 정보표시, 영양표시, 기타면), 성적서, 배합비를 교차 검증하십시오.

---

[⚠️ 검토 대원칙: 15대 특수 지침 (Final Version)]

✅ **Rule 1~10. 일반 원재료 및 강조 표시 룰**
   - 물/주정/당류 원산지 산정 제외, 향료 표기 적합, 5% 알레르기 필수 표기, 수입산 유연 표기 허용 등 기존 규정 엄수.

✅ **Rule 11. 영양정보 팩트 체크 (함량 듀얼 정답 및 비율 절대 법칙)**
   - **[1단계: 시안 강제 읽기]** 영양성분표 이미지의 픽셀을 판독하여 함량과 비율(%) 추출.
   - **[2단계: 성분별 단위 환산]** 열량(5kcal 단위), 나트륨(120mg 이하 5mg 단위), 탄/당/단/지(0.5g 미만 0).
   - **[3단계: 비타민·무기질 판정]** 강제 정수 단위 없음. 환산값이 4.18mg일 때 수학적 반올림인 **4.2mg**도 ✅적합, 보수적 하향 표기인 **4.0mg**도 80% 허용오차 내이므로 ✅적합.
   - **[4단계: 1일 기준치 비율(%) 절대 법칙]** 비율(%)에는 보수적 룰이 절대 적용되지 않음. (시안의 최종 함량 ÷ 1일 기준치) × 100 계산 후 정수 반올림한 값이 수학적으로 완벽히 일치해야 함.

✅ **Rule 12. 배합비 5% 미만 코칭**
   - 5% 미만 복합원재료(예: 유산균배양액)는 하위 원재료 생략 가능함을 코칭. 단, 알레르기(우유)는 필수 표기.

✅ **Rule 13. 알레르기 텍스트+디자인(음영) / Rule 14. 첨가물 용도명 병기**

🆕 **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 (주표시면 & 기타면 확장)**
   - **[영양 강조]** [주표시면] 및 [기타면]의 'ZERO', '무' 표시를 영양성분표의 최종 함량과 대조. (예: 5kcal가 정답인데 ZERO라고 적혀있으면 🚨부적합).
   - **[효능/과대광고 검증]** 사용자가 업로드한 [기타면] 이미지에 건강기능식품으로 오인할 수 있는 과도한 질병 예방/치료 효능 표기가 있는지 스캔하여, 일반식품 표시광고법 위반 소지가 있다면 경고하십시오.

---
[📝 결과 보고서 5단계 작성 양식]
## 1️⃣ [주표시면 및 기타면]
- 제품명, 내용량, 강조표시(ZERO 등) 및 기타면의 효능/기능성 마케팅 문구 적정성 검토.
## 2️⃣ [영양표시]
- 📊 **영양성분 팩트 체크 표** (7컬럼 유지)
| 성분명 | 성적서 (100mL) | 환산값 (총량) | 법적 단위 적용 정답 (함량 / %) | 시안 표기값 (함량 / %) | 판정 | 비고 (적용 법규) |
- 세부 분석 (비타민 듀얼 정답 인정 사유, 비율(%) 정확성 확인 등).
## 3️⃣ [정보표시면]
## 4️⃣ [기타사항]
## 5️⃣ [종합의견]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (기타면/효능 검증 추가)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 분할 이미지")
        main_img = st.file_uploader("1. 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
        extra_img = st.file_uploader("4. 기타면 (측면/효능 강조 등 - 선택)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서")
        lab_report = st.file_uploader("5. 시험성적서 (필수 PDF)", type=["pdf"])
        recipe_doc = st.file_uploader("6. 원재료 명세서/배합비 (필수 엑셀/PDF)", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 Rule 1~15 정밀 진단 시작", type="primary"):
        if not (main_img and info_img and nutri_img and lab_report and recipe_doc):
            st.warning("⚠️ 완벽한 검증을 위해 필수 5가지 파일을 모두 업로드해주세요. (기타면 이미지는 선택사항입니다)")
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

        with st.spinner("이미지 및 문서 전방위 교차 검증 중..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            if extra_img: add_file(extra_img, "기타면")  # 추가된 기타면 처리 로직
            add_file(lab_report, "시험성적서")
            add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            업로드된 시안과 문서를 교차 검증하라.
            특히 [기타면 이미지]가 업로드되었다면, 그곳에 적힌 마케팅 문구나 효능 표시가 '식품 등의 표시·광고에 관한 법률'에 위배되는 과대광고(일반식품인데 건강기능식품처럼 오인할 우려)는 없는지 집중적으로 점검하여 1️⃣ [주표시면 및 기타면] 항목에 서술해라.
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
