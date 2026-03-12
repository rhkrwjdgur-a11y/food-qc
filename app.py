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
# 3. 통합 전문가 프롬프트 (분할 이미지 완벽 대응 버전)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
사용자가 [주표시면], [정보표시면], [영양정보표] 등으로 시안을 분할 캡처하여 업로드할 수 있습니다. 각 이미지의 특성에 맞게 집중 판독하십시오.

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

🆕 **Rule 11. 영양정보 팩트 체크 (★분할된 '영양정보표' 이미지 집중 판독)**
   - 사용자가 '영양정보표'만 따로 자른 이미지를 올렸다면, 그 이미지의 픽셀을 100% 신뢰하여 표기된 숫자를 추출하십시오. 절대 성적서 숫자를 복사해 넣지 마십시오.
   - 환산 시 식약처 '반올림' 기준 엄수. (지방, 탄수화물, 당류, 단백질 등이 환산 후 0.5g 미만이면 무조건 0g 처리).

✅ **Rule 12. 배합비(명세서) 기반 원재료 순서 철저 대조**
   - 업로드된 [원재료 명세서] 파일의 '법적 명칭'과 분할된 [정보표시면] 이미지 속 원재료명이 정확히 일치하는지 대조하십시오.
   - 2% 미만 원재료 순서 혼용 허용 / 5% 미만 복합원재료 하위 생략 허용.

✅ **Rule 13. 알레르기 유발물질 '텍스트+디자인' 동시 확인**
   - 분할된 [정보표시면] 이미지에서 "OO 함유" 글자를 찾고, 바탕색(음영) 디자인을 인식하십시오.

✅ **Rule 14. 첨가물 용도명 동시 표기**
   - 감미료 옆에 '(감미료)' 명시 확인.

🆕 **Rule 15. [모든 성분 범용] 강조표시 연쇄 불합격 팩트 폭격 룰 (★'주표시면' 이미지 집중 판독)**
   - 분할된 [주표시면(앞면)] 이미지를 스캔하여 'ZERO'나 '무'로 강조된 성분을 모두 찾으십시오.
   - 이를 Rule 11의 영양정보 환산 최종값(0인지 아닌지)과 대조하여 허위 표기 여부를 지적하십시오.

---
[📝 결과 보고서 작성 양식]

## 0️⃣ [시험성적서 및 원재료 명세서 교차 검증]
   - 📊 **영양성분 팩트 체크 표** (Rule 11 적용: 영양정보표 크롭 이미지에서 직접 읽은 숫자 vs 법적 환산값 비교)
## 1️⃣ 주표시면 검토
   - 분할 이미지 기반 시각적 강조 문구 연쇄 검증 (Rule 15)
## 2️⃣ 정보표시면 검토
   - 명세서 대조 기반 원재료명, 알레르기 음영(Rule 13), 첨가물 용도명(Rule 14)
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
    
    st.info("💡 **[추천]** 시안 이미지를 **①주표시면(앞면) ②정보표시면(뒷면) ③영양정보표** 3장으로 잘라서 올리시면 인식률이 100%에 가까워집니다! (배합비/성적서는 PDF로 업로드)")
    uploaded_files = st.file_uploader("파일 업로드 (분할 캡처된 시안 및 PDF 자료들)", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)

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
                with st.spinner("분할 업로드된 이미지들의 각 특성을 파악하여 정밀 판독 중입니다..."):
                    prompt = """
                    업로드된 파일들을 종합적으로 검토해줘. 
                    사용자가 시안을 여러 장(앞면, 뒷면, 영양표 등)으로 잘라서 올렸을 수 있다. 영양정보 팩트 체크 표를 그릴 때는 반드시 '숫자가 빽빽하게 적힌 영양정보표 이미지'에 적힌 텍스트만 추출해서 써!
                    절대 성적서를 베껴 쓰지 마. 그리고 원재료 명세서에 있는 원료 이름과 뒷면 이미지의 글자가 토씨 하나 안 틀리고 똑같은지 대조해라.
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
