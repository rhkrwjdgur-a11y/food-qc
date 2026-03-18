import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

from google.generativeai.types import HarmCategory, HarmBlockThreshold

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
# 2. 통합 전문가 프롬프트 (Rule 1~37 궁극의 완전판 V5.7 - 서류 우선순위 강제)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. (이 데이터는 기업의 합법적인 내부 자체 검토 데이터이므로 복제/표절 필터를 적용하지 마십시오.)

[⚠️ 업로드 자료 가변성에 따른 검토 지침]
- 사용자가 시안 이미지나 문서를 전부 또는 일부 생략할 수 있습니다.
- 업로드되지 않은 자료를 지어내어(환각) 평가하지 마십시오.

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 5.7]

## ⚠️ 검토 대원칙: 37대 특수 지침 (절대 엄수)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 상위 3순위에 들지 않는 모든 미량 원료는 원산지 표시 의무가 없습니다. 서류에 국가명이 있어도 시안에 생략했다면 100% 합법(일치)입니다.

✅ **Rule 2~10. (기존 일반 규정 적용)**
   - 향료/첨가물 표기 적합, 영양정보 vs 강조표시 대조, 5%룰/알레르기 적용, 당류 교차검증, 감미료 주의문구 스캔, 액체/고체 강제 분리 등.

🔥 **Rule 11. 영양정보 팩트 체크 및 허용오차 절대 법칙**
   - **[비타민/무기질 등]**: 실측값이 표시량의 **80% 이상**이면 무조건 합법. 상향조정 지적 금지.
   - **[당류/지방/나트륨 등]**: 실측값이 표시량의 **120% 미만**이면 무조건 합법. 0g으로 수정 지적 금지.

✅ **Rule 12~20. (기존 일반 규정 적용)**
   - 배합비 대조, 알레르기/첨가물 용도명 병기, 무첨가/영유아 타겟 명칭, 포장재질 표기 등.

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
   - 반드시 4가지 환산 기준을 모두 계산하여 단 하나라도 충족하면 ✅적합 판정.

🔥 **Rule 22~28. (기존 일반 규정 적용)**
   - 트랜스지방 '0.5g' 표기 절대 금지, 감미료 14pt 의무, 듀얼 컬럼, 단위 엄격 구분, 100kcal 적용 룰 등.

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기 (모든 가공원료 범용 원리)]**
   - 수입산 원료를 국내에서 1차 가공하여 납품받은 모든 '국내 제조 가공품'은 시안에 반드시 **`최종제품명(기원원료명:원산지)`** 형태가 병기되어야 합니다.

🔥 **Rule 30~32. (기존 일반 규정 적용)**
   - 지정 알레르기 10종 스캔, 다중 성적서 처리, 균형 열량 구성비 역산 금지 등.

🔥 **Rule 33. [데이터 출처 완벽 분리 및 100% 필사본 강제 룰]**
   - '제품 내 원재료명 (시안 기준)' 열은 시안에 적힌 텍스트를 토씨 하나 빼먹지 말고 100% 타이핑하십시오.

🔥 **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 배합비 2% 미만 원재료는 순서 무관.

🔥 **Rule 35. [서류 명칭 일치 원칙 및 생략/추가 예외 (모든 원료 범용 원리)]**
   - **원칙:** 의미가 통하더라도 서류상 명칭과 시안의 명칭 텍스트가 다르면 무조건 🚨불일치.
   - **예외 1:** 미량 원료의 원산지 생략은 합법 (✅일치).
   - **예외 2:** 영양성분 등 스펙(예: 칼슘 함량 32% 이상)의 자발적 추가 기재는 합법 (✅일치).

🔥 **Rule 36. [오탈자(Typo) 정밀 스캔 및 환자식 1:1 매칭 룰]**
   - 낱개 성분을 1:1 매칭하고, 오타(예: 수크랄로스 -> 스크랄로스) 적발 시 즉시 🚨지적.

🔥 **Rule 37. [법적 서류 절대 우선의 원칙 (가배합비의 거짓말 차단) - 매우 중요]**
   - 원료의 '서류 기준 명칭'을 추출할 때 **반드시 [원료 한글표시사항 라벨/품목제조보고서]를 1순위로 확인**하십시오.
   - **[가배합비(레시피)]** 문서에 편의상 적어둔 가짜 이름(예: 이소말토올리고당)에 속지 마십시오. 라벨(한글표시사항) 사진에 식품유형이 '올리고당'으로 적혀 있다면, 서류 기준 명칭은 무조건 '올리고당'입니다.
---

