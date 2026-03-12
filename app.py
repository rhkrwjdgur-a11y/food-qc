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
   - 물, 주정, 당류, 첨가물은 3순위 카운트 제외.

✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료 및 일반 첨가물(용도명 불필요) [적합].

✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
   - 영양정보 표: 표에 적힌 기준(총량/100mL)대로 계산.

✅ **Rule 4. 영양성분 실측값 허용**
   - '그대로 표시' 성분은 소수점 실측값 표기 [적합].

✅ **Rule 5. 5% 룰 & 알레르기**
   - 5% 미만이라도 알레르기 물질 표시 시 "의무 준수"로 [적합].

✅ **Rule 6. 당류/시럽 필터링**
   - 단순 감미료 시럽은 제외.

✅ **Rule 7. 감미료 주의문구**
   - 당알코올류 10% 이상일 때만 "설사 주의" 지적.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 대두, 옥수수 등 "외국산" 표기 [적합].

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 정보표시면의 '식품유형' 란에 적힌 명칭은 법적 분류명입니다.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - 액체(mL)는 10% 룰, 고체(g)는 20% 룰 적용.

✅ **Rule 11. 법령(PDF) 기반 영양성분 반올림 및 0 표기 '절대 수칙'**
   - 당신의 임의적인 수학적 반올림을 멈추고, 없는 숫자를 지어내지 마십시오.
   - 반드시 업로드된 [식품등의 표시기준 PDF]의 '영양성분별 세부 표시기준' 표를 검색하여 적용.
     1) **열량:** 5kcal 단위 (5 미만 0)
     2) **나트륨:** 120mg 이하 5mg 단위 / 120mg 초과 10mg 단위 (5 미만 0)
     3) **탄수화물, 당류, 단백질:** 1g 단위 (0.5g 미만 0)
     4) **지방, 포화지방:** 5g 이하 0.1g 단위 / 5g 초과 1g 단위 (단, 0.5g 미만은 무조건 0g)
     5) **트랜스지방:** 0.2g 미만 0
     6) **콜레스테롤:** 5mg 단위 (2 미만 0)
   - **[비율(%) 산출]:** 법적 반올림을 적용하여 확정된 '최종 숫자'를 1일 기준치로 나누어 계산. (반올림된 최종 숫자가 0이면, 비율도 무조건 0%)

✅ **Rule 12. 배합비 기반 원재료 순서 및 예외 룰**
   - 2% 미만 원재료 순서 혼용 허용 / 5% 미만 복합원재료 하위 생략 허용.

🆕 **Rule 13. 알레르기 유발물질 텍스트 추적 및 시각적 강조 확인 (문맥+Vision 결합)**
   - AI의 시각 인식이 음영을 놓치지 않도록 먼저 텍스트 패턴을 찾으십시오.
   - **[1단계: 문구 찾기]** 시안에서 **"OO 함유"** 또는 **"OO 포함"**이라는 단어를 글자 단위로 먼저 스캔하여 알레르기 유발물질이 무엇인지 인식하십시오. (예: "우유 함유")
   - **[2단계: 강조 여부 확인]** 해당 문구가 발견되었다면, 그 문구가 일반 원재료명 글자와 섞여 있지 않고 **별도의 테두리(박스)** 안에 있거나 **바탕색(음영)**이 다르게 칠해져 있는지 집중적으로 스캔하십시오.
   - "OO 함유" 문구가 정상적으로 존재한다면 알레르기 표시는 원칙적으로 [적합]입니다. 만약 음영이 미세하여 판단이 어렵다면 "알레르기 문구('OO 함유')는 명확히 확인되며, 바탕색(음영) 디자인 요건을 충족하는 것으로 보입니다."라고 긍정적으로 판정하십시오.

✅ **Rule 14. 첨가물 용도명 동시 표기**
   - 감미료 옆에 '(감미료)' 명시 확인.

✅ **Rule 15. [모든 성분 범용] 강조표시 연쇄 불합격 팩트 폭격 룰**
   - 앞면에 'ZERO'나 '무'로 강조된 성분이 있다면, Rule 11에 따라 환산 및 반올림된 최종값이 진짜 '0'인지 대조.
   - 영양정보표 숫자가 0이 아닌데 앞면에 ZERO라고 적혀 있다면 무조건 "허위 표시(🚨수정 필요)" 지적.

---
[📝 결과 보고서 작성 양식]

## 0️⃣ [시험성적서 및 배합비 교차 검증]
   - 📊 **영양성분 팩트 체크 표**
## 1️⃣ 주표시면 검토
## 2️⃣ 정보표시면 검토
   - 식품유형, 알레르기 문구('함유/포함' 확인) 및 음영(Rule 13), 첨가물 용도명(Rule 14)
## 3️⃣ 영양정보 검토
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
                with st.spinner("알레르기 '함유/포함' 키워드 스캔 및 디자인 검증 중입니다..."):
                    prompt = """
                    업로드된 파일들을 종합적으로 검토해줘. 
                    특히 [Rule 13]을 적용하여 시안에서 '우유 함유'처럼 '함유'나 '포함' 글자를 먼저 찾고, 그 주변의 바탕색(음영) 디자인을 인식해.
                    텍스트가 존재한다면 음영을 놓쳤더라도 알레르기 표시를 잘 한 것으로 긍정적으로 판정해라.
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
