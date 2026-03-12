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
# 2. 통합 전문가 프롬프트 (비율% 예외 금지 룰 추가)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 시안(분할 이미지), 성적서, 배합비를 교차 검증하십시오.

---

[⚠️ 검토 대원칙: 15대 특수 지침 (Final Version)]

✅ **Rule 1. 원산지 3순위 산정 제외 (White-list)**
   - 물, 주정, 당류, 첨가물은 3순위 카운트 제외. 남은 상위 3개만 원산지 확인.

✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료 및 일반 첨가물(용도명 불필요) 표기 [적합].

✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
   - 영양정보 표는 표에 적힌 기준(총량/100mL)대로 계산.

✅ **Rule 4. 영양성분 실측값 허용**
   - '그대로 표시' 성분은 소수점 실측값 표기 [적합].

✅ **Rule 5. 5% 룰 & 알레르기**
   - 5% 미만이라도 알레르기 물질 표시 시 "의무 준수"로 [적합].

✅ **Rule 6. 당류/시럽 필터링**
   - 단순 감미료 시럽은 배합비에서 원료 카운트 제외.

✅ **Rule 7. 감미료 주의문구**
   - 당알코올류 10% 이상일 때만 "설사 주의 문구" 필수 지적.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 대두, 옥수수 등 "외국산" 표기 [적합].

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 정보표시면의 '식품유형' 란에 적힌 명칭은 법적 분류명입니다.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - 강조표시 시 액체(mL)는 10% 룰, 고체(g)는 20% 룰 적용.

🆕 **Rule 11. 영양정보 팩트 체크 및 비율(%) 절대 법칙**
   - **[1단계: 시안 강제 읽기]** 영양성분표 이미지의 픽셀을 판독하여 함량과 비율(%) 추출.
   - **[2단계: 함량 법적 단위 환산]** 1) 열량: 5kcal 단위 (5 미만만 0)
     2) 나트륨: 120mg 이하 5mg 단위 / 초과 10mg 단위
     3) 탄/당/단/지방: 0.5g 미만 0
   - **[3단계: 비타민·무기질 함량 보수적 표기 인정]** 환산값(예: 1.2mg)보다 실무적으로 낮게 표기(예: 1.0mg)한 경우 '함량 수치'에 한해 ✅적합.
   - **[4단계: 1일 기준치 비율(%) 절대 법칙 - 매우 중요]** - 1일 기준치 비율(%)에는 보수적 룰(80%)이 절대 적용되지 않습니다!
     - 비율(%) 정답 = (시안에 표기하기로 확정된 최종 함량 ÷ 1일 영양성분 기준치) × 100 후 정수 반올림.
     - 예: 비타민B6 함량을 0.4mg으로 표시하기로 했다면, (0.4 ÷ 1.5) × 100 = 26.66%이므로 무조건 **27%**가 정답입니다. 시안에 24%라고 적혀있다면 이는 "보수적 표기"가 아니라 **🚨부적합(계산 오류)**입니다.

✅ **Rule 12. 배합비 5% 미만 적극 코칭**
   - 정보표시면 검토 시, 배합비 5% 미만 복합원재료(예: 유산균배양액 등)는 하위 원재료 생략이 가능함을 안내. 단 알레르기(우유 등)는 표기 필수.

✅ **Rule 13. 알레르기 문구 텍스트+디자인(음영) 추적**
   - 시안에서 'OO 함유' 글자 확인 및 바탕색/테두리 스캔.

✅ **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료 옆 '(감미료)' 명시 확인.

✅ **Rule 15. 강조표시 연쇄 불합격 팩트 폭격**
   - 열량 환산값이 6.95kcal(정답 5kcal)인데 주표시면에 'ZERO'라고 적혀있으면 🚨부적합.

---
[📝 결과 보고서 5단계 작성 양식]

## 1️⃣ [주표시면]
## 2️⃣ [영양표시]
- 📊 **영양성분 팩트 체크 표** (7컬럼 유지)
| 성분명 | 성적서 (100mL) | 환산값 (총량) | 법적 단위 적용 정답 (함량 / %) | 시안 표기값 (함량 / %) | 판정 | 비고 (적용 법규) |
- 세부 분석 (비율(%) 계산 오류 시 엄격히 지적).
## 3️⃣ [정보표시면]
- 배합비 5% 미만 생략 코칭 (Rule 12) 포함.
## 4️⃣ [기타사항]
## 5️⃣ [종합의견]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (비율% 완전 무결성 버전)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 시안 분할 이미지")
        main_img = st.file_uploader("1. 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2. 정보표시면 (뒷면)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3. 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
    with col2:
        st.subheader("📄 증빙 문서")
        lab_report = st.file_uploader("4. 시험성적서 (필수 PDF)", type=["pdf"])
        recipe_doc = st.file_uploader("5. 원재료 명세서/배합비 (필수 엑셀/PDF)", type=["pdf", "xlsx", "csv"])

    if st.button("🔍 Rule 1~15 정밀 진단 시작", type="primary"):
        if not (main_img and info_img and nutri_img and lab_report and recipe_doc):
            st.warning("⚠️ 완벽한 검증을 위해 5가지 파일을 모두 업로드해주세요.")
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

        with st.spinner("함량 및 비율(%)의 수학적 무결성 검증 중..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(lab_report, "시험성적서")
            add_file(recipe_doc, "원재료명세서")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = """
            [Rule 11-4]를 명심해라. 
            함량(mg, ug)은 80% 룰에 따라 보수적으로 낮게 표기할 수 있지만, 비율(%)은 시안에 표기된 그 함량을 기준으로 수학적으로 완벽하게 떨어져야 한다! 
            비타민B6 함량을 0.4mg으로 표시했다면 %는 무조건 27%다. 24%로 적은 시안은 계산 오류이므로 '🚨부적합(비율 오류)'으로 지적해라.
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
