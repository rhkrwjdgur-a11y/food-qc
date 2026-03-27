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
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 문서에 없는 데이터를 임의로 생성(Hallucination)하는 것을 엄격히 통제합니다.

## 🚨 [⚖️ 1일 영양성분 기준치]
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

[54대 품질관리 지침]
Rule 1. 정제수, 주정, 당류, 식품첨가물은 원산지 3순위 산정에서 100% 제외.
Rule 2. 개별 향료명이 있더라도 시안에 '향료' 묶음 표기 합법.
Rule 3. 영양성분 수치와 마케팅 문구 대조.
Rule 4. 식약처 허용 오차 내 성적서 실측값 시안 반영 합법.
Rule 5. 배합비 5% 미만 복합원재료 하위 성분 전개 생략 합법.
Rule 6. 영양표시 당류 0g이면 실제 0.5g 미만인지 검증.
Rule 7. 당알콜류 설사 주의 문구 확인.
Rule 8. 수입 원료 '외국산/수입산' 표기 합법.
Rule 9. 제품명과 식품유형 명확히 구분.
Rule 10. 강조표시(고체/액체) 기준 분리 심사.
Rule 11. [영양 허용오차]: 시안 표시량에 0.8 또는 1.2 곱하여 기준선 도출. 역산 금지.
Rule 12. 배합비 없이 임의 추론 금지.
Rule 13. [알레르기 검증]: '~함유' 물질은 원재료명 리스트에 실존 필수 (없으면 🚨).
Rule 14. [묶음 표기]: 구연산나트륨 등 "영양강화제 2종" 표기 가능. '향료(착향료)' 병기 요구 금지.
Rule 15. 건강기능식품 오인 문구 적발.
Rule 16. 단일 국가 100% 수입 시에만 '국가명 100%' 강조.
Rule 17. 사용 금지 첨가물 배제 강조 시 기만광고(🚨).
Rule 18. 일반 식품에 영유아 타겟 명칭 사용 적발.
Rule 19. '무당(0.5g 미만)' vs '무가당(첨가 없음)' 분리.
Rule 20. 포장재질은 '직접 접촉 내면 재질'만 기재.
Rule 21. 비타민/무기질 강조 4가지 기준 중 1개만 충족해도 적합.
Rule 22. 외국어는 한글보다 작거나 같아야 함.
Rule 23. [0 표시 예외]: 트랜스지방 0.2미만 "0.5g미만", 콜레스테롤 2~5미만 "5mg미만", 포화지방 등 0.5미만 "0g" 표시 합법.
Rule 24. 무당 강조 시 14pt 이상 "감미료 함유" 표시.
Rule 25. 다중 포장 1단위 및 총 내용량 분리.
Rule 26. 고체(g), 액체(mL) 표기 단위 검사.
Rule 27. 제한 성분 100kcal 당 조건 적용 금지.
Rule 28. 배합비 하위 성분 원산지 과잉 요구 금지 (Rule 53 예외).
Rule 29. 복합원재료 자체 원산지만 확인.
Rule 30. 호밀, 귀리, 보리는 '밀' 알레르기 아님.
Rule 31. 성적서 병합 대조.
Rule 32. 열량 구성비 역산만으로 부적합 처리 금지.
Rule 33. 서류/시안 수치 구분.
Rule 34. 2% 미만 원료 기재 순서 무관.
Rule 35. 동일 간략 명칭 적합.
Rule 36. 오탈자 검수.
Rule 37. 서류 최우선 판별.
Rule 38. 교차오염 주의사항에 투입 원료 중복 기재 시 부적합(🚨).
Rule 39. 복합원재료 독립 대조.
Rule 40. 열량 5kcal 단위 반올림 우선.
Rule 41. % 계산 시 한국 식약처 수치만 대입.
Rule 42. 완제품 성적서 사용.
Rule 43. 판독 불가 시 육안 확인 요망 처리.
Rule 44. 혼합제제 하위 전개 적합성.
Rule 45. 선택적 마케팅 누락 지적 금지.
Rule 46. 제품명 숫자 강조 시 하위 전개 대조.
Rule 47. 내/외포장 물리적 차이 예외 인정, 텍스트 100% 일치 강제.
Rule 48. 배합비(순서)와 한글라벨(최종 명칭) 역할 분리.
Rule 49. 혼합제제 해체 병합 전개 합법.
Rule 50. [원액/100% 판별]: 납품 원료가 순수 원액이면 제품 공정 섞여도 'OO원액' 합법.
Rule 51. PDF 데이터 1:1 매칭.
Rule 52. [모순 탐지]: 마케팅 숫자와 실제 원료 쉼표 개수 정합성 카운트.
Rule 53. [제품명 연동 강제]: 제품명에 원재료 포함 시, ①앞면 함량(%) 표기, ②뒷면 원산지 무조건 표기 (누락 🚨).
Rule 54. [비율 생략 검증]: 단일 원료 2개국 표기 시 비율(%) 누락되면 🚨확인 요망.
"""

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    print_css = """
    <style>
    @media print {
        header, footer, .stDeployButton { display: none !important; }
        .stFileUploader, .stButton, .stRadio, .stTextInput, .stTabs { display: none !important; }
        .hide-on-print { display: none !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)

    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V30.0 - 백그라운드 추론 복구판)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

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
        
        🚨 [사전 연산(Thinking) 강제 명령 - 정확성 확보] 🚨
        당신은 본 리포트의 마크다운 표를 그리기 전에, 반드시 첫 글자를 `<thinking>` 태그로 열어서 각 룰에 대한 데이터 매칭과 수식 계산 과정을 명확히 기록하십시오. 이 과정을 생략하면 계산 오류가 발생합니다.
        
        <thinking>
        (여기에 데이터 추출 결과 및 허용오차 산술 연산 과정 상세 기록)
        </thinking>
        
        🚨 [표 렌더링 절대 강제 규칙 - 표 깨짐 방지] 🚨
        사고 과정이 끝난 후 아래의 정식 리포트를 출력할 때, 표(Table)는 절대 한 줄로 이어서 쓰면 안 됩니다.
        
        [🟢 올바른 표 작성 예시 - 반드시 행마다 엔터(Enter)를 칠 것]
        | No | 원료명 | 판정 |
        |---|---|---|
        | 1 | 정제수 | 적합 |
        | 2 | 사과 | 적합 |
        
        [❌ 절대 금지 예시 - 이렇게 쓰면 시스템 에러가 발생합니다]
        | No | 원료명 | 판정 | |---|---|---| | 1 | 정제수 | 적합 |
        
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
            with st.spinner("주표시면 마케팅 문구 및 뱃지 분석 중..."):
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
                    thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if thinking_match:
                        thinking_log = thinking_match.group(1).strip()
                        report_content = result.replace(thinking_match.group(0), "").strip()
                        with st.expander("🧠 AI 백그라운드 추론 연산 과정 (로그 보기)"):
                            st.markdown(f"*{thinking_log}*")
                        st.markdown(report_content)
                    else:
                        st.markdown(result)

    # ==========================================================
    # 탭 2: 정보표시면 검토
    # ==========================================================
    with tab2:
        st.info("정보표시면 이미지와 한글라벨, 배합비를 대조하여 원재료명, 원산지, 알레르기 유발물질을 검토합니다.")
        if st.button("▶️ 정보표시면 분석 시작", key="btn_info"):
            with st.spinner("원재료 매칭 및 알레르기 교차오염 분석 중... (표 렌더링)"):
                prompt = """
                ## 2️⃣ [원재료명 및 원산지 대조]
                - 결론: (✅ 적합 또는 🚨 부적합)
                
                (반드시 위의 🟢올바른 표 작성 예시를 참고하여 각 행마다 완벽히 줄바꿈을 적용하여 그리십시오. '배합비 검증' 칸에 투입 순위 필수 기입)
                | No | 시안 원재료명 | 한글라벨 매칭 원료 | 배합비 검증 (투입 순위 필수) | 판정 및 수정안 |
                |---|---|---|---|---|
                
                ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
                - 결론: (✅ 적합 또는 🚨 부적합)
                - '~함유' 물질 원재료명 실존 여부:
                - 교차오염 경고 중복/모순 여부:
                """
                result = run_qc_model(prompt)
                if result:
                    thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if thinking_match:
                        thinking_log = thinking_match.group(1).strip()
                        report_content = result.replace(thinking_match.group(0), "").strip()
                        with st.expander("🧠 AI 백그라운드 추론 연산 과정 (로그 보기)"):
                            st.markdown(f"*{thinking_log}*")
                        st.markdown(report_content)
                    else:
                        st.markdown(result)

    # ==========================================================
    # 탭 3: 영양성분표 검토
    # ==========================================================
    with tab3:
        st.info("영양성분표 이미지와 시험성적서를 대조하여 9대 영양소의 허용오차율 및 식약처 1일 기준치를 깐깐하게 계산합니다.")
        if st.button("▶️ 영양성분표 분석 시작", key="btn_nutri"):
            with st.spinner("영양성분 허용오차 및 기준치를 계산 중입니다... (표 렌더링)"):
                prompt = """
                ## 4️⃣ [영양표시 및 % 기준치 검증]
                - 결론: (✅ 적합 또는 🚨 부적합)
                
                (반드시 위의 🟢올바른 표 작성 예시를 참고하여 각 행마다 완벽히 줄바꿈을 적용하여 그리십시오. 계산 수식 명시)
                | 영양성분명 | 성적서 실측값 | 시안 표시량 | 법적 허용오차 기준선 | 1일 기준치 | 시안 % | % 검증 | 판정 |
                |---|---|---|---|---|---|---|---|
                """
                result = run_qc_model(prompt)
                if result:
                    thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if thinking_match:
                        thinking_log = thinking_match.group(1).strip()
                        report_content = result.replace(thinking_match.group(0), "").strip()
                        with st.expander("🧠 AI 백그라운드 추론 연산 과정 (로그 보기)"):
                            st.markdown(f"*{thinking_log}*")
                        st.markdown(report_content)
                    else:
                        st.markdown(result)

if __name__ == "__main__":
    if check_password(): main()
