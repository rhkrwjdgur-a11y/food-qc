import streamlit as st

# ==========================================
# 🚨 [UI 레이아웃 픽스] 반드시 최상단에 위치해야 넓은 화면이 유지됩니다!
# ==========================================
st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")

import google.generativeai as genai
import glob
import time
import os
import re
import tempfile
import socket
import io
import json

# 👇 [네트워크 방어] 파이썬 전체 대기 시간을 10분(600초)으로 연장
socket.setdefaulttimeout(600)

# ==========================================
# 🔠 [Google Cloud Vision API 설정] (스트림릿 클라우드 호환 버전)
# ==========================================
try:
    from google.cloud import vision
    from google.oauth2 import service_account
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

def extract_text_with_vision(file_path):
    """Google Cloud Vision API를 사용하여 이미지에서 순수 텍스트를 추출하는 함수"""
    if not VISION_AVAILABLE:
        return "🚨 [시스템 알림]: google-cloud-vision 라이브러리가 설치되지 않았습니다."
    
    try:
        # 🌟 스트림릿 비밀 금고(Secrets)에서 열쇠 꺼내기
        if "GOOGLE_VISION_KEY" in st.secrets:
            key_dict = json.loads(st.secrets["GOOGLE_VISION_KEY"])
            credentials = service_account.Credentials.from_service_account_info(key_dict)
            client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            # 로컬 컴퓨터에서 .bat 파일로 실행할 때 (환경 변수 의존)
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
    else:
        return True

# ==========================================
# 🔑 1. API 키 및 모델 설정
# ==========================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-pro"

# ==========================================
# 🛡️ AI 표 깨짐 강제 복구 함수
# ==========================================
def fix_markdown_table(text):
    text = re.sub(r'([^\n])\s*(\|\s*No\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*시안 원재료명\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*팩\(내포장\)\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*서류 매칭 원료\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*영양성분명\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'\|\s+\|', '|\n|', text)
    text = re.sub(r'([^\n])\n(\|)', r'\1\n\n\2', text)
    text = re.sub(r'\|\n\n\|', '|\n|', text)
    return text

# ==========================================
# 📚 2. 시스템 지시어
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
당신에게는 창의성, 추론 능력, 융통성이 전혀 없습니다. 오직 화면에 보이는 픽셀 단위의 글자(Text)만 있는 그대로 읽고 기계적으로 1:1 대조하는 봇(Bot)입니다.
🔥 [절대 금지: 과거 데이터 환각 및 개입 금지]: 이전 대화에서 다른 제품의 영양성분 수치나 원재료를 검토했던 기억을 현재 답변에 절대 끌어오지 마십시오. 오직 '현재 사용자가 방금 업로드한 문서' 안에 들어있는 수치만 사용하십시오.
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항(예: 당알코올 10% 컷오프, 향료 통합, 간략명 허용, 첨가물 원산지 생략 등)은 이 1:1 기계적 대조 원칙보다 무조건 최우선으로 적용하여 합법(✅) 처리하십시오.**
🔥 [오탈자 무관용 및 환각 차단 원칙]: 당신은 식품공학자가 아닙니다. 단어의 의미가 통하더라도 글자(자음/모음)가 다르면 부적합 처리하십시오. 단, 시안에 없는 원료명이나 원산지를 당신의 배경지식으로 유추하여 소설을 쓰는 행위를 엄격히 금지합니다.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 명확한 사유를 반드시 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 77대 룰북 원문 (V310.0 패치 적용)
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

## ⚠️ 검토 대원칙: 77대 품질관리 지침

🔥 **Rule 1. [원산지 3순위 산정 제외 및 임의 분류(환각) 금지]**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 완벽 적합입니다. 단, 식품유형이 '혼합제제'인 원료를 향료로 묶는 것은 금지.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치]**
   - 주표시면(앞면)에 특정 영양소 함량이 강조되어 있다면, 뒷면 영양성분표의 수치와 단 1의 오차도 없이 일치해야 합니다.

