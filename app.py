import streamlit as st
import google.generativeai as genai
import os
import tempfile
import socket
import io
import json

# ==========================================
# 🚨 [UI 레이아웃 픽스] 반드시 최상단에 위치!
# ==========================================
st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")

# 네트워크 타임아웃 연장 (대용량 검토용)
socket.setdefaulttimeout(600)

# ==========================================
# 🔠 [Google Cloud Vision API 설정 (OCR)]
# ==========================================
try:
    from google.cloud import vision
    from google.oauth2 import service_account
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

@st.cache_data(show_spinner=False)
def extract_text_with_vision(file_path):
    if not VISION_AVAILABLE:
        return "🚨 [시스템 알림]: google-cloud-vision 라이브러리가 설치되지 않았습니다."
    try:
        if "GOOGLE_VISION_KEY" in st.secrets:
            key_dict = json.loads(st.secrets["GOOGLE_VISION_KEY"])
            credentials = service_account.Credentials.from_service_account_info(key_dict)
            client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            client = vision.ImageAnnotatorClient()
            
        with io.open(file_path, 'rb') as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        response = client.document_text_detection(image=image)
        if response.error.message:
            return f"🚨 [Vision API 에러]: {response.error.message}"
        return response.full_text_annotation.text
    except Exception as e:
        return f"🚨 [Vision API 실행 오류]: {e}"

# ==========================================
# 🧠 [Gemini API 설정]
# ==========================================
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.warning("🚨 secrets.toml에 GEMINI_API_KEY가 없습니다.")

generation_config = {
  "temperature": 0.0,
  "top_p": 0.1,
  "top_k": 32,
  "max_output_tokens": 8192,
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config
)

