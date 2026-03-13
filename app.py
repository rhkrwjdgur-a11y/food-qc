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
# 2. 통합 전문가 프롬프트 (Rule 1~25 완결판)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오.

[⚠️ 업로드 자료 가변성에 따른 검토 지침]
- 사용자가 시안 이미지나 문서를 전부 또는 일부 생략할 수 있습니다.
- 업로드되지 않은 자료를 지어내어(환각) 평가하지 마십시오.

---
[⚠️ 검토 대원칙: 25대 특수 지침 (Full Version)]

✅ **Rule 1. 원산지 3순위 산정 제외 (White-list)**
   - 물, 주정, 당류, 첨가물은 3순위 카운트 제외. 남은 상위 3개만 원산지 확인.
✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료 및 일반 첨가물 표기 [적합].
✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
✅ **Rule 4. 영양성분 실측값 허용**
✅ **Rule 5. 5% 룰 & 알레르기**
✅ **Rule 6. 당류/시럽 필터링**
✅ **Rule 7. 감미료 주의문구**
✅ **Rule 8. 수입 원료 원산지 유연성 보호**
✅ **Rule 9. 식품유형 vs 제품명 구분**
✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
✅ **Rule 11. 영양정보 팩트 체크 및 고시 세부 단위 절대 법칙**
   - 비율(%) 계산 시 보수적 룰 미적용. 정수 반올림 값과 일치해야 함.
✅ **Rule 12. 배합비 대조 검증 및 생략 코칭**
✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔**
✅ **Rule 14. 첨가물 용도명 병기 스캔**
✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
🆕 **Rule 16. [원산지 100%]** 물은 산정 제외, 농산물 국산이면 100% 합법.
🆕 **Rule 17. ['無첨가' 절대 룰]** 금지된 첨가물을 안 넣었다고 강조할 때만 🚨지적.
🆕 **Rule 18. [영유아 타겟 명칭]** '베베', '키즈' 일반식품 마케팅 합법.
🆕 **Rule 19. ['무당/무가당/저당' 엄격 적용]** 저당(5g 미만), 무당(0.5g 미만), 무가당(무첨가).
🆕 **Rule 20. [용기·포장재질 표기법]** "재질명(포장부위)" 형태로 코칭.
🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증 및 수치 환각 방지]**
   - AI가 법적 수치를 임의로 지어내지 마십시오. '고(풍부)'의 기준은 고체 20%, 액체 10%입니다.
   - 단백질, 식이섬유, 칼슘, 비타민 등 **모든 영양성분**에 대해 '고/풍부/함유/무/저' 강조표시 적합성을 심사할 때, 100g(또는 100ml) 기준 하나만 보고 탈락시키면 🚨심각한 오류입니다.
   - 반드시 아래 **4가지 환산 기준을 모두 계산**하여 단 하나라도 충족하면 ✅적합(합법)으로 판정하십시오.
     1) **100g당 (고체)**: 기준치의 20% 이상 (함유는 10%)
     2) **100ml당 (액체)**: 기준치의 10% 이상 (함유는 5%)
     3) **100kcal당**: 기준치의 10% 이상 (함유는 5%)
     4) **1회 섭취참고량당**: 기준치의 20% 이상 (함유는 10%)
   - 판정 예시: "100g 기준으로는 미달이나, 총 칼로리 기준 환산 시 100kcal당 OOg으로 10% 이상 조건을 충족하므로 '고단백' 표기가 합법입니다."
🆕 **Rule 22. [다국어 폰트 크기]** 영문이 한글보다 크면 부적합 코칭.

🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 시 AI 자체 계산 절대 금지 및 부적합 강제]**
   - **[절대 금지 사항]** AI 당신이 임의로 총 내용량을 개수로 나누어(예: 0.5g / 4 = 0.125g) "0.2g 미만이므로 0g 표기가 적합하다"고 유추하여 합격시키는 행위를 전면 금지합니다.
   - **[1단계]** 시안의 트랜스지방 총 내용량 표기란에 **'0.5g'**이라고 숫자만 딱 떨어지게 적혀있다면 묻지도 따지지도 말고 🚨**부적합(불합격)** 처리하십시오. (이유: 식약처 고시상 0.2~0.49g 구간은 무조건 텍스트로 **'0.5g 미만'**이라고 적어야 하며, '0.5g'으로 퉁쳐서 적는 것은 표시기준 위반입니다.)
   - **[2단계]** 특히 1컵당 '0g'인데 총 내용량에 '0.5g'이라고 짝지어져 있다면, 🚨**부적합** 판정을 내리고 다음 문구를 반드시 리포트에 출력하십시오: 
     "🚨 [Rule 23 위반] 1컵 기준 미량(0.1g 등)이 포함되어 4입 누적 시 0.2g~0.49g 구간이 되었다면, 총 내용량 트랜스지방은 '0.5g'이 아니라 반드시 **'0.5g 미만'**으로 표기해야 합니다. 현재 시안의 '0.5g' 표기는 부적합하므로 즉시 수정 바랍니다."

🔥 **Rule 24. [제로/무가당 강조표시 주변 열량 및 감미료 의무 표기]**
   - 저열량 기준 초과 시 강조표시 주변에 '총 열량' 또는 '저열량 제품 아님' 문구 표기 스캔.
🔥 **Rule 25. [다중 포장(묶음 단위) 영양성분표 비전 스캔 분리]**
   - 1개당 / 총 내용량 듀얼 컬럼 혼동 금지.
🔥 **Rule 26. [고체(g) vs 액체(mL) 단위 엄격 구분 및 적용 룰]**
   - 제품의 내용량 단위가 'g'(고체)인지 'mL'(액체)인지 먼저 명확히 식별하십시오. (예: 발효유, 액상차, 음료는 mL 적용)
   - 영양강조표시 기준을 적용할 때 단위를 혼용하거나 무시하지 마십시오.
   - 액체(mL)는 고체(g)보다 기준이 훨씬 엄격하거나 다릅니다 (예: 저당 기준 고체 5g 미만 / 액체 2.5g 미만).
   - 액체 제품(mL)에 고체(g)의 헐렁한 잣대를 들이대어 합격시키는 치명적인 오류를 절대 범하지 마십시오.

   🔥 **Rule 27. [제한 영양성분(당류/지방/나트륨 등) 100kcal 적용 절대 금지 룰]**
   - **당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨**의 '무(Free)' 또는 '저(Low)' 강조표시를 검토할 때는 **절대 100kcal 기준이나 1회 섭취량 기준을 적용하지 마십시오.**
   - 오직 해당 식품의 제형에 맞춰 **100g당(고체) 또는 100mL당(액체)** 기준만 매우 엄격하게 적용하여 초과 시 🚨부적합 처리하십시오.
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
    st.title("🏭 식품 표시사항 정밀 검토 (Rule 1~25 완결판)")
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
            특히 영양성분표에서 트랜스지방이 0g으로 되어있다면, 스스로 수학적 유추를 해서 합격시키지 말고 Rule 23에 따라 무조건 '0.5g 미만 표기 조건'에 대한 경고를 리포트에 출력해라.
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