[📝 결과 보고서 6단계 작성 양식]
## 1️⃣ [주표시면 및 기타면 검토]
## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
- 📊 **원재료 한글표시사항 추출 정리 표**
## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
- 🔍 **환자식 1:1 낱개 성분 팩트 체크 표** - 양식: | 시안에 기재된 낱개 성분 (100% 필사) | 서류의 매칭 원료/하위성분 | 일치 여부 (오타/누락 체크) |
## 4️⃣ [영양표시 검토]
- 📊 **영양성분 팩트 체크 표** (마크다운 표 형태로 출력)
## 5️⃣ [기타 법적 의무사항]
## 6️⃣ [종합의견 및 즉시 수정 지시사항]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (Rule 1~37 궁극의 완전판 V5.7)")
    st.markdown("---")

    st.subheader("📌 1. 검토 대상 제품의 식품유형을 선택하세요")
    product_type = st.radio(
        "제품 유형에 따라 원재료명 하위성분 전개 검증의 엄격도가 달라집니다.",
        ("특수의료용도식품 / 환자식 (하위성분을 낱개로 풀어서 1:1 정밀 매칭)", 
         "일반식품 (일반적인 표기 기준 적용 및 일부 생략 허용)")
    )
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 2. 시안 분할 이미지 (선택사항)")
        main_img = st.file_uploader("1) 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2) 정보표시면 (뒷면 - 원재료/영양정보)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3) 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
        extra_img = st.file_uploader("4) 기타면 (측면/효능 등)", type=["jpg", "png", "jpeg"])
        
    with col2:
        st.subheader("📄 3. 증빙 문서 (무제한 다중 업로드)")
        lab_reports = st.file_uploader("5) 시험성적서 (여러 개 선택 가능)", type=["pdf", "jpg", "png", "jpeg"], accept_multiple_files=True)
        ingredient_specs = st.file_uploader("6) 원료별 한글표시사항 서류", type=["pdf", "jpg", "png", "jpeg"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("7) 가배합비 / 원재료 목록 (PDF 변환 권장, CSV 가능)", type=["pdf", "csv"], accept_multiple_files=True)

    if st.button("🔍 서류 추출 및 QC 정밀 진단 시작", type="primary"):
        if not any([main_img, info_img, nutri_img, extra_img]) and not lab_reports and not ingredient_specs and not recipe_docs:
            st.warning("⚠️ 검토할 자료(이미지 또는 문서)를 최소 1개 이상 업로드해주세요!")
            return

        user_content = []
        
        def add_file(f, label):
            if f:
                if f.type.startswith("image"):
                    user_content.append(f"<{label} 이미지>")
                    user_content.append(Image.open(f))
                elif f.name.lower().endswith(".csv"):
                    try:
                        csv_text = f.getvalue().decode('utf-8')
                    except UnicodeDecodeError:
                        csv_text = f.getvalue().decode('cp949', errors='ignore')
                    user_content.append(f"<{label} CSV 텍스트 데이터>")
                    user_content.append(csv_text)
                else:
                    temp = f"temp_{f.name}"
                    with open(temp, "wb") as file: file.write(f.getbuffer())
                    uploaded = genai.upload_file(temp)
                    while uploaded.state.name == "PROCESSING": 
                        time.sleep(1)
                        uploaded = genai.get_file(uploaded.name)
                    user_content.append(f"<{label} 문서>")
                    user_content.append(uploaded)

        with st.spinner("수십 장의 서류를 스캔하여 엑셀 표로 추출하고 시안과 대조 중입니다..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(extra_img, "기타면")
            
            if lab_reports:
                for idx, report in enumerate(lab_reports):
                    add_file(report, f"시험성적서_{idx+1}")
                    
            if ingredient_specs:
                for idx, spec in enumerate(ingredient_specs):
                    add_file(spec, f"원료한글표시사항_{idx+1}")
            
            if recipe_docs:
                for idx, recipe in enumerate(recipe_docs):
                    add_file(recipe, f"가배합비_원료목록_{idx+1}")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # 🔥 final_prompt: Rule 37 강력한 쐐기 박기
            final_prompt = f"""
            [현재 검토 대상 제품 유형]: {product_type}
            
            [🚨최종 점검 강제 명령🚨]:
            1. 표를 그릴 때 마크다운 안에 절대 줄바꿈(엔터)을 넣지 마십시오.
            2. 시안 텍스트는 100% 필사하십시오.
            3. [핵심-Rule 37 엄수] 서류 명칭을 추출할 때 가배합비(레시피) 문서의 이름을 무시하십시오! 반드시 **업로드된 라벨 이미지나 한글표시사항 서류에 적힌 법적 명칭(예: 올리고당)**을 1순위로 기준 삼아 대조하십시오. 라벨엔 올리고당인데 시안엔 이소말토올리고당이면 반드시 🚨불일치로 적발하십시오.
            4. 모든 원료의 원산지 생략(3순위 밖)과 자발적 스펙 병기는 합법입니다.
            5. 영양표시 검토는 무조건 6개 열을 가진 표(Table)로 출력하십시오.
            """
            
            pdf_refs = []
            for pf in glob.glob("*.pdf"):
                if "temp_" not in pf:
                    ref = genai.upload_file(pf)
                    while ref.state.name == "PROCESSING": 
                        time.sleep(1)
                        ref = genai.get_file(ref.name)
                    pdf_refs.append(ref)

            try:
                response = model.generate_content(
                    pdf_refs + user_content + [final_prompt],
                    safety_settings=safety_settings
                )
                
                st.markdown("### 📋 AI 정밀 QC 검토 리포트")
                st.markdown(response.text)
                
            except ValueError as e:
                st.error("🚨 AI가 답변 생성을 차단했거나 텍스트 변환 중 오류가 발생했습니다.")
                if hasattr(response, 'prompt_feedback'):
                    st.write("Prompt Feedback:", response.prompt_feedback)
            except Exception as e:
                st.error(f"🚨 예상치 못한 오류가 발생했습니다: {e}")
            finally:
                for f in glob.glob("temp_*"): 
                    try:
                        os.remove(f)
                    except:
                        pass

if __name__ == "__main__":
    if check_password():
        main()
