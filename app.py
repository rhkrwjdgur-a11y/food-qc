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
# 2. 통합 전문가 프롬프트 (Rule 1~18 풀버전 복구)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오.

[⚠️ 업로드 자료 가변성에 따른 검토 지침]
- 사용자가 시안 이미지나 문서를 전부 또는 일부 생략할 수 있습니다.
- 업로드되지 않은 자료를 지어내어(환각) 평가하지 마십시오. 제공된 자료 안에서만 확인 가능한 부분을 검토하여 보고서를 작성하십시오. 해당 사항이 없는 목차는 "자료 미제공으로 검토 생략"으로 기재하십시오.

---
[⚠️ 검토 대원칙: 18대 특수 지침 (Full Version)]

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

✅ **Rule 11. 영양정보 팩트 체크 및 고시 세부 단위 절대 법칙**
   - **[1단계]** 영양성분표 이미지 판독 (함량 및 %).
   - **[2단계: 환산]** 열량(5kcal 단위, 5미만 0), 나트륨(120mg 이하 5mg 단위, 초과 10mg 단위), 탄/당/단/지(0.5g 미만 0) 등 법적 단위 강제 적용.
   - **[3단계: 비타민 듀얼 정답]** 환산값이 4.18mg일 때 수학적 반올림(4.2mg)도 ✅적합, 보수적 하향 표기(4.0mg)도 ✅적합.
   - **[4단계: 비율 절대 법칙]** 비율(%)에는 보수적 룰 미적용. (시안 최종 함량 ÷ 1일 기준치) × 100 계산 후 정수 반올림 값과 완벽히 일치해야 함.

✅ **Rule 12. 배합비 대조 검증 및 적극적 생략 코칭**
   - 5% 미만 복합원재료(예: 유산균배양액)는 하위 원재료 생략 가능함을 안내. 단, 알레르기(예: 우유)는 필수 표기.
✅ **Rule 13. 알레르기 문구 텍스트+디자인(음영) 추적**
   - 시안에서 'OO 함유' 글자 확인 및 바탕색/테두리 시각적 강조 스캔.
✅ **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료 옆 '(감미료)' 명시 확인.
✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
   - 열량 정답이 5kcal 등 0이 아닌데 'ZERO'라고 적혀있으면 🚨부적합. (단, 100ml 환산 시 4kcal 미만이면 합법이므로 용량 주의).
   - 기타면(측면)에 과도한 질병 예방/치료 효능 표기 스캔.

🆕 **Rule 16. [원산지/유기농 100%] 액상 제품의 '물(정제수)' 예외 룰**
   - 액상차/음료 시안에 "100% 국산 원료" 강조 시, '정제수(물)'가 들어갔다는 이유로 기만광고라 지적하는 환각 절대 금지. 물은 용매이므로 산정 제외, 농산물 원료가 국산이면 ✅적합.
🆕 **Rule 17. ['無첨가' 강조표시 절대 룰] 법적 허용과 기만의 구분**
   - "4無첨가(향료, 감미료 등)" 표기 시, 해당 식품유형에 원래 금지된 첨가물이 아니라면 합법 마케팅으로 ✅적합. 원래 법으로 금지된 첨가물(예: 다류의 색소/보존료)을 안 넣었다고 할 때만 기만광고로 🚨지적.
🆕 **Rule 18. [영유아 타겟 일반식품] '베베', '키즈' 등 제품명 허용 룰**
   - 일반식품(액상차 등) 제품명에 '베베', '키즈' 등이 사용되었다고 "특수용도식품이 아니므로 기만이다"라고 과잉 지적 금지. 합법적 타겟 마케팅이므로 ✅적합 판정.

---
[📝 결과 보고서 5단계 작성 양식]
## 1️⃣ [주표시면 및 기타면]
## 2️⃣ [영양표시]
- 📊 **영양성분 팩트 체크 표** (7컬럼 유지. 성적서 없으면 환산값/정답 칸은 '-' 처리)
| 성분명 | 성적서 | 환산값 | 법적 단위 적용 정답 | 시안 표기값 | 판정 | 비고 |
- 세부 분석.
## 3️⃣ [정보표시면]
## 4️⃣ [기타사항]
## 5️⃣ [종합의견]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (Rule 1~18 풀버전)")
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
            업로드된 자료만 가지고 평가해라. 문서만 들어왔다면 문서의 적합성만, 시안만 들어왔다면 디자인 표시사항만 점검해라.
            Rule 18(영유아 일반식품 명칭 허용)을 인지하여 제품명에 딴지 걸지 마라.
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
