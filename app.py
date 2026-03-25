import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

# [보안] 관계자 외 접속 제한
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
        st.text_input("🔒 비밀번호 오류. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else: return True

# 1. API 키 및 모델 설정
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash" 

# ==========================================
# 👀 AI Prompt (Extraction & Strict Calculation)
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 이모지를 붙이십시오.

---
# [식품 패키지 표시사항 QC 51대 룰 기반 검증 지침]

✅ **Rule 1/2/5/8/9/12/34:** 원산지 3순위 카운트 제외, 하위 향료 생략 합법, 복합원재료 생략 합법, 수입산 유연성, 식품유형/제품명 구분 등을 시안 텍스트를 읽고 검증하라.
🔥 **Rule 13 (알레르기 텍스트 추적):** 문서 전체에서 시각적 형태가 아닌 "~함유" 키워드를 추적하라.
🔥 **Rule 14 (괄호 및 묶음 표기):** 향료 뒤에 괄호 금지. "영양강화제 2종" 숫자 합성 합법 인정.
✅ **Rule 15/17/18/19:** 건강기능식품 오인, 무첨가 기만, 영유아 타겟 명칭, 무당/무가당 문맥 분리.
🔥 **Rule 21 (영양강조 다중조건):** 비타민/무기질(칼슘 등)의 '고/풍부' 강조 판별 시 4가지 기준(100g, 100mL, 100kcal, 1회섭취참고량)의 허용치를 모두 계산해보고 하나라도 만족하면 합법.
🔥 **Rule 23 (0표시 예외구간):** 콜레스테롤(2~5mg은 5mg미만), 트랜스지방(0.2~0.5g은 0.5g미만) 등 예외 구간 범용 적용.
🔥 **Rule 30 (알레르기 차단):** 호밀/보리는 밀이 아님.
✅ **Rule 38/46/47/48/49:** 교차오염 중복 기재 위반, 숫자 통칭 개별 전개 확인, 선물포장 대조, 서류 역할 분리, 혼합제제 강제 전개 인정.
🔥 **Rule 50 (원액 기만광고 판별):** 원료 자체의 하위 성분에 정제수 등이 있는지 파악하여 기만광고 적발.
🔥 **Rule 51:** 왼쪽 열 시안, 오른쪽 열 합법 데이터 1:1 매칭 해독.

🚨 [출력 형식 강제 명령 - 7단계 목차 엄수] 🚨
아래 7단계 목차 형식을 단 하나도 빠짐없이 100% 준수하십시오.

## 1️⃣ [주표시면 및 마케팅 뱃지 (Rule 50 적용)]
- 결론: (✅ 또는 🚨)

## 2️⃣ [원재료명 및 원산지 대조 (Rule 48, 49, 50, 51 적용)]
- 🚨 [긴급 차단 명령]: "영양강화제 2종" 등 숫자 묶음 표기 지적 금지. 향료 뒤에 괄호 금지. 
| No | 시안 원재료명 (개별 전개) | 한글라벨 매칭 원료 | 배합비 순서 | 판정 및 수정안 |
|---|---|---|---|---|

## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
- 결론: (✅ 또는 🚨)
- 🚨 호밀이나 보리를 보고 '밀 함유'를 적으라는 헛소리 절대 금지.

## 4️⃣ [영양표시 및 % 기준치 정밀 검증 (Rule 11, 23, 41 적용)]
- 결론: (✅ 또는 🚨)
- 🚨 [긴급 차단 명령 - 산수 붕괴 방지]: 반드시 표의 '법적 허용오차 기준선'과 '% 검증' 칸에 당신이 어떻게 계산했는지 **수식(예: 145 * 1.2 = 174 미만)**을 타이핑하여 증명하십시오.
- 🚨 [표 양식 엄수]: 사용자가 원하는 것은 단순 추출이 아닙니다. 아래 9개 칸으로 이루어진 정밀 분석표를 반드시 작성하십시오. 틀린 항목이 있다면 '판정 및 수정안' 칸에 어떻게 고쳐야 하는지 명확히 제시하십시오.
| 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식 필수) | 1일 기준치 | 시안 % | % 검증 (계산식) | 판정 및 수정안 |
|---|---|---|---|---|---|---|---|---|

## 5️⃣ [기타 법적 의무사항]
- 결론: (✅ 또는 🚨)

## 6️⃣ [외포장(선물세트) vs 내포장(팩) 1:1 전수 대조 결과]
- 결론: (✅ 또는 🚨)
- 🚨 [포장물리 차이 허용]: 소비기한 위치(상단/측면)나 포장재질(팩/박스)이 다르게 적힌 것은 합법이므로 지적 금지.
- 식품과 직접 닿는 재질(내면 폴리에틸렌 등)이 양쪽 다 누락 없이 텍스트에 적혀있는지 스캔 결과 기술.