# ==========================================
# 📜 [마스터 프롬프트 딕셔너리 - V331.00 엔진]
# ==========================================
PROMPT_TEMPLATES = {
    "tab1_raw_materials": """
당신은 대한민국 최고의 대기업 식품 법무팀 소속 QC 수석 검토관입니다.
첨부된 [서류]와 [포장지 시안]을 대조하여 원재료명 표시사항의 합법성을 검사하십시오.

[🚨 출처 철통 격리 (Source Isolation)]
- 서류에 없는 원료를 시안에서 가져와 환각(Hallucination)으로 만들어내지 마십시오.

[🎯 투트랙 스마트 맵핑 & 5% 룰]
- Rule 35, 90, 91: 시럽/첨가물/동의어는 유연하게 묶되, 과일류/유가공품 등 본질 원물은 엄격하게 구분할 것.
- Rule 5: 5% 미만 복합원재료의 하위 성분은 모두 나열하되, 비율 순서대로 기재.
- Rule 44: '비타민E혼합제제' 등 껍데기 명칭만 적는 것은 위법. 하위 성분 필수 기재.
- Rule 84: 'ORGANIC' 등 유기농 문구는 인증서 증빙 필수.

[🔥 데이터 누락 시 하이브리드 검증 로직]
마스터 서류에 특정 원료(예: 원액두유)의 '한글표시사항' 텍스트가 누락되어 있다면 억지로 유추하지 말고 "서류상 한글표시사항 누락으로 텍스트 직접 대조 불가"라고 명시할 것.
단, 여기서 멈추지 말고 해당 원료의 다른 속성 데이터(원산지, 알레르기 물질, 추출물 여부)를 활용하여 [원산지 표기 의무], [고형분 함량 표기 의무] 등이 포장지 시안에 잘 지켜졌는지 대체(Cross) 검증을 반드시 수행할 것.
""",

    "tab2_nutrition": """
당신은 식품 영양표시 QC 검토관입니다. [포장지 시안]의 영양정보와 [서류]를 대조하십시오.

[⭐ Rule 21, 52: 영양강조표시 4중 교차 검증 (치트키 로직)]
영양강조표시(예: 단백질 n g 함유 등)의 법적 적합성을 평가할 때, '단일 기준(1단위 포장당)'에 미달한다고 해서 성급하게 부적합 판정을 내리지 마십시오.
반드시 아래 4가지 기준을 모두 수학적으로 교차 계산하여, 단 1개라도 충족하면 무조건 [✅ 적합]으로 판정하십시오.
  ① 100g(또는 100mL)당 기준
  ② 1회 섭취참고량당 기준
  ③ 총 내용량당 기준
  ④ 100kcal당 기준 (가장 중요! 용량 기준 미달 시 반드시 100kcal당 수치로 환산하여 기준치의 5% 등을 만족하는지 증명할 것)

[🛑 Rule 68: 다포장/세트포장]
외포장 주표시면에 낱팩의 수치만 기준량 없이 적혀있다면 "소비자 오인·혼동 (기준량 명시 요망)" 판정을 내릴 것.
""",

    "tab3_allergens": """
알레르기 유발물질 혼입 및 의무 표시사항을 검토합니다.
서류에 기재된 알레르기 유발물질과 포장지 시안을 철저히 대조하여 누락 및 오탈자를 적발하십시오.
""",

    "tab4_legal": """
의무표시사항(식품유형, 소비기한, 보관방법, 업소명 및 소재지 등)의 텍스트가 식약처 고시에 부합하는지 스캔하십시오.

[🇰🇷 특별 룰: 소재지 '대한민국' 표기 감지]
시안의 '제조원' 또는 '유통전문판매원' 주소지(소재지) 텍스트에 "대한민국" 이라는 국가명이 추가로 표기되어 있는지 스캔하십시오.
만약 "대한민국"이 적혀 있다면, 부적합으로 단정하지 말고 아래 문구를 [주의/확인 요망] 항목으로 반드시 출력하십시오.
➡️ "⚠️ [수출 겸용 확인 요망]: 시안의 소재지에 '대한민국'이 표기되어 있습니다. 원칙적으로는 품목제조보고서와 일치해야 하나, 수출 제품(또는 수출/내수 겸용)일 경우 수입국 통관 요건에 따른 합법적인 추가 기재입니다. 수출용이 맞는지 실무 부서에 최종 확인하시기 바랍니다."
""",

    "tab5_holistic": """
당신은 대기업 식품 법무팀장입니다. 지금까지의 결과를 종합하여 입체적인 최종 보고서를 작성하십시오.

[파트 1: 마케팅 및 부당광고 리스크]
- 허위, 과대, 기만, 오인·혼동 리스크 검토 (예: "베베" 표기로 영유아용 오인, 타 첨가물이 있는데 "100%" 표기 등)

[🔥 파트 2: 룰북 사각지대 및 패키지의 구조적/법적 모순 스캔]
- 단순 주의문구 체크를 넘어서, 기계적 룰(1~87)이 놓칠 수 있는 패키지 전반의 '법적 이상 징후'를 고시 원문 맥락을 바탕으로 추론하십시오.
- 예시: ① 앞면의 제품명/이미지와 뒷면 배합비 간의 법적 모순 (향료만 썼는데 과일 원물 사진을 과도하게 크게 쓴 경우 등), ② 식품유형과 어울리지 않는 부적절한 규격 표기, ③ 타겟 고객층을 표방함에 따라 추가로 강제되는 특수 법적 요건(임산부, 환자용 등) 누락 여부 등.
"""
}

# ==========================================
# 🖥️ [Streamlit UI 구성]
# ==========================================
st.title("🏭 식품 QC 마스터 시스템 (V331.00 - 완전체 버전)")
st.markdown("""
**[V331.00 업데이트 핵심 적용 사항]**
- 🇰🇷 **수출 겸용 소재지 확인 룰:** 주소지 내 '대한민국' 감지 및 예외 처리 가이드 반영 완료
- 🧩 **결측치 하이브리드 검증:** 서류 내 한글라벨 누락 시, 메타 데이터(고형분/원산지) 기반 우회 추적
- 📊 **영양강조 4중 방어막:** 100kcal 환산 로직 강제화 (Rule 21, 52)
- 👁️ **법무팀장 입체 추론:** 파트 1(마케팅 기만) / 파트 2(구조적 법률 모순 사각지대) 역할 완벽 분리
""")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 기준 서류 업로드 (품목제조보고서, 마스터표 등)")
    doc_files = st.file_uploader("PDF, PNG, JPG 파일", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="docs")

