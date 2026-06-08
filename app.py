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
이전 대화의 다른 제품 시안 데이터를 현재 검토에 절대 개입시키지 마십시오. 오직 현재 사용자가 업로드한 문서만을 팩트로 사용하십시오.
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항은 무조건 최우선으로 적용하여 합법(✅) 처리하십시오.**
🔥 [오탈자 무관용 및 환각 차단 원칙]: 단어의 의미가 통하더라도 글자가 단 하나라도 다르면 무조건 부적합 처리하십시오. 기계의 배경지식으로 글자를 유추하여 소설을 쓰는 행위를 엄격히 금지합니다.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 명확하고 구체적인 사유를 반드시 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 77대+α 룰북 원문 (V310.0 무결점 패치 적용)
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산/무기질]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

## ⚠️ 검토 대원칙: 핵심 품질관리 지침

🔥 **Rule 1. [원산지 3순위 산정 제외 및 임의 분류 금지]**
   - 정제수, 주정, 당류, 첨가물은 배합비율이 높아도 원산지 3순위 산정에서 제외됩니다. ('나한과추출분말' 등 임의 첨가물 판정 금지)

✅ **Rule 2. 향료 및 첨가물 명칭 유연화**
   - 식품유형이 '향료'인 원료는 '향료'로 묶어 표기 가능합니다. (혼합제제는 묶기 불가)

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치]**
   - 앞면에 강조된 함량은 뒷면 영양표시 수치와 100% 일치해야 합니다.

🔥 **Rule 5. [복합원재료 5% 룰]**
   - 배합비 5% 미만인 복합원재료는 하위 성분을 전개할 의무가 없습니다.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 (수학적 역산 절대 금지!)]**
   - **[하한선(단백질/미네랄 등)]**: `(성적서 환산 실측값) >= (시안 표시량 × 0.8)` 이면 ✅합법.
   - **[상한선(열량/당류 등)]**: `(성적서 환산 실측값) <= (시안 표시량 × 1.2)` 이면 ✅합법.

🔥 **Rule 28. [원산지 3순위 완벽 필터링 (숫자 세기 환각 금지)]**
   - 물, 당류, 첨가물, '미생물(포스트바이오틱스 등)'을 소거한 후 남은 '진짜 농수산물' 원료만으로 1, 2, 3순위를 산정하십시오. 
   - ⭐ **[족쇄]**: 4순위 이하 원료나 첨가물 원산지가 시안에 없더라도 절대 부적합을 주지 마십시오.

🔥 **Rule 35. [범용 간략명/동의어 허용]**
   - 식약처 이명(구연산나트륨=구연산삼나트륨) 및 내부 코드 생략 완벽 허용.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 (수학적 차집합 수식 필수)]**
   - ⭐ **[족쇄]**: 교차오염은 무조건 `[교차오염 정답지] = [공장 취급 마스터] - [직접 투입 알레르기 물질]` 수식을 도출해야 합니다. 타사 납품업체 교차오염 억지 적용 금지.

🔥 **Rule 52. [영양성분 강조표시 컷오프 (수학 증명 강제)]**
   - '고/풍부/무/저' 강조 시 100g, 100mL, 100kcal, 1회섭취량 4가지 조건 중 하나라도 충족해야 합법. 부적합 판정 시 4가지 수식을 모두 증명하십시오.

🔥 **Rule 59. [CS 및 1399 3종 Global Scan 강제]**
   - '소비자상담실', '부정불량식품 1399', '반품/교환처'는 측면뿐 아니라 패키지 **어디에든 하나라도 있으면 합법**입니다. 전체 수집 텍스트를 모두 뒤지십시오.

🔥 **Rule 70. [내/외포장 100% 일치 강제]**
   - 팩과 박스 텍스트는 픽셀 단위로 대조하여 다르면 🚨부적합.

🔥 **Rule 76. [OEM 업소명 타이틀 강제 스캔]**
   - 제조원이 타사면 자사 상호명 앞에 반드시 '유통전문판매원' 또는 '판매원' 타이틀이 있어야 합니다.

🔥 **Rule 77. [범용 필수 주의문구 스캔]**
   - 냉동, 고카페인, 젤리 등 필수 문구. (액상 음료에 질식 주의 억지 적용 금지)

🔥 **Rule 80. [세트포장(박스) 영양정보 레이아웃 강제 (V310.0 신설)]**
   - 박스 시안의 영양정보표 상단에는 반드시 **`총 내용량 OOO mL (OOO mL X O개입)`** 및 **`1개(OOO mL)당`** 이라는 포맷이 정확히 존재해야 합법입니다. 