## 7️⃣ [종합의견 및 즉시 수정 지시사항]
- 전체적인 리뷰 및 수정이 필요한 사항 총정리.
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    # [인쇄용 CSS 핵심 패치 유지]
    print_css = """
    <style>
    @media print {
        header, footer, .stDeployButton { display: none !important; }
        .stFileUploader, .stButton, .stRadio, .stTextInput { display: none !important; }
        .hide-on-print { display: none !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)

    st.title("🏭 식품 표시사항 정밀 검토 (V7.03 - 정밀 분석 테이블 복구판)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    c_type, c_mode = st.columns(2)
    with c_type:
        product_type = st.radio("📌 1. 식품유형 선택", ("일반식품", "특수의료용도식품 / 환자식"))
    with c_mode:
        inspection_mode = st.radio("📌 2. 검토 모드 선택", ("단품(개별 팩) 검토", "선물세트(외포장/번들) 100% 일치 교차 검토"))
    
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    st.markdown("<h3 class='hide-on-print'>🎨 3. 본 시안 이미지 (외포장 또는 단품)</h3>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    img_inner_main = img_inner_info = img_inner_nutri = img_inner_extra = None

    if "선물세트" in inspection_mode:
        st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)
        st.markdown("<h3 class='hide-on-print'>🎁 4. 내포장(개별 팩) 시안 (선물세트 대조 시 필수)</h3>", unsafe_allow_html=True)
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1: img_inner_main = st.file_uploader("내포장 주표시면", type=["jpg", "png", "jpeg"], key="inner_main")
        with ic2: img_inner_info = st.file_uploader("내포장 정보표시면", type=["jpg", "png", "jpeg"], key="inner_info")
        with ic3: img_inner_nutri = st.file_uploader("내포장 영양성분표", type=["jpg", "png", "jpeg"], key="inner_nutri")
        with ic4: img_inner_extra = st.file_uploader("내포장 기타면", type=["jpg", "png", "jpeg"], key="inner_extra")

    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)
    st.markdown("<h3 class='hide-on-print'>📄 증빙 서류 (성적서/배합비/한글라벨)</h3>", unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    with d1: report_docs = st.file_uploader("시험성적서", type=["pdf", "jpg", "png"], accept_multiple_files=True)
    with d2: recipe_docs = st.file_uploader("배합비 / 레시피", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True)
    with d3: legal_docs = st.file_uploader("한글라벨 / 품목보고서", type=["pdf", "jpg", "png"], accept_multiple_files=True)

    def process_qc(ptype, imode, content_hashes):
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        
        # 🚨 안전 필터 완전 해제
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        final_prompt = f"""
        [제품유형]: {ptype}
        [검토모드]: {imode}
        위 지침에 따라 7단계 목차를 100% 준수하여 리포트를 작성하십시오.
        특히 4번 목차에서 단순 추출을 멈추고, 반드시 허용오차 범위(계산식 포함)와 1일 기준치 %를 검증한 후 수정안을 명시하십시오.
        """
        
        response = model.generate_content(
            user_content + [final_prompt], 
            generation_config=genai.types.GenerationConfig(temperature=0.0),
            safety_settings=safety_settings
        )
        
        return response.text

    if st.button("🔍 전수 룰 QC 시작", type="primary"):
        has_files = any([
            img_main, img_info, img_nutri, img_extra,
            img_inner_main, img_inner_info, img_inner_nutri, img_inner_extra,
            report_docs, recipe_docs, legal_docs
        ])
        if not has_files:
            st.warning("🚨 검토할 시안이나 서류 파일을 최소 1개 이상 업로드해주세요!")
            st.stop()

        user_content = []
        def process_single_file(f, label):
            user_content.append(f"### [분류: {label}] ###")
            if f.type.startswith("image"): 
                user_content.append(Image.open(f))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                uploaded = genai.upload_file(temp)
                while uploaded.state.name == "PROCESSING": 
                    time.sleep(1)
                user_content.append(uploaded)

        with st.spinner(f"AI 정밀 분석 및 테이블 생성 중... [{inspection_mode}]"):
            if img_main: process_single_file(img_main, "시안_외포장_주표시면")
            if img_info: process_single_file(img_info, "시안_외포장_정보표시면")
            if img_nutri: process_single_file(img_nutri, "시안_외포장_영양성분표")
            if img_extra: process_single_file(img_extra, "시안_외포장_기타면")
            
            if img_inner_main: process_single_file(img_inner_main, "시안_내포장_주표시면")
            if img_inner_info: process_single_file(img_inner_info, "시안_내포장_정보표시면")
            if img_inner_nutri: process_single_file(img_inner_nutri, "시안_내포장_영양성분표")
            if img_inner_extra: process_single_file(img_inner_extra, "시안_내포장_기타면")
            
            if report_docs: 
                for f in report_docs: process_single_file(f, "근거_성적서")
            if recipe_docs:
                for f in recipe_docs: process_single_file(f, "근거_배합비")
            if legal_docs:
                for f in legal_docs: process_single_file(f, "근거_한글라벨")

            try:
                result_text = process_qc(product_type, inspection_mode, None)
                st.markdown(result_text, unsafe_allow_html=True)
            except Exception as e: 
                st.error(f"🚨 오류: {e}")
            finally:
                for f in glob.glob("temp_*"): 
                    os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