✅ **Rule 4. 영양성분 실측값 허용**
   - 식약처 허용 오차 범위를 고려하여 시험성적서 실측값을 그대로 반영한 경우 합법(적합)입니다.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 하위 성분을 전개할 의무가 없습니다.

🔥 **Rule 7. [당알코올 주의문구 개정 (10% 컷오프 룰)]**
   - 당알코올류가 최종 제품에 **10% 미만**으로 사용된 경우 주의문구 생략은 100% 합법(✅)입니다.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 (수학적 역산 절대 금지!)]**
   - 영양성분은 '해당 용량으로 환산한 실측값'을 기준으로 판단합니다.
   - **[하한선 그룹(비타민,미네랄,단백질 등)]**: `(용량 환산 실측값) >= (시안 표시량 × 0.8)` 이면 무조건 합법(✅).
   - **[상한선 그룹(열량,나트륨,당류 등)]**: `(용량 환산 실측값) <= (시안 표시량 × 1.2)` 이면 합법(✅).

🔥 **Rule 13. [알레르기 정밀 추적 및 위치 표기 절대 규칙]**
   - 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 기재되어야 합니다.

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 완벽 스나이퍼]**
   - 표 6: 유화제, 산도조절제 등은 용도명만 적어도 합법(✅)입니다. (예: 유화제 옆에 성분명을 안 적어도 됨)

🔥 **Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무가 없으므로 생략해도 합법입니다. 

🔥 **Rule 28. [원산지 3순위 완벽 필터링 및 자율표시 월권 금지 (V310.0 핵심 패치)]**
   - 정제수, 당류, 첨가물, 미생물류를 완전히 소거한 후 남은 '진짜 농수산물' 원료만 모아 배합량 순서대로 1, 2, 3순위를 재정렬하십시오.
   - ⭐ **[🚨 필수 족쇄]**: 원산지 표시 의무는 오직 최종 도출된 상위 1, 2, 3순위에만 존재합니다. 4순위 이하 원료나 식품첨가물(혼합제제, L-카르니틴, 산화아연 등)의 원산지가 패키지 시안에 없더라도 절대 부적합을 주지 마십시오! 디자이너가 4순위 이상을 적었다면 그것은 단순 강조(자율 표시)일 뿐입니다.

🔥 **Rule 29. [국내 가공 복합원재료 원산지 역추적 합법성]**
   - 난소화성말토덱스트린(물엿 기반) 등 국내 가공 복합원재료라도 하위 원물의 원산지(옥수수-러시아 등)를 역추적해 표기했다면 완벽한 합법(✅)입니다. 

🔥 **Rule 35. [🌟 범용 간략명/동의어 허용]**
   - 식약처 공식 이명(예: 카복시메틸셀룰로스나트륨 = 셀룰로스검) 표기는 100% 합법입니다.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 (외부 납품업체 차단)]**
   - 교차오염 경고 문구는 오직 사용자가 입력한 **'[우리 공장 취급 마스터 목록]'**만을 기준으로 연산하십시오. 원료 납품 업체의 스펙서 하단에 적힌 교차오염(예: 게, 돼지고기 취급 공장)을 우리 완제품 시안에 억지로 끌고 와서 누락이라고 지적하는 환각을 영구히 금지합니다.

🔥 **Rule 39. [동명 원료 및 식품유형 종속성 분리 룰]**
   - 원료 명칭이 같아도 식품유형(향료 vs 혼합제제)이 다르면 각각 분리 표기되어야 합법입니다.

🔥 **Rule 44. [혼합제제 전개 및 해체 병합 완벽 허용 룰]**
   - 혼합제제는 괄호로 묶든, 해체해서 적든 모두 완벽한 합법(✅)입니다.