🔥 **Rule 81. [영양표시 하단 면책 문구 토시 대조 (V310.0 신설)]**
   - 영양표시 하단에는 **`"1일 영양성분 기준치에 대한 비율(%)은 2,000 kcal 기준이므로 개인의 필요 열량에 따라 다를 수 있습니다."`** 라는 문구가 토씨, 띄어쓰기 하나 틀리지 않고 100% 일치해야 합법(✅)입니다.

🔥 **Rule 82. [영양소 법정 단위 엄격 검증 (V310.0 신설)]**
   - 비타민A: `μg RE` / 비타민D, B12, 엽산 등: `μg` / 비타민E: `mg α-TE` / 비타민C, B1, B2, B6: `mg`. (아래첨자 및 대소문자까지 완벽하게 매칭되어야 합법)
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

COMMON_RULES = [35, 38, 70]
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 52] + COMMON_RULES)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 11, 28, 38, 70, 76] + COMMON_RULES)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 11, 52, 80, 81, 82] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([38, 52, 59, 77] + COMMON_RULES)

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
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V310.0 - 무결점 마스터)")
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
        label_docs = st.file_uploader("2️⃣ 원료 한글라벨/스펙 (원재료 대조용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("3️⃣ 배합비/레시피 데이터", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            local_paths = []
            DEFAULT_DOCS_DIR = "./default_docs"

            def robust_upload(file_path, label):
                user_content.append(f"### [{label}] ###")
                
                # ⭐ [Vision API 100% 강제 가동 (V310.0 패치)]
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
        if st.button("🚀 전체 시스템 파일 연동 (Vision API 자동 가동)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다..."):
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
🔥 [절대 금지사항]: "등", "등 다수", "중략" 이라는 표현을 절대 쓰지 마십시오.

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

            # ── PASS 1.5: 자체 검증 (V310.0 사전 판정 영구 차단 패치) ──
            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 종합 자체검증 명령]
⭐ 당신은 '매의 눈 검수관'입니다. 아래 수집된 분할 미션 결과들을 검열하십시오.

[분할 미션 통합 텍스트]
{extracted_text_combined}

검증 규칙:
1. ⭐ [월권행위 금지]: 이 단계에서 절대 룰북을 대입해 부적합(🚨)을 판정하지 마십시오. 오직 텍스트 복원만 수행하십시오.
2. ⭐ [오타/환각 원천 차단]: 글자를 유추하거나 변경하지 마십시오.
3. ⭐ [XML 괄호 보존]: 표나 태그 형태를 유지하십시오.
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
⭐ [최종 자기검증 명령]
1. 위 텍스트에 존재하는 내용만을 근거로 삼으십시오. 과거 기억이나 다른 제품의 데이터를 끌어오는 환각을 엄벌합니다.
"""
        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
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

    # ==========================================
    # 결과 출력 헬퍼
    # ==========================================
    def display_result(result, tab_name=""):
        if not result: return
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)

        if pass1_match:
            pass1_log = pass1_match.group(1).strip()
            result = result.replace(pass1_match.group(0), "").strip()
            with st.expander(f"📋 Pass 1 분할 미션 원본 로그 보기 ({tab_name})"): st.markdown(f"*{pass1_log}*")

        if pass15_match:
            pass15_log = pass15_match.group(1).strip()
            result = result.replace(pass15_match.group(0), "").strip()
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 보기 ({tab_name})"): st.markdown(f"*{pass15_log}*")

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
                missions = ["주표시면(앞면) 이미지에서 '제품명, 내용량, 칼로리, 마케팅 강조문구'만 리스트로 정확히 추출하십시오."]
                judgment_prompt = """
