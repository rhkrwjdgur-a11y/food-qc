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
# 2. 통합 전문가 프롬프트 (Rule 1~39 + 구조 고정 템플릿 V6.0)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.0]

## ⚠️ 검토 대원칙: 39대 특수 지침 (절대 엄수)
✅ Rule 1. 미량 원료(상위 3순위 밖) 원산지 생략 합법.
✅ Rule 2~10. 일반 규정 (향료, 5%룰, 당류 검증, 감미료 주의문구 등).
🔥 Rule 11. 영양정보 허용오차(비타민 80% 이상, 당/지방 120% 미만) 절대 법칙. 상향/하향 억지 지적 금지.
✅ Rule 12~20. 배합비, 알레르기 별도 표기, 무가당 조건 등.
🔥 Rule 21~28. 영양강조 4가지 조건 100% 검증, 트랜스지방 0.5g 표기 금지, 다국어 폰트, 100kcal 기준 적용.
🔥 Rule 29. 모든 국내 제조 가공품 원료는 기원원료와 원산지 병기 필수.
🔥 Rule 30~34. 지정 알레르기 10종(실제 투입 한정) 스캔, 100% 필사본 강제, 2% 미만 자유 배열.
🔥 Rule 35. [서류 명칭 일치 원칙] 의미가 같아도 글자가 다르면 무조건 불일치(예: 올리고당 vs 이소말토올리고당). 단, 원산지 생략과 스펙 추가는 합법.
🔥 Rule 36. [오탈자 스캔] 환자식 낱개 성분 1:1 매칭 및 오타 적발.
🔥 Rule 37. [법적 서류 절대 우선] 명칭은 가배합비를 무시하고 반드시 '원료 라벨/한글표시사항'을 1순위로 채택.
🔥 Rule 38. [교차오염 전이 금지] 원료 라벨의 "같은 제조시설에서 제조" 문구(돼지고기, 쇠고기 등)는 100% 무시.
🔥 Rule 39. [동명 원료 혼선 차단] A 원료 안의 '현미'를 검증할 때 B 원료 서류의 '태국산 현미'를 끌어오지 말 것. 구역 분리 철저.
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.0 - 출력 형식 고정판)")
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

            # 🔥 final_prompt: 마크다운 템플릿 하드코딩 (절대 이 틀을 벗어나지 못하게 강제)
            final_prompt = f"""
            [현재 검토 대상 제품 유형]: {product_type}
            
            당신은 어떠한 경우에도 아래에 제공된 [결과 리포트 출력 템플릿]의 1번부터 6번까지의 마크다운 구조를 100% 동일하게 복사하여 빈칸을 채우는 방식으로만 답변해야 합니다. 줄글로 풀어쓰거나 임의로 목차를 생략/병합하면 시스템 오류가 발생합니다.

            [결과 리포트 출력 템플릿 시작]
            ## 1️⃣ [주표시면 및 기타면 검토]
            - (여기에 내용 작성)

            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            - (여기에 마크다운 표 작성)

            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
            - (여기에 마크다운 표 작성. 양식: | 시안 기재 성분 | 서류 매칭 원료 | 일치 여부 |)

            ## 4️⃣ [영양표시 검토]
            - (여기에 마크다운 표 작성. 양식: | 영양성분 | 시안 표시량 | 서류 실측값 | 환산결과 | 오차기준 | 판정 |)

            ## 5️⃣ [기타 법적 의무사항]
            - (여기에 내용 작성)

            ## 6️⃣ [종합의견 및 즉시 수정 지시사항]
            - (여기에 내용 작성)
            [결과 리포트 출력 템플릿 끝]
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
                # 🔥 핵심 해결책: temperature=0.0 을 부여하여 AI의 무작위성을 완벽 차단!
                generation_config = genai.types.GenerationConfig(
                    temperature=0.0
                )

                response = model.generate_content(
                    pdf_refs + user_content + [final_prompt],
                    safety_settings=safety_settings,
                    generation_config=generation_config
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