🔥 **Rule 52. [영양성분 단순 명칭 강조 컷오프 완벽 검증 룰]**
   - '단백질 4g' 등 강조 시 100g, 100mL, 100kcal, 1회 섭취량 기준 중 하나라도 만족해야 합법. 부적합 시 반드시 4가지 수식을 모두 나열하여 증명할 것.

🔥 **Rule 70. [내/외포장 원재료명 100% 일치 강제]**
   - 내포장(팩)과 외포장(박스) 텍스트가 다르면 🚨부적합 처리.

🔥 **Rule 76. [OEM 업소명 타이틀 강제 스캔 (유통전문판매원)]**
   - 위탁생산 시 자사 상호명 앞에 '유통전문판매원' 직함이 없으면 부적합.

🔥 **Rule 77. [범용 식품유형 필수 주의문구 강제 스캔]**
   - 특정 식품(냉동, 젤리 등)의 필수 문구 확인. (과채음료에 질식 주의문구 억지 지적 금지)
"""

def get_sliced_rules(rule_numbers):
    rules = []
    lines = RULE_BOOK_FULL.split("\n")
    current_rule = []
    is_capturing = False
    for line in lines:
        if line.startswith("✅ **Rule") or line.startswith("🔥 **Rule"):
            match = re.search(r'Rule (\d+)', line)
            if match and int(match.group(1)) in rule_numbers:
                is_capturing = True
                if current_rule:
                    rules.append("\n".join(current_rule))
                    current_rule = []
                current_rule.append(line)
            else:
                if current_rule:
                    rules.append("\n".join(current_rule))
                    current_rule = []
                is_capturing = False
        elif is_capturing:
            current_rule.append(line)
    if current_rule:
        rules.append("\n".join(current_rule))
    return "\n\n".join(rules)

COMMON_RULES = [35, 38, 39, 44, 70]
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 52, 70] + COMMON_RULES)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 7, 13, 14, 20, 28, 29, 35, 38, 39, 44, 70, 76, 77] + COMMON_RULES)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 11, 52] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([7, 13, 38, 77] + COMMON_RULES)

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    for key in ["result_tab1", "result_tab2", "result_tab3", "result_tab4", "result_summary", "uploaded_content", "local_file_paths"]:
        if key not in st.session_state:
            st.session_state[key] = None if key != "local_file_paths" else []

    print_css = """
    <style>
    @media print {
        [data-testid="stSidebar"], header, footer, [data-testid="stHeader"], [data-testid="stToolbar"],
        .stFileUploader, .stButton, .stRadio, .stTextInput, button { display: none !important; }
        [role="tablist"], [data-baseweb="tab-list"] { display: none !important; }
        html, body, .stApp, main, .block-container, 
        [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"] {
            height: auto !important; min-height: 100% !important; max-height: none !important;
            overflow: visible !important; position: static !important; width: 100% !important; max-width: 100% !important;
            padding: 0 !important; margin: 0 !important; display: block !important;
        }
        table { page-break-inside: auto !important; width: 100% !important; border-collapse: collapse !important; }
        tr { page-break-inside: avoid !important; page-break-after: auto !important; }
        th, td { page-break-inside: avoid !important; border: 1px solid black !important; padding: 8px !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V310.0 - 환각/영역침범 영구차단판)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        with st.expander("⚙️ 고급 설정 (수동 텍스트 입력)", expanded=False):
            st.info("💡 텍스트가 너무 빽빽해서 AI가 글자를 빼먹는다면, 디자이너 원본 텍스트를 복붙해 주세요.")
            st.session_state["manual_target"] = st.text_area("📦 타겟(박스) 원재료명 직접 입력", height=100)
            st.session_state["manual_compare"] = st.text_area("🧃 비교용(팩) 원재료명 직접 입력", height=100)

        st.markdown("#### 📌 기본 검토 조건")
        product_type = st.radio("1. 식품유형", ("일반식품 (두유류 등 - 냉장표시 의무 없음)", "특수의료용도식품 / 환자식", "냉장 축산물 (우유/가공유 등)"))
        inspection_mode = st.radio("2. 검토 모드", ("단품(팩/단일포장) 기본 검토", "선물세트 박스(외포장) 교차 검토"))
        doc_type = st.radio("3. 증빙 서류 형태", ("통합 엑셀/PDF 자료 (마스터표 생략)", "개별 원료 한글라벨 무더기 (마스터표 생성)"))
        
        st.markdown("---")
        st.markdown("#### 🏭 공장 알레르기 마스터 설정")
        factory_allergens = st.text_area("우리 공장 취급 알레르기 물질 (쉼표로 구분)", "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류")
        
        st.markdown("---")
        if inspection_mode == "선물세트 박스(외포장) 교차 검토":
            st.markdown("#### 📦 [타겟] 박스(외포장) 시안")
            img_main = st.file_uploader("1️⃣ 박스 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 박스 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 박스 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 박스 기타면/측면", type=["jpg", "png", "jpeg"])
            st.markdown("#### 🔍 [비교용] 팩(내포장) 시안")
            box_main = st.file_uploader("🔍 팩(내포장) 주표시면", type=["jpg", "png", "jpeg"])
            box_info = st.file_uploader("🔍 팩(내포장) 정보표시면", type=["jpg", "png", "jpeg"])
            box_nutri = st.file_uploader("🔍 팩(내포장) 영양성분표", type=["jpg", "png", "jpeg"])
            box_extra = st.file_uploader("🔍 팩(내포장) 기타면/측면", type=["jpg", "png", "jpeg"])
        else:
            st.markdown("#### 🔹 시안 업로드")
            img_main = st.file_uploader("1️⃣ 시안 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 시안 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 시안 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 시안 기타면/측면", type=["jpg", "png", "jpeg"])
            box_main = box_info = box_nutri = box_extra = None

        st.markdown("---")
        st.markdown("#### 📑 추가 증빙 서류 (선택사항)")
        report_docs = st.file_uploader("1️⃣ 시험성적서 (영양성분 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        label_docs = st.file_uploader("2️⃣ 원료 한글라벨/스펙 (원재료 1:1 대조용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("3️⃣ 배합비/레시피 (🔥2% 순서 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            local_paths = []
            DEFAULT_DOCS_DIR = "./default_docs"

            def robust_upload(file_path, label):
                user_content.append(f"### [{label}] ###")
                
                # ⭐ [Vision API 강제 가동 족쇄]: 이미지면 무조건 OCR 가동
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    vision_text = extract_text_with_vision(file_path)
                    user_content.append(f"[Vision API 순수 OCR 추출 텍스트 (참조용)]\n{vision_text}\n---")
                
                max_retries = 5 
                for attempt in range(max_retries):
                    try:
                        up = genai.upload_file(file_path)
                        while up.state.name == "PROCESSING":
                            time.sleep(3)
                            up = genai.get_file(up.name) 
                        if up.state.name == "FAILED": raise Exception("구글 서버 처리 실패")
                        user_content.append(up)
                        return
                    except Exception as e:
                        if attempt == max_retries - 1: raise e
                        time.sleep(3 * (attempt + 1)) 

            def process(f, label):
                ext = os.path.splitext(f.name)[1] or ".png"
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(f.getbuffer())
                    safe_temp_path = tmp.name
                local_paths.append(safe_temp_path)
                robust_upload(safe_temp_path, label)

            if os.path.exists(DEFAULT_DOCS_DIR):
                auto_files = glob.glob(os.path.join(DEFAULT_DOCS_DIR, "*.pdf"))
                for file_path in auto_files:
                    robust_upload(file_path, f"자동로드_기본서류: {os.path.basename(file_path)}")

            if img_main: process(img_main, "타겟_시안_주표시면")
            if img_info: process(img_info, "타겟_시안_정보표시면")
            if img_nutri: process(img_nutri, "타겟_시안_영양성분표")
            if img_extra: process(img_extra, "타겟_시안_기타면_측면")
            if box_main: process(box_main, "비교용_정답지_시안_주표시면")
            if box_info: process(box_info, "비교용_정답지_시안_정보표시면")
            if box_nutri: process(box_nutri, "비교용_정답지_시안_영양성분표")
            if box_extra: process(box_extra, "비교용_정답지_시안_기타면_측면")
            
            if report_docs:
                for f in report_docs: process(f, "수동추가_근거_시험성적서")
            if label_docs:
                for f in label_docs: process(f, "수동추가_원료_한글라벨_및_스펙")
            if recipe_docs:
                for f in recipe_docs: process(f, "수동추가_배합비_레시피_데이터")
                
            return user_content, local_paths

        st.markdown("---")
        if st.button("🚀 전체 시스템 파일 연동 (Vision API 상시 가동)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다... (크레딧을 확인하세요)"):
                content, paths = get_uploaded_content()
                st.session_state["uploaded_content"] = content
                st.session_state["local_file_paths"] = paths
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    # ==========================================
    # 🔥 3-Pass 파이프라인
    # ==========================================
    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_missions_list: list = None):
        if not st.session_state["uploaded_content"]:
            st.warning("🚨 좌측 사이드바 하단의 [🚀 전체 시스템 파일 연동] 버튼을 먼저 눌러주세요.")
            return None

        content = st.session_state["uploaded_content"]
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        manual_target = st.session_state.get("manual_target", "")
        manual_compare = st.session_state.get("manual_compare", "")
        
        extracted_text_combined = ""

        if extract_missions_list:
            # ── PASS 1: 미션 쪼개기 ──
            extracted_results = []
            for i, mission in enumerate(extract_missions_list):
                st.toast(f"🕵️‍♂️ 분할 미션 {i+1}/{len(extract_missions_list)} 추출 중...")
                pass1_prompt = f"""
[PASS 1 - 텍스트 단일 추출 미션 (Divide & Conquer)]
⭐ 이 단계에서는 판정을 금지합니다. 오직 '아래의 특정 미션'에만 시야를 좁혀 텍스트를 추출하십시오.
🔥 [절대 금지사항]: "등", "등 다수", "중략" 이라는 표현을 절대 쓰지 마십시오. 리스트에 항목이 100개면 100개를 모두 타이핑해야 합니다.

[사용자 수동 입력 원재료명 데이터]
- 타겟(박스): {manual_target if manual_target else '없음'}
- 비교용(팩): {manual_compare if manual_compare else '없음'}

🎯 [현재 타겟 미션]:
{mission}
"""
                try:
                    pass1_response = model.generate_content(content + [pass1_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                    extracted_results.append(f"=== [미션 {i+1} 결과] ===\n" + pass1_response.text)
                except Exception as e:
                    return f"🚨 Pass 1 (단일 추출 {i+1}) 오류 발생: {e}"
            
            extracted_text_combined = "\n\n".join(extracted_results)

            # ── PASS 1.5: 자체 검증 및 사전 판정 영구 차단 ──
            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 종합 자체검증 명령]
⭐ 당신은 '매의 눈 검수관'입니다. 아래 수집된 분할 미션 결과들을 검열하십시오.
⭐ [무한 로딩 방지]: 생각 과정을 출력하지 말고, 검증/수정 완료된 텍스트만 출력하십시오.

[분할 미션 통합 텍스트]
{extracted_text_combined}

검증 규칙:
1. ⭐ [월권행위 및 사전 판정 절대 금지]: 당신은 이 단계(Pass 1.5)에서 적합(✅)이나 부적합(🚨)을 판정할 권한이 전혀 없습니다. 룰북을 적용한 어떠한 평가 내용도 출력하지 마십시오. 오직 추출된 텍스트 자체만 복원 및 교정하십시오.
2. ⭐ [오타/환각 원천 차단]: '염화콜린'을 '염화칼륨'으로 잘못 읽는 등 자동완성을 엄격히 금지합니다.
3. ⭐ [누락 및 요약 절대 금지]: "등", "등 다수", "..."을 써서 퉁치는 행위를 영구히 금지합니다. 100% 모조리 복원하십시오.
"""
            try:
                pass15_response = model.generate_content(content + [pass15_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                verified_text = pass15_response.text
            except Exception as e:
                verified_text = extracted_text_combined

        # ── PASS 2: 판정 ──
        pass2_context = ""
        if extract_missions_list:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================
⭐ [최종 자기검증 명령 및 🔥 Double-Check Protocol]
1. 위 텍스트에 존재하는 내용만을 근거로 삼으십시오. 과거 데이터 개입은 파멸을 의미합니다.
2. 🚨부적합 판정을 내리기 직전, 속으로만 텍스트를 재검색하십시오. 정말로 없을 때만 🚨부적합 처리하십시오.
"""
        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
⭐ 이미지를 직접 다시 참조하는 것을 엄격히 금지합니다. 제공된 문서와 아래 텍스트만 참조하십시오.

[제품유형]: {product_type}
[검토모드]: {inspection_mode}
[우리 공장 알레르기 마스터 목록]: {factory_allergens}

[이 탭에 적용되는 핵심 룰]
{tab_rules}

{pass2_context}

{judgment_prompt}
"""
        try:
            pass2_response = model.generate_content(content + [pass2_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
            if extract_missions_list:
                final_output = (
                    f"<pass1_log>\n{extracted_text_combined}\n</pass1_log>\n"
                    f"<pass15_log>\n{verified_text}\n</pass15_log>\n"
                    f"{pass2_response.text}"
                )
            else:
                final_output = pass2_response.text
            return fix_markdown_table(final_output)
        except Exception as e:
            return f"🚨 Pass 2 (룰 판정) 오류 발생: {e}"

    def run_qc_model(prompt_text):
        if not st.session_state["uploaded_content"]:
            return None
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        full_prompt = f"""
        [제품유형]: {product_type}\n[검토모드]: {inspection_mode}\n[우리 공장 알레르기 마스터 목록]: {factory_allergens}
        {RULE_BOOK_FULL}\n========================================\n당신은 지금 선택된 탭의 임무만 완벽하게 수행해야 합니다.\n{prompt_text}
        """
        try:
            response = model.generate_content(st.session_state["uploaded_content"] + [full_prompt], generation_config=generation_config)
            return fix_markdown_table(response.text)
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    # ==========================================
    # 결과 출력 헬퍼
    # ==========================================
    def display_result(result, tab_name=""):
        if not result: return
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)

        if pass1_match:
            pass1_log = pass1_match.group(1).strip()
            result = result.replace(pass1_match.group(0), "").strip()
            with st.expander(f"📋 Pass 1 분할 미션 원본 로그 보기 ({tab_name})"): st.markdown(f"*{pass1_log}*")

        if pass15_match:
            pass15_log = pass15_match.group(1).strip()
            result = result.replace(pass15_match.group(0), "").strip()
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 보기 ({tab_name}) ← 실제 판정에 사용된 텍스트"):
                st.info("💡 Pass 1.5는 Pass 1 추출본을 이미지와 재대조하여 오독/환각을 제거한 최종 확정 텍스트입니다.")
                st.markdown(f"*{pass15_log}*")

        if thinking_match:
            thinking_log = thinking_match.group(1).strip()
            result = result.replace(thinking_match.group(0), "").strip()
            with st.expander(f"🧠 Pass 2 판정 사전 분석 로그 보기 ({tab_name})"): st.markdown(f"*{thinking_log}*")

        st.markdown(result)

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "📊 5️⃣ 종합 보고서"])

    # ── TAB 1: 주표시면 ──
    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "주표시면(앞면) 이미지에서 '제품명, 내용량, 칼로리, 마케팅 강조문구'만 리스트로 정확히 추출하십시오."
                ]
                judgment_prompt = """
## 1️⃣ [주표시면 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망)
- ⭐ [Rule 3] 세트포장(박스) 앞면 총내용량 및 총열량 누락 검증: 
- ⭐ [Rule 47] 박스 vs 팩 뼈대 정보 교차 검증:
- ⭐ [Rule 52] 영양강조 컷오프(4대 조건) 검증:
## 🔍 [주표시면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 (월권 차단 패치 적용) ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【분할 미션 스캔 중... (시간이 다소 소요됩니다)】"):
                missions = [
                    "오직 '타겟(박스) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "오직 '비교용(팩) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "정보표시면의 '알레르기 유발물질', '교차오염 주의문구', '행정 정보(제조원 등)' 추출.",
                    "증빙 서류의 모든 원료명, 하위 성분, 원산지를 표로 추출하되, 반드시 원료명 앞에 [식품유형] 꼬리표를 강제로 붙이십시오! (예: [향료] 복숭아향)"
                ]
                
                base_tab2_warning = """
⭐ [1:1 대조 예외 절대 원칙 (Rule 2, 28, 35 우선 적용)] ⭐
🔥 [시스템 절대 족쇄: 영양정보 개입 및 이전 환각 절대 금지] 🔥
이 탭(정보표시면)에서는 절대로 '영양정보(열량, 나트륨, 당류, 칼슘 등)' 수치를 검토하거나 부적합 판정을 내리지 마십시오! 영양정보 관련 내용은 무조건 출력에서 삭제하십시오.
"""
                
                if inspection_mode == "단품(팩/단일포장) 기본 검토":
                    common_tab2_prompts = """
## 1️⃣ [원료 스펙 마스터 취합표]
| 매칭된 증빙 서류명 | 원료 제품명 | 식품유형 | 한글표시사항 (하위 전개 성분) | 원산지 | 알레르기 물질 |
|---|---|---|---|---|---|

## 2️⃣ [마스터 서류 vs 시안 법적 대조 검증]
⭐ [원산지 순위 도출 절대 원칙]: Rule 28에 따라 물, 첨가물을 완전히 소거한 후 남은 진짜 원물만으로 1, 2, 3순위를 도출하십시오. 4순위 이하 원료 및 첨가물의 원산지가 시안에 없다고 부적합을 주지 마십시오.
| 시안 표기 원재료명 (100% 나열) | 매칭된 서류 원료명 | 원산지 산정 순위 | 대조 검증 결과 | 최종 판정 |
|---|---|---|---|---|

## 3️⃣ [알레르기 및 주의사항 교차 검증 (Rule 38 적용)]
## 4️⃣ [행정 정보 교차 검증 (Rule 76 적용)]
"""
                else: # 선물세트 박스 모드
                    common_tab2_prompts = """
## 1️⃣ [원료 스펙 마스터 취합표]
| 매칭된 증빙 서류명 | 원료 제품명 | 식품유형 | 한글표시사항 (하위 전개 성분) | 원산지 | 알레르기 물질 |
|---|---|---|---|---|---|

## 2️⃣ [통합 마스터 대조 매트릭스 (Rule 70 & 서류 교차 검증 병합)]
⭐ [원산지 순위 도출 절대 원칙]: Rule 28에 따라 물, 첨가물을 소거하고 1, 2, 3순위를 도출하십시오. 첨가물 원산지 누락 지적 금지!
| 매칭된 서류 원료/항목 | 🧃 비교용(팩) 시안 | 📦 타겟(박스) 시안 | 대조 검증 결과 및 사유 (원산지 순위, 팩/박스 일치 여부 포함) | 최종 판정 |
|---|---|---|---|---|

## 3️⃣ [알레르기 및 주의사항 교차 검증 (Rule 38 적용)]
## 4️⃣ [행정 정보 교차 검증 (Rule 76 적용)]
"""
                if doc_type == "통합 엑셀/PDF 자료 (마스터표 생략)":
                    judgment_prompt = base_tab2_warning + common_tab2_prompts.replace("## 1️⃣ [원료 스펙 마스터 취합표]", "")
                else:
                    judgment_prompt = base_tab2_warning + common_tab2_prompts

                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【분할 미션 스캔 중... (잠시만 기다려주세요)】"):
                missions = [
                    "타겟(박스) 시안 및 비교용(팩) 시안의 영양정보표 내부 수치 전부 추출.",
                    "시험성적서 서류에서 각 영양성분의 실측값 데이터를 추출. (반드시 현재 업로드된 최신 문서만 참조할 것)"
                ]
                
                judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
- 결론: (✅ 적합 또는 🚨 부적합)
⭐ [계산 검증 원칙]: 성적서 실측값을 반드시 '시안의 해당 총 내용량'에 맞게 배수(예: 240mL면 * 2.4)하여 환산한 뒤, 식약처 80%/120% 룰에 대입하십시오.
⭐ [부적합 사유 증명 필수]: 🚨 부적합 판정 시 반드시 수학적 부등호 수식을 기재하여 증명하십시오.

| 영양성분 | 성적서 환산값(A) | 비교용(팩) 시안(B) | 타겟(박스) 시안(C) | 팩/박스 일치 여부 | 법적 기준선 (B의 80% 또는 120%) | 판정 및 상세 사유 (수식 증명 필수) |
|---|---|---|---|---|---|---|
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【분할 미션 스캔 중... (잠시만 기다려주세요)】"):
                missions = [
                    "전 구역 이미지를 스캔하여 필수 의무표시 3종(상담번호, 교환처, 1399 문구)과 기타 주의문구 추출."
                ]
                judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지]
- ⭐ [Rule 77] 범용 식품유형 필수 주의문구 점검:
## 🔍 [기타면/측면 전용: 오탈자 검증]
- ⭐ 오탈자 및 띄어쓰기 적발:
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    # ── TAB 5: 종합 보고서 ──
    with tab5:
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"], st.session_state["result_tab3"], st.session_state["result_tab4"]]):
                st.warning("🚨 앞의 1~4번 탭 중에서 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("최종 수정 지시서를 작성 중입니다..."):
                    def strip_logs(result):
                        if not result: return "분석 안 함"
                        result = re.sub(r'<pass1_log>.*?</pass1_log>', '', result, flags=re.DOTALL)
                        result = re.sub(r'<pass15_log>.*?</pass15_log>', '', result, flags=re.DOTALL)
                        result = re.sub(r'<thinking>.*?</thinking>', '', result, flags=re.DOTALL)
                        return result.strip()

                    combined_results = f"""
[1번 탭 결과]: {strip_logs(st.session_state.get('result_tab1'))}
[2번 탭 결과]: {strip_logs(st.session_state.get('result_tab2'))}
[3번 탭 결과]: {strip_logs(st.session_state.get('result_tab3'))}
[4번 탭 결과]: {strip_logs(st.session_state.get('result_tab4'))}
"""
                    summary_prompt = f"""
[지시]: 지금까지 사용자가 각 탭에서 검토한 내용들을 모았습니다. 실무자가 한눈에 보고 패키지를 수정할 수 있도록 종합 결론을 내려주십시오.

[기존 분석 데이터]
{combined_results}

## 📋 [최종 종합 검토 리포트]
- **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)

### 📌 [핵심 지적 사항 및 수정 지시]
(위 분석 데이터에서 '부적합(🚨)' 또는 '확인요망'이 나온 내용들만 뽑아서 번호 순 불릿 포인트로 요약하십시오.)
"""
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])

if __name__ == "__main__":
    if check_password():
        main()
