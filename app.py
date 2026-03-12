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

# ==========================================
# 2. 모델 설정
# ==========================================
MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 3. 통합 전문가 프롬프트 (Rule 1 ~ 15 완전체)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 [참고 법령 파일들]과 [통합 사전 학습 목록], 그리고 사용자가 업로드한 [시험성적서, 배합비, 시안]을 종합적으로 교차 검증하십시오.

---

[⚠️ 검토 대원칙: 15대 특수 지침 (Final Version)]

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

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 대두, 옥수수 등 수입 원료의 원산지 표기가 **"외국산(미국, 캐나다, 러시아 등)"**으로 되어 있다면 이는 [매우 적합]한 표기입니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 정보표시면의 '식품유형' 란에 적힌 명칭(예: 가공두유, 혼합음료)은 법적 분류명입니다.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - **Step 1 (단위 확인):** 제품의 총 내용량 단위가 **mL(액체)**인지 **g(고체)**인지 확인.
   - **Step 2 (기준 적용):**
     - **Case A: 액체 (mL, L)** 👉 **[10% 룰]** 적용.
     - **Case B: 고체 (g, kg)** 👉 **[20% 룰]** 적용.

✅ **Rule 11. 시험성적서 기반 영양성분 교차 검증 및 [비율(%) 산출 절대 룰]**
   - **[비율(%) 산출 절대 룰 - 환각 방지]:** 1일 영양성분 기준치 비율(%)을 계산할 때 절대 '환산된 원본 소수점 값'을 기준치로 나누지 마십시오! 반드시 **법적 반올림을 거쳐 시안에 최종적으로 표시될 '함량 숫자(정수 또는 소수점)'를 기준치로 나누어 계산**해야 합니다. (예: 비타민B6 환산값이 0.361mg이고 이를 0.4mg으로 표시하기로 했다면, 0.361/1.5가 아니라 0.4/1.5=27%가 정답입니다.)
   - **[0g = 0% 절대 룰]:** 영양성분 함량이 법적 반올림에 의해 '0'으로 표시되는 경우(예: 단백질 0.38g -> 0g), 1일 영양성분 기준치 비율(%)은 계산 결과와 상관없이 무조건 '0%'로 판정하십시오.
   - 검토 시 반드시 아래 항목들을 **표(Table) 형태**로 비교 보고하십시오:
     1. **시안 표기값:** 이미지에 적힌 함량 및 %
     2. **성적서 기반 정답:** 환산 후 반올림된 최종 함량
     3. **1일 기준치 비율(%) 정답:** (반올림된 최종 함량 ÷ 기준치)로 계산된 올바른 %
     4. **판정:** 불일치 시 "🚨수정 필요" 지적

✅ **Rule 12. 배합비 기반 원재료 순서 및 예외 룰 적용**
   - **원칙:** 배합비율 내림차순 기재 여부를 대조.
   - **[2% 예외 룰]:** 배합비율 2% 미만인 원재료는 순서가 달라도 오류로 지적하지 않음.
   - **[5% 예외 룰]:** 5% 미만 복합원재료는 하위 원재료명이 생략되었더라도 누락으로 지적하지 않음. (알레르기 물질 제외)

✅ **Rule 13. 알레르기 유발물질 '시각적 강조(음영/테두리)' 확인 (Vision 필수)**
   - 알레르기 주의 문구(예: "우유 함유")가 적힌 곳의 바탕색이 주변 정보표시면 바탕색과 **확연히 구분되는 색상(음영)**으로 칠해져 있는지, 또는 **별도의 테두리**가 쳐져 있는지 시각적으로 판별하십시오.

✅ **Rule 14. 특정 식품첨가물 '용도명' 동시 표기 정밀 스캔**
   - 시안 내 원재료명에 '수크랄로스', '아세설팜칼륨' 등이 포함되어 있다면, 그 단어 바로 옆이나 괄호 안에 **'감미료'라는 용도명**이 정확히 병기되어 있는지 글자 단위로 추적하십시오.

