import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

# ==========================================
# [보안] 비밀번호 설정 (사내 공유용)
# ==========================================
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "2082":  # 🔑 비밀번호 설정 (원하는 대로 변경 가능)
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 비번 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 처음 접속 시
        st.text_input(
            "🔒 관계자 외 접속 금지 (비밀번호 입력)", 
            type="password", 
            on_change=password_entered, 
            key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # 비번 틀렸을 때
        st.text_input(
            "🔒 비밀번호가 틀렸습니다. 다시 입력하세요.", 
            type="password", 
            on_change=password_entered, 
            key="password"
        )
        return False
    else:
        # 비번 맞음 -> 앱 실행
        return True

# ==========================================
# 1. API 키 설정
# ==========================================
# 👇 여기에 발급받으신 Google Gemini API 키를 넣어주세요.
API_KEY = "AIzaSyD0AaiSi7JfcjGc6Q9_KnzXplQwtFnc8V4"
genai.configure(api_key=API_KEY)

# ==========================================
# 2. 모델 설정
# ==========================================
MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 3. 통합 전문가 프롬프트 (Rule 1 ~ 10 완전체)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 [참고 법령 파일들]과 [통합 사전 학습 목록]을 근거로 시안을 정밀 검토하십시오.

[⚠️ AI 판단 로직 설정 (Critical Logic)]
단순히 숫자를 비교하지 말고, **제품의 단위(mL vs g)**를 최우선으로 확인한 뒤 법적 기준을 다르게 적용하십시오.
또한, 현장의 대량 생산 특성과 수급 변동성을 고려하여 제조사에 유리하고 안전한 방향으로 해석하십시오.

---

[⚠️ 검토 대원칙: 10대 특수 지침 (Final Version)]

✅ **Rule 1. 원산지 3순위 산정 제외 (White-list)**
   - 물, 주정, 당류(시럽 포함), 첨가물은 3순위 카운트 제외.
   - 남은 '실질 농축수산물' 상위 3개만 원산지 확인.

✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료(천연/합성 불문), 일반 첨가물(용도명 불필요) [적합].

✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
   - 영양정보 표: 표에 적힌 기준(총량/100mL)대로 계산.
   - 강조표시(고/풍부): 액상 제품은 무조건 **[Rule 10]**에 따라 판단.

✅ **Rule 4. 영양성분 실측값 허용**
   - '그대로 표시' 성분은 소수점 실측값 표기 [적합].

✅ **Rule 5. 5% 룰 & 알레르기**
   - 5% 미만이라도 알레르기 물질 표시 시 "의무 준수"로 [적합].

✅ **Rule 6. 당류/시럽 필터링**
   - 단순 감미료 시럽은 제외, 과일/농산물 시럽은 원료로 포함.

✅ **Rule 7. 감미료 주의문구 (알룰로스 예외 & 당알코올 10%)**
   - **대상:** 당알코올류(에리스리톨, 말티톨, 자일리톨 등).
   - **판정 기준:** 제품 내 함량이 **10% 이상**인 경우에만 "설사 주의 문구" 필수 지적. (10% 미만은 적합)
   - **(지적 금지):** 알룰로스(D-알룰로오스)는 법적 표시 의무가 없으므로, 경고 문구가 없어도 절대 지적하지 마십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 대두, 옥수수 등 수입 원료의 원산지 표기가 **"외국산(미국, 캐나다, 러시아 등)"**으로 되어 있다면 이는 [매우 적합]한 표기입니다.
   - **(지적 금지):** "국가를 명확히 하라"거나 "'등'을 빼라"고 제안하지 마십시오. 이는 원료 수급지 변경 시 법적 리스크를 초래합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 정보표시면의 '식품유형' 란에 적힌 명칭(예: 가공두유, 혼합음료)은 법적 분류명입니다.
   - **(지적 금지):** 이를 보고 "제품명이 너무 단순하다", "브랜드명을 써라"고 제안하지 마십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - **Step 1 (단위 확인):** 제품의 총 내용량 단위가 **mL(액체)**인지 **g(고체)**인지 확인하십시오.
   - **Step 2 (기준 적용):**
     - **Case A: 액체 (mL, L)** 👉 **[10% 룰]** 적용. (1일 영양성분 기준치의 **10% 이상**이면 "고/풍부" 적합)
       (예: 단백질은 100mL당 **5.5g** 이상이면 합격. 11g을 요구하지 마십시오.)
     - **Case B: 고체 (g, kg)** 👉 **[20% 룰]** 적용. (1일 영양성분 기준치의 **20% 이상**이어야 "고/풍부" 적합)
       (예: 단백질은 100g당 **11g** 이상이어야 합격)

---
[📝 결과 보고서 작성 양식]

## 0️⃣ [규격서 vs 포장지] 교차 검증 결과 (해당 시)
## 1️⃣ 주표시면 검토
## 2️⃣ 정보표시면 검토
   - **(검토 포인트)** 식품유형과 원산지 표기(Rule 8, 9)가 제조 유연성을 확보하고 있는지 확인.
   - **(주의)** 감미료(Rule 7) 경고문구 필요 여부 (알룰로스 제외, 당알코올 10% 미만 제외).
## 3️⃣ 영양정보 검토
   - **(검토 포인트)** 강조 표시(Rule 10)가 액체(10%)/고체(20%) 기준에 맞게 적용되었는지 확인.
## 4️⃣ 기타 법적 사항

(각 항목별: 📝상세분석 -> 📖법적근거 -> 🚨행정처분(표) -> 💡수정제안)
"""

# ==========================================
# 4. 법령 파일 업로드 함수
# ==========================================
@st.cache_resource
def upload_reference_files_to_gemini():
    pdf_files = glob.glob("*.pdf")
    # 임시 파일 및 시스템 파일 제외
    pdf_files = [f for f in pdf_files if "temp_user_file" not in f and "temp_" not in f]
    uploaded_files = []
    
    if not pdf_files: return [], []
    
    for file_path in pdf_files:
        try:
            uploaded_file = genai.upload_file(file_path)
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(1)
                uploaded_file = genai.get_file(uploaded_file.name)
            uploaded_files.append(uploaded_file)
        except Exception as e:
            st.error(f"파일 업로드 실패 ({file_path}): {e}")
            
    return uploaded_files, pdf_files

# ==========================================
# 5. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 통합 마스터 (Final)", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (현장 실무형 통합버전)")
    st.markdown("---")
    
    with st.spinner("법령 데이터베이스를 연결 중입니다..."):
        references, file_names = upload_reference_files_to_gemini()
    
    if file_names:
        st.success(f"✅ 법령 파일 {len(file_names)}개가 준비되었습니다.")
        with st.expander("📂 학습된 법령 파일 목록 보기"):
            for name in file_names:
                st.write(f"- 📄 {name}")
    else:
        st.error("⚠️ 폴더에 PDF 법령 파일이 없습니다. (같은 폴더에 넣어주세요)")
    
    uploaded_files = st.file_uploader("파일 업로드 (시안, 규격서)", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        user_content = []
        st.write(f"📂 총 {len(uploaded_files)}개의 파일이 인식되었습니다.")
        
        for uploaded_file in uploaded_files:
            if uploaded_file.type == "application/pdf":
                temp_filename = f"temp_{uploaded_file.name}"
                with open(temp_filename, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                user_pdf = genai.upload_file(temp_filename)
                while user_pdf.state.name == "PROCESSING":
                    time.sleep(1)
                    user_pdf = genai.get_file(user_pdf.name)
                user_content.append(user_pdf)
                
            else:
                image = Image.open(uploaded_file)
                st.image(image, caption=f"{uploaded_file.name}", width=200)
                user_content.append(image)

        if st.button("🔍 QC 전문가 모드 진단 시작", type="primary"):
            try:
                model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                
                with st.spinner("Rule 1~10 (액체/고체 구분, 알룰로스 예외 등)을 모두 적용하여 정밀 분석 중입니다..."):
                    prompt = """
                    파일들을 검토해줘.
                    특히 [Rule 7, Rule 8, Rule 10]을 철저히 지켜서 판단해.
                    액체 제품(mL)에는 고체 기준(20%)을 적용하지 말고 10% 기준을 적용해.
                    현장에서 제조사가 안전하게 생산할 수 있는 방향으로 판단해.
                    """
                    
                    full_input = references + user_content + [prompt]
                    response = model.generate_content(full_input)
                    
                    st.success("분석 완료")
                    st.markdown("### 📋 상세 법적 검토 리포트")
                    st.markdown("---")
                    st.markdown(response.text)
                    
                    # 임시 파일 정리
                    for f in glob.glob("temp_*.pdf"):
                        try: os.remove(f)
                        except: pass

            except Exception as e:
                st.error("오류가 발생했습니다.")
                st.error(f"에러 내용: {e}")

# ==========================================
# 실행 (비밀번호 체크 포함)
# ==========================================
if __name__ == "__main__":
    if check_password():
        main()