import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os
import re

# ==========================================
# 🔒 [보안] 시스템 접속 비밀번호 설정
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == "2082":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("🔒 시스템 접속 비밀번호 입력", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🚨 비밀번호 오류. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else: return True

# ==========================================
# 🔑 1. API 키 및 모델 설정
# ==========================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash" 

# ==========================================
# 📚 2. 통합 전문가 프롬프트 
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 이모지를 붙이십시오.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 당신의 판단은 100% 논리적으로 일관되어야 하며, 문서에 없는 데이터를 임의로 생성(Hallucination)하는 것을 엄격히 통제합니다.

## 🚨 [⚖️ 1일 영양성분 기준치]
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

(참고: 54대 품질관리 지침은 각 구간별 검토 시 엄격하게 적용됩니다.)
"""

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (3구간 분할 렌더링)")
    st.markdown("<hr>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        product_type = st.radio("📌 1. 식품유형", ("일반식품", "특수의료용도식품 / 환자식"))
        inspection_mode = st.radio("📌 2. 검토 모드", ("단품(개별 팩) 검토", "선물세트 교차 검토"))
        
        st.markdown("---")
        img_main = st.file_uploader("1️⃣ 주표시면(앞면)", type=["jpg", "png", "jpeg"])
        img_info = st.file_uploader("2️⃣ 정보표시면(뒷면)", type=["jpg", "png", "jpeg"])
        img_nutri = st.file_uploader("3️⃣ 영양성분표", type=["jpg", "png", "jpeg"])
        
        st.markdown("---")
        report_docs = st.file_uploader("📑 시험성적서", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("📑 배합비", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        legal_docs = st.file_uploader("📑 한글라벨", type=["pdf", "jpg", "png"], accept_multiple_files=True)

    def get_uploaded_content():
        user_content = []
        def process(f, label):
            user_content.append(f"### [{label}] ###")
            if f.type.startswith("image"): 
                user_content.append(Image.open(f))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                up = genai.upload_file(temp)
                while up.state.name == "PROCESSING": time.sleep(1)
                user_content.append(up)
        
        if img_main: process(img_main, "시안_주표시면")
        if img_info: process(img_info, "시안_정보표시면")
        if img_nutri: process(img_nutri, "시안_영양성분표")
        if report_docs: 
            for f in report_docs: process(f, "근거_시험성적서")
        if recipe_docs: 
            for f in recipe_docs: process(f, "근거_배합비")
        if legal_docs: 
            for f in legal_docs: process(f, "근거_한글라벨")
            
        for f in glob.glob("temp_*"): os.remove(f)
        return user_content

    def run_qc_model(prompt_text):
        content = get_uploaded_content()
        if not content:
            st.warning("🚨 업로드된 파일이 없습니다. 파일을 먼저 업로드해 주십시오.")
            return None
            
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=8192)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        
        full_prompt = f"""
        [제품유형]: {product_type}
        [검토모드]: {inspection_mode}
        
        🚨 [출력 및 보안 강제 명령] 🚨
        당신의 응답은 반드시 `<thinking>` 태그로 시작하십시오.
        시스템 안정성을 위해 `<thinking>` 내부에는 검토에 대한 **아주 간략한 요약을 한두 문장으로만 작성**하십시오. 구체적인 중간 연산 과정이나 불필요한 세부 논리 전개는 모두 생략하십시오.
        
        <thinking>
        (검토에 대한 아주 간략한 요약을 한두 문장으로 작성하십시오.)
        </thinking>
        
        {prompt_text}
        """
        
        try:
            response = model.generate_content(content + [full_prompt], generation_config=generation_config, safety_settings=safety_settings)
            return response.text
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3 = st.tabs(["1️⃣ 주표시면 (마케팅/뱃지)", "2️⃣ 정보표시면 (원재료/알레르기)", "3️⃣ 영양성분표 (오차 연산)"])

    # ==========================================================
    # 탭 1: 주표시면 검토
    # ==========================================================
    with tab1:
        st.info("주표시면 이미지와 배합비를 대조하여 마케팅 문구, 함량 표기, 제품명 연동 규정 등을 검토합니다.")
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("주표시면 데이터를 분석 중입니다..."):
                prompt = """
                ## 1️⃣ [주표시면 및 마케팅 뱃지]
                - 결론: (✅ 적합 또는 🚨 부적합/확인요망)
                - 100% 원액 강조 적합성: 
                - 마케팅 숫자(N종, N곡 등) 정합성: 
                - 제품명 연동 함량(%) 표기 여부: 
                - 기타 특이사항: 
                """
                result = run_qc_model(prompt)
                if result:
                    # 요약 태그 숨기기
                    match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if match:
                        st.markdown(result.replace(match.group(0), "").strip())
                    else:
                        st.markdown(result)

    # ==========================================================
    # 탭 2: 정보표시면 검토 
    # ==========================================================
    with tab2:
        st.info("정보표시면 이미지와 한글라벨, 배합비를 대조하여 원재료명, 원산지, 알레르기 유발물질을 검토합니다.")
        if st.button("▶️ 정보표시면 분석 시작", key="btn_info"):
            with st.spinner("원재료 및 알레르기 정보를 대조 중입니다..."):
                prompt = """
                ## 2️⃣ [원재료명 및 원산지 대조]
                - 결론: (✅ 적합 또는 🚨 부적합)
                | No | 시안 원재료명 | 한글라벨 매칭 원료 | 배합비 검증 (투입 순위) | 판정 및 수정안 |
                |---|---|---|---|---|
                (여기에 표 작성 시 반드시 각 행 끝에 줄바꿈을 넣으십시오)
                
                ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
                - 결론: (✅ 적합 또는 🚨 부적합)
                - '~함유' 물질 원재료명 실존 여부:
                - 교차오염 경고 중복/모순 여부:
                """
                result = run_qc_model(prompt)
                if result:
                    match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if match:
                        st.markdown(result.replace(match.group(0), "").strip())
                    else:
                        st.markdown(result)

    # ==========================================================
    # 탭 3: 영양성분표 검토
    # ==========================================================
    with tab3:
        st.info("영양성분표 이미지와 시험성적서를 대조하여 9대 영양소의 허용오차율 및 식약처 1일 기준치를 계산합니다.")
        if st.button("▶️ 영양성분표 분석 시작", key="btn_nutri"):
            with st.spinner("영양성분 허용오차 및 기준치를 계산 중입니다..."):
                prompt = """
                ## 4️⃣ [영양표시 및 % 기준치 검증]
                - 결론: (✅ 적합 또는 🚨 부적합)
                | 영양성분명 | 성적서 실측값 | 시안 표시량 | 법적 허용오차 기준선 | 1일 기준치 | 시안 % | % 검증 | 판정 |
                |---|---|---|---|---|---|---|---|
                (여기에 열량, 나트륨, 탄수화물, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤, 단백질 9개 성분을 계산하여 표를 작성하십시오. 행 끝에 줄바꿈 필수.)
                """
                result = run_qc_model(prompt)
                if result:
                    match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if match:
                        st.markdown(result.replace(match.group(0), "").strip())
                    else:
                        st.markdown(result)

if __name__ == "__main__":
    if check_password(): main()
