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
        if st.session_state["password"] == "2082":  # 🔑 비밀번호 설정
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
# 키는 Secrets에서 가져옴
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)

# ==========================================
# 2. 모델 설정
# ==========================================
MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 3. 통합 전문가 프롬프트 (Rule 1 ~ 12 완전체)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 [참고 법령 파일들]과 [통합 사전 학습 목록], 그리고 사용자가 업로드한 [시험성적서, 배합비, 시안]을 종합적으로 교차 검증하십시오.

[⚠️ AI 판단 로직 설정 (Critical Logic)]
단순히 숫자를 비교하지 말고, **제품의 단위(mL vs g)**를 최우선으로 확인한 뒤 법적 기준을 다르게 적용하십시오.
또한, 현장의 대량 생산 특성과 수급 변동성을 고려하여 제조사에 유리하고 안전한 방향으로 해석하십시오.

---

[⚠️ 검토 대원칙: 12대 특수 지침 (Final Version)]

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

🆕 **Rule 11. 시험성적서 기반 영양성분 정밀 검증 (자료 제공 시)**
   - **용량 환산:** 시험성적서의 결과(예: 100g/100mL 기준)를 제품의 실제 총 내용량(또는 1회 제공량)에 맞게 비례 환산하여 시안의 표기값과 일치하는지 확인하십시오.
   - **반올림 단위:** 「식품등의 표시기준」에 따른 영양성분별 반올림 단위(나트륨 5mg, 당/탄수화물 1g 등) 적용 여부를 확인하십시오.
   - **허용 오차:** 성적서 값 대비 시안의 표기 값이 법적 허용 오차 범위(열량/당류/지방 120% 미만, 단백질 80% 이상 등) 내에 있는지 검증하십시오.

🆕 **Rule 12. 배합비 기반 원재료 순서 및 예외 룰 적용 (자료 제공 시)**
   - **원칙:** 배합비율 내림차순 기재 여부를 대조하십시오.
   - **[2% 예외 룰]:** 배합비율 2% 미만인 원재료는 시안에서 순서가 배합비율과 다르게 기재되어 있어도 오류로 지적하지 마십시오.
   - **[5% 예외 룰]:** 전체 배합비의 5% 미만인 복합원재료는 시안에서 하위 원재료명이 생략되었더라도 누락으로 지적하지 마십시오. (단, 우유, 대두, 밀, 쇠고기 등 법적 알레르기 유발물질이 하위 원재료에 있다면 생략 불가하므로 반드시 지적하십시오.)

---
[📝 결과 보고서 작성 양식]

## 0️⃣ [시험성적서 및 배합비 교차 검증] (해당 자료가 제공된 경우에만 작성)
   - 영양성분 환산 및 오차범위 검토 결과 (Rule 11 적용)
   - 원재료 배합비 순서 확인 및 2%/5% 예외 룰 적용 결과 (Rule 12 적용)
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
    
    # 👇 안정성을 위해 엑셀은 빼고, 안내 문구를 강화했습니다.
    st.info("💡 **[필독]** 엑셀(.xlsx)이나 한글(.hwp) 형식의 배합비/성적서는 표 구조 인식을 위해 반드시 **PDF로 저장(변환)** 후 업로드해 주세요.")
    uploaded_files = st.file_uploader("파일 업로드 (시안 및 PDF 변환된 성적서/배합비)", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        user_content = []
        st.write(f"📂 총 {len(uploaded_files)}개의 파일이 인식되었습니다.")
        
        for uploaded_file in uploaded_files:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            
            # 이미지와 PDF 분리 처리
            if file_ext in ['jpg', 'jpeg', 'png']:
                image = Image.open(uploaded_file)
                st.image(image, caption=f"{uploaded_file.name}", width=200)
                user_content.append(image)
                
            elif file_ext == 'pdf':
                # PDF 문서 파일 처리
                temp_filename = f"temp_{uploaded_file.name}"
                with open(temp_filename, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                user_doc = genai.upload_file(temp_filename)
                while user_doc.state.name == "PROCESSING":
                    time.sleep(1)
                    user_doc = genai.get_file(user_doc.name)
                user_content.append(user_doc)

        if st.button("🔍 QC 전문가 모드 진단 시작", type="primary"):
            try:
                model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                
                with st.spinner("Rule 1~12 (액체/고체 구분, 배합비 2/5% 룰, 성적서 환산 등)을 모두 적용하여 정밀 분석 중입니다..."):
                    prompt = """
                    업로드된 파일들을 종합적으로 검토해줘. 
                    특히 [Rule 11, Rule 12]에 집중하여, 업로드된 자료 중에 '배합비'나 '시험성적서'가 있다면 시안과 교차 검증을 철저하게 수행해.
                    2% 미만 원료 순서와 5% 미만 복합원재료 하위성분 생략 규정을 정확히 적용해서 불필요한 지적을 하지 마.
                    현장에서 제조사가 안전하고 유연하게 생산할 수 있는 방향으로 판단해.
                    """
                    
                    full_input = references + user_content + [prompt]
                    response = model.generate_content(full_input)
                    
                    st.success("분석 완료")
                    st.markdown("### 📋 상세 법적 검토 리포트")
                    st.markdown("---")
                    st.markdown(response.text)
                    
                    # 찌꺼기 파일 삭제
                    for f in glob.glob("temp_*"):
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