## 1️⃣ [주표시면 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망)
- ⭐ [Rule 3] 세트포장(박스) 앞면 총내용량 및 총열량 누락 검증: 
- ⭐ [Rule 52] 영양강조 컷오프(4대 조건) 검증: (반드시 수학적 수식 증명 포함)
## 🔍 [주표시면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "오직 타겟(박스)과 비교용(팩) 시안의 원재료명 리스트만 추출. 중략 절대 금지.",
                    "정보표시면의 '알레르기 물질', '교차오염 주의문구', '행정 정보' 추출.",
                    "증빙 서류의 원료명, 하위 성분, 원산지를 표로 추출."
                ]
                
                common_tab2_prompts = """
🔥 [시스템 절대 족쇄: 영양정보 연산 개입 절대 금지] 
이 탭(정보표시면)에서는 나트륨, 당류 등 영양수치를 검토하는 월권행위를 절대 금지합니다.

## 1️⃣ [원료 스펙 마스터 취합표]
| 매칭된 서류명 | 원료 제품명 | 식품유형 | 한글표시사항 | 원산지 | 알레르기 물질 |
|---|---|---|---|---|---|

## 2️⃣ [마스터 서류 vs 시안 법적 대조 매트릭스]
⭐ [원산지 순위 도출 규칙]: Rule 28에 따라 물/첨가물/미생물 소거 후 1,2,3순위를 도출하십시오. 4순위 이하는 지적 금지!
| 매칭된 서류 | 🧃 비교용(팩) | 📦 타겟(박스) | 검증 결과 (원산지 순위, 일치 여부) | 최종 판정 |
|---|---|---|---|---|

## 3️⃣ [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38 적용)]
⭐ [강제 지시]: 반드시 아래의 '수학적 차집합 수식' 풀이 과정을 텍스트로 써서 증명하십시오.
- [공장 마스터 목록]: 
- [직접 투입된 알레르기]: 
- [도출된 교차오염 정답지]: 
- [시안 표기 문구]: 
- [최종 판정 및 사유]: 

## 4️⃣ [행정 정보 검증 (Rule 76 판매원 타이틀 확인)]
## 🔍 [정보표시면 전용 오탈자 검증]
"""
                judgment_prompt = common_tab2_prompts
                if doc_type == "통합 엑셀/PDF 자료 (마스터표 생략)":
                    judgment_prompt = common_tab2_prompts.replace("## 1️⃣ [원료 스펙 마스터 취합표]", "")

                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "타겟(박스) 및 비교용(팩) 시안의 영양정보표 텍스트 전부 추출.",
                    "시험성적서 서류에서 각 영양성분의 100mL(g) 당 실측값 데이터 추출."
                ]
                judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
⭐ [계산 규칙]: 성적서 실측값을 반드시 시안의 총 내용량에 맞게 환산한 뒤 비교하십시오. 부적합 판정 시 부등호 수식 기재 필수!
| 영양성분 | 성적서 환산값(A) | 비교용(팩) 시안(B) | 타겟(박스) 시안(C) | 팩/박스 일치 여부 | 법적 기준선 (B의 80% 또는 120%) | 판정 및 사유 (수식 증명 필수) |
|---|---|---|---|---|---|---|

## 🔍 [영양성분표 치명적 레이아웃 및 뼈대 스나이퍼 (V310.0 신설)]
- ⭐ [Rule 80] 박스 포장 상단 레이아웃 확인 (`총 내용량... (X개입)` 및 `1개당` 기재 여부): 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = ["기타면/측면 이미지를 스캔하여 모든 마케팅 문구, 주의문구, 행정 정보 추출."]
                judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지]
- ⭐ [Rule 59] CS번호 및 1399 등 의무표시 3종 Global Scan: (현재 측면에 없더라도, 전체 캐시 텍스트를 다 뒤져서 패키지 어디든 있으면 합법 처리하십시오!)
- ⭐ [Rule 38] 알레르기 교차오염 수학적 차집합 검증: (수식 풀이과정 기재 필수)
- ⭐ [Rule 52] 마케팅 뱃지 영양강조 컷오프(4대 조건) 교차 검증: ('고/무/풍부' 단어 발견 시 반드시 4가지 수학 증명 필수!)
- ⭐ [Rule 77] 범용 식품유형 필수 주의문구 점검:
## 🔍 [기타면/측면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
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
                        return result.strip()

                    combined_results = f"""
[1번 탭 결과]: {strip_logs(st.session_state.get('result_tab1'))}
[2번 탭 결과]: {strip_logs(st.session_state.get('result_tab2'))}
[3번 탭 결과]: {strip_logs(st.session_state.get('result_tab3'))}
[4번 탭 결과]: {strip_logs(st.session_state.get('result_tab4'))}
"""
                    summary_prompt = f"""
[지시]: 사용자가 검토한 내용들을 바탕으로 패키지 수정 종합 결론을 내려주십시오.
[기존 분석 데이터]\n{combined_results}

## 📋 [최종 종합 검토 리포트]
- **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)

### 📌 [핵심 지적 사항 및 수정 지시]
(위 분석 데이터에서 '부적합(🚨)' 또는 '확인요망'이 나온 내용들만 뽑아서 번호 순 불릿 포인트로 요약 및 법적 사유 명시.)
"""
                    model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                    res = model.generate_content(st.session_state["uploaded_content"] + [summary_prompt])
                    st.session_state["result_summary"] = res.text

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])

if __name__ == "__main__":
    if check_password():
        main()