with col2:
    st.subheader("🎨 포장지 시안 업로드")
    design_files = st.file_uploader("포장지 전면/후면 시안 파일", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="designs")

# ==========================================
# ⚙️ [분석 실행 엔진]
# ==========================================
if st.button("🚀 전체 입체 교차 검증 실행", type="primary", use_container_width=True):
    if not doc_files and not design_files:
        st.warning("⚠️ 서류나 시안 파일을 업로드해 주세요.")
    else:
        with st.spinner("🕵️‍♂️ QC 마스터 룰북 대조 및 4중 교차 검증 진행 중... (최대 3~5분 소요)"):
            
            # 1. 파일 처리 및 Vision API 텍스트 추출
            uploaded_docs_content = []
            for file in doc_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = tmp.name
                text = extract_text_with_vision(tmp_path) if VISION_AVAILABLE else "Vision API 비활성화됨"
                uploaded_docs_content.append(text)
                
            uploaded_design_content = []
            uploaded_design_parts = []
            for file in design_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = tmp.name
                
                # Gemini Multi-modal 파트 생성
                file_part = {
                    "mime_type": file.type,
                    "data": file.getvalue()
                }
                uploaded_design_parts.append(file_part)
                
                # OCR 텍스트 추출
                text = extract_text_with_vision(tmp_path) if VISION_AVAILABLE else "Vision API 비활성화됨"
                uploaded_design_content.append(text)

            combined_docs_text = "\n\n--- [서류 텍스트] ---\n".join(uploaded_docs_content)
            combined_design_text = "\n\n--- [포장지 OCR 텍스트] ---\n".join(uploaded_design_content)

            # 2. 탭 UI 생성
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "원재료명 (결측치 우회)", 
                "영양강조 (100kcal 방어)", 
                "알레르기", 
                "의무표시 (대한민국 감지)", 
                "법률 모순 스캔 (파트1/2)"
            ])

            # 공통 입력 데이터 페이로드
            base_prompt_data = [
                f"### [기준 서류 데이터] ###\n{combined_docs_text}\n\n",
                f"### [포장지 OCR 데이터] ###\n{combined_design_text}\n\n",
                "### [포장지 시안 시각 데이터] ###\n"
            ] + uploaded_design_parts

            # [Tab 1: 원재료]
            with tab1:
                response_1 = model.generate_content([PROMPT_TEMPLATES["tab1_raw_materials"]] + base_prompt_data)
                st.write(response_1.text)

            # [Tab 2: 영양정보]
            with tab2:
                response_2 = model.generate_content([PROMPT_TEMPLATES["tab2_nutrition"]] + base_prompt_data)
                st.write(response_2.text)

            # [Tab 3: 알레르기]
            with tab3:
                response_3 = model.generate_content([PROMPT_TEMPLATES["tab3_allergens"]] + base_prompt_data)
                st.write(response_3.text)

            # [Tab 4: 의무표시]
            with tab4:
                response_4 = model.generate_content([PROMPT_TEMPLATES["tab4_legal"]] + base_prompt_data)
                st.write(response_4.text)

            # [Tab 5: 종합 교차판정]
            with tab5:
                response_5 = model.generate_content([PROMPT_TEMPLATES["tab5_holistic"]] + base_prompt_data)
                st.write(response_5.text)
                
            st.success("🎉 모든 탭의 심층 교차 검증 및 예외 스캔이 완료되었습니다!")
