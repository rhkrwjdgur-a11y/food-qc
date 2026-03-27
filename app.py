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
제공된 법령(고시)과 업로드한 자료들을 교차 검증하되, 문서에 없는 데이터를 임의로 지어내는(Hallucination) 것을 엄격히 통제합니다.

## 🚨 [⚖️ 1일 영양성분 기준치 (비율 계산 규칙)]
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- **[비율(%) 표기]:** 소수점 첫째 자리에서 반올림하여 정수(1% 단위)로 표시.
- **[1% 미만 표기]:** 계산값이 1% 미만인 경우 0%가 아니라 **"1% 미만"** 텍스트로 표시 (0g 규정에 해당하여 0g으로 적힌 경우에만 0% 표기).

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

    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V32.0 - 100% 정밀 대조판)")
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
        # 출력 토큰 넉넉하게 설정 (최대치)
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
        
        🚨 [표 렌더링 절대 강제 규칙 - 표 깨짐 원천 차단] 🚨
        1. 표(Table)를 그릴 때 무조건 행(Row)마다 **엔터(Enter, 줄바꿈)**를 치십시오.
        2. 표를 한 줄의 텍스트로 이어 붙여 쓰면 시스템 에러가 발생합니다.
        
        {prompt_text}
        """
        
        try:
            # 쾌적한 출력을 위해 스트리밍(stream) 대신 One-shot 적용
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
            with st.spinner("주표시면 텍스트 및 뱃지 정밀 대조 중..."):
                prompt = """
                ## 1️⃣ [주표시면 및 마케팅 뱃지]
                - 결론: (✅ 적합 또는 🚨 부적합/확인요망)
                - 100% 원액 강조 적합성: 
                - 마케팅 숫자(N종, N곡 등) 정합성: 
                - 제품명 연동 함량(%) 표기 여부: 
                - 기타 특이사항: 
                """
                result = run_qc_model(prompt)
                if result: st.markdown(result)

    # ==========================================================
    # 탭 2: 정보표시면 검토 (이중 작성 금지, 100% 베껴쓰기)
    # ==========================================================
    with tab2:
        st.info("정보표시면 이미지와 한글라벨, 배합비를 대조하여 원재료명, 원산지, 알레르기를 토씨 하나 안 틀리고 전수 검토합니다.")
        if st.button("▶️ 정보표시면 원재료 100% 대조 시작", key="btn_info"):
            with st.spinner("서류의 품번 및 상세 내역을 표에 다이렉트로 옮겨 적는 중..."):
                prompt = """
                🚨 [원재료명 파트 특별 명령 - 이중 작성 금지 & 100% 베껴쓰기] 🚨
                1. 원재료 파트는 산술 계산이 필요 없으므로 `<thinking>` 태그를 사용하지 마십시오.
                2. 서류(배합비, 한글라벨)에 적힌 **향료의 품번(예: JW3-241825 등), 복잡한 스펙, 괄호 안의 원산지**를 단 한 글자도 요약하거나 빼먹지 말고 **100% 완벽하게 그대로 복사해서** 아래 표의 '서류 매칭 원료' 칸에 집어넣으십시오. QC 검수는 정확한 글자 대조가 생명입니다.
                
                ## 2️⃣ [원재료명 및 원산지 대조]
                - 결론: (✅ 적합 또는 🚨 부적합)
                | No | 시안 원재료명 | 서류 매칭 원료 (품번, 상세 스펙 100% 기재) | 배합비 검증 (투입 순위 필수) | 판정 및 사유 |
                |---|---|---|---|---|
                (여기에 표 작성 시 행마다 줄바꿈 필수)
                
                ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
                - 결론: (✅ 적합 또는 🚨 부적합)
                - '~함유' 물질 원재료명 실존 여부:
                - 교차오염 경고 중복/모순 여부:
                """
                result = run_qc_model(prompt)
                if result: st.markdown(result)

    # ==========================================================
    # 탭 3: 영양성분표 검토
    # ==========================================================
    with tab3:
        st.info("영양성분표 이미지와 시험성적서를 대조하여 9대 영양소의 허용오차율 및 식약처 1일 기준치를 계산합니다.")
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("영양성분 오차 수식 계산 및 표 렌더링 중..."):
                prompt = """
                🚨 [영양성분 파트 특별 명령 - 계산식 전용 Thinking] 🚨
                1. 영양성분 파트는 정확한 수학적 검증을 위해 반드시 `<thinking>` 태그를 열고, 각 성분에 대한 허용오차 기준선 계산(0.8배, 1.2배)만 간략히 수행하십시오.
                2. 불필요하게 텍스트를 길게 쓰지 말고 수식만 적은 후 바로 닫으십시오.
                
                <thinking>
                (여기에 9개 성분의 허용오차 기준선 계산식만 간략하게 작성)
                </thinking>
                
                ## 4️⃣ [영양표시 및 % 기준치 검증]
                - 결론: (✅ 적합 또는 🚨 부적합)
                
                (여기에 위에서 계산한 결과를 바탕으로 표 작성. "정보 없음" 금지. 각 행마다 줄바꿈 필수)
                | 영양성분명 | 성적서 실측값 | 시안 표시량 | 법적 허용오차 기준선 | 1일 기준치 | 시안 % | % 검증 | 판정 |
                |---|---|---|---|---|---|---|---|
                """
                result = run_qc_model(prompt)
                if result:
                    # <thinking> 태그 분리 및 아코디언 처리
                    thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
                    if thinking_match:
                        thinking_log = thinking_match.group(1).strip()
                        report_content = result.replace(thinking_match.group(0), "").strip()
                        with st.expander("🧠 영양소 허용오차 기준선 산술 연산 로그 보기"):
                            st.markdown(f"*{thinking_log}*")
                        st.markdown(report_content)
                    else:
                        st.markdown(result)

if __name__ == "__main__":
    if check_password(): main()