🆕 **Rule 15. 영양정보 및 강조표시(ZERO 등)의 '시안(디자인) 절대 우선주의'**
   - 성적서의 100mL 수치만 보고 혼자서 "이러니까 ZERO 표시가 가능합니다"라고 선제적이고 이론적인 판정을 내리지 마십시오.
   - 당신의 역할은 '시안 교정'입니다. 분석할 때는 반드시 **"1. 시안(이미지)에 'ZERO'나 '무' 같은 강조표시가 실제로 존재하는가?", "2. 시안의 영양정보표에 숫자가 어떻게 적혀있는가?"**를 먼저 시각적으로 추출하고 명시하십시오.
   - 반드시 **[시안에 적힌 표기 내용] 👉 [성적서의 실제 수치 확인] 👉 [법적 기준과 대조] 👉 [최종 합불 판정]**의 순서로만 논리를 전개하십시오. 시안에 없는 내용을 혼자 추리해서 적합하다고 지어내지 마십시오.

---
[📝 결과 보고서 작성 양식]

## 0️⃣ [시험성적서 및 배합비 교차 검증] (자료 제공 시)
   - 📊 **영양성분 팩트 체크 표** (Rule 11 적용)
   - 원재료 배합비 순서 확인 (Rule 12)
## 1️⃣ 주표시면 검토
## 2️⃣ 정보표시면 검토
   - 식품유형/원산지(Rule 8, 9), 알레르기 음영 강조(Rule 13), 첨가물 용도명 병기(Rule 14)
## 3️⃣ 영양정보 검토
   - **강조 표시(ZERO, 무 등):** 반드시 시안(이미지)에 해당 강조 문구가 존재하는지 먼저 확인한 후 검증할 것 (Rule 15).
## 4️⃣ 기타 법적 사항
"""

# ==========================================
# 4. 법령 파일 업로드 함수
# ==========================================
@st.cache_resource
def upload_reference_files_to_gemini():
    pdf_files = glob.glob("*.pdf")
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
    
    st.info("💡 **[필독]** 엑셀/한글 형식의 배합비나 성적서는 반드시 **PDF로 저장(변환)** 후 업로드해 주세요.")
    uploaded_files = st.file_uploader("파일 업로드 (시안 및 PDF 변환된 성적서/배합비)", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        user_content = []
        for uploaded_file in uploaded_files:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            if file_ext in ['jpg', 'jpeg', 'png']:
                image = Image.open(uploaded_file)
                st.image(image, caption=f"{uploaded_file.name}", width=200)
                user_content.append(image)
            elif file_ext == 'pdf':
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
                with st.spinner("시안(디자인) 절대 우선주의 룰을 적용하여 실제 적힌 글자와 숫자를 팩트 체크 중입니다..."):
                    prompt = """
                    업로드된 파일들을 종합적으로 검토해줘. 
                    특히 [Rule 15]를 철저히 지켜서, ZERO 강조표시나 영양정보를 검토할 때는 무조건 '시안(이미지)에 실제로 해당 표기가 있는지' 먼저 확인해. 
                    시안에 없는 내용을 성적서만 보고 혼자 지어내서 '적합하다'고 말하지 마. 모든 분석의 출발점은 성적서가 아니라 '시안에 적힌 디자인(글자/숫자)'이어야 해!
                    """
                    full_input = references + user_content + [prompt]
                    response = model.generate_content(full_input)
                    
                    st.success("분석 완료")
                    st.markdown("### 📋 상세 법적 검토 리포트")
                    st.markdown("---")
                    st.markdown(response.text)
                    
                    for f in glob.glob("temp_*"):
                        try: os.remove(f)
                        except: pass

            except Exception as e:
                st.error("오류가 발생했습니다.")
                st.error(f"에러 내용: {e}")

if __name__ == "__main__":
    if check_password():
        main()
