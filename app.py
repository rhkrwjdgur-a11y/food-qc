import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os
import re
import tempfile

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
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항(예: 펙틴 부형제 생략, 당류 기원 생략, 향료 통합, 공전 명칭 치환, 내부 코드 생략 등)은 이 1:1 기계적 대조 원칙보다 무조건 최우선으로 적용하여 합법 처리하십시오.**
🔥 [오탈자 무관용 및 범용적 예외 원칙]: 의미가 통하더라도 자음/모음이 하나라도 다른 단순 오타는 무조건 부적합 처리하십시오. 단, 화학식 기호(α vs ALPHA), 아래첨자(₁ vs 1), 대소문자(DL vs dl), 단순 띄어쓰기 차이는 동의어 표기이므로 일치(✅) 처리하십시오.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 "왜 잘못되었는지, 어떻게 수정해야 하는지" 명확히 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 🌟(알림) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 65대 룰북 원문 (V160.0 범용 완결판)
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다. (기계 임의의 기준 적용 절대 금지)
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음, %표기 불가), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

**[⭐ 비율(%) 표기 절대 규칙]:** 소수점 첫째 자리에서 반올림하여 정수(1% 단위)로 표시합니다.
**[⭐ 1% 미만 예외 규칙]:** 비율이 1% 미만인 경우 반드시 "1% 미만"이라고 표기하십시오. (함량이 0g인 경우에만 0%로 표기)

## ⚠️ 검토 대원칙: 67대 품질관리 지침

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 합법입니다. 단, '향료2종'과 같이 숫자를 붙이는 것은 명칭 위반(⚠️)입니다.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 일치 및 당알콜 분리 연산]**
   - 주표시면에 강조된 열량/영양소 함량은 영양정보표 수치와 100% 일치해야 합니다. (총내용량/총열량 박스 표기 필수)
   - 영양정보표에 당알콜이나 식이섬유가 표기된 경우, 탄수화물 칼로리 계산 시 반드시 분리 적용(자일리톨 2.4kcal, 에리스리톨 0kcal 등) 하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서 실측값을 반영할 수 있습니다.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 하위 성분을 전개할 의무가 없습니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g이면, 실제 함량 0.5g 미만인지 검증하십시오.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 및 과다검출 이상치 방어 룰]**
   - 무조건 '시안 표시량'을 기준으로 법적 기준선을 도출하십시오. (역산 금지)
   - **[하한선 80% 이상 합법]**: 단백질, 비타민, 미네랄 등은 (실측값) >= (표시량 * 0.8) 이면 완벽한 합법(✅)입니다. (제조사의 의도된 보수적/안전빵 표기 인정)
   - **[상한선 120% 미만 합법]**: 열량, 나트륨, 당류, 지방 등은 (실측값) <= (표시량 * 1.2) 이면 완벽한 합법(✅)입니다.

🔥 **Rule 13. [알레르기 정밀 추적 및 파생 원료 예외 허용]**
   - "~함유" 박스에 적힌 알레르기 물질은 '원재료명' 내에 실존해야 합니다. (별도 란 기재 합법)

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 스나이퍼]**
   - **[표 4]**: 감미료 등은 반드시 "명칭+용도명" 병기.
   - **[표 5]**: 용도명 대체 금지. 지정 명칭/간략명 표기.
   - **[표 6]**: 유화제, 산도조절제 등은 용도명만 표기해도 100% 합법(✅).

🔥 **Rule 24. [무당/무가당/설탕무첨가 2대 의무 표기]**
   - 포도당 등 당류 포함 시 설탕 무첨가 표시는 부적합(🚨). 감미료 문구 및 열량 물리적 위치 강제.

🔥 **Rule 28. [원산지 3순위 완벽 필터링]**
   - 정제수, 첨가물 등을 제외한 진짜 원료 상위 1~3위 원산지 누락 시 부적합(🚨).

🔥 **Rule 35. [🌟 범용 간략명/동의어 허용 및 고도 정제/부형제 생략 보장 (강력 예외 룰)]**
   - **[🌟 고도 정제 원료 기원 생략]**: 포도당, 물엿, 과당 등 단일 당류는 서류에 옥수수전분 등 기원이 적혀있어도, 시안에서 이를 생략하고 '포도당'이라 적는 것이 100% 합법입니다.
   - **[🌟 첨가물 부형제 생략]**: 펙틴 등 혼합제제 서류에 포함된 부형제/희석제(자당, 덱스트린, 포도당 등)가 시안에서 생략되고 '펙틴'처럼 주원료만 적힌 것은 완벽한 합법입니다. 절대 누락으로 오판하지 마십시오.
   - **[🌟 수치 그대로 표시 허용]**: 영양표시 시 5.6g 등 소수점이 포함된 실측값을 그대로 적는 것은 합법(✅)입니다. 반올림을 강요하지 마십시오.
   - **[🌟 간략화 치환]**: 구연산나트륨을 구연산삼나트륨으로 적거나, 비타민 B1 염산염을 비타민B1으로 적는 통용명 치환은 모두 합법입니다.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 룰 (수학적 차집합 연산)]**
   - [교차오염 정답지] = [공장 마스터] - [직접 투입 알레르기 물질]. 중복/누락 시 부적합(🚨).

🔥 **Rule 44. [혼합제제 분산 전개(해체) 합법성 보장 룰]**
   - 혼합제제 하위 성분들을 괄호 없이 개별 원료처럼 분산하여 적는 것은 완벽한 합법(✅)입니다.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 및 뼈대 정보 교차 검증]**
   - **[🌟 영문 제품명 예외 허용]**: 앞면의 영문 브랜드명(예: MH Milk House)과 뒷면의 법적 한글 제품명이 불일치해도 디자인 요소로 완벽히 합법(✅)입니다.

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰 (통합 스캐너 전용)]**
   - 1) 소비자상담 2) 반품교환처 3) 1399 신고문구. 4장 시안 중 한 곳에라도 있으면 합법(✅).

🔥 **Rule 66. [영양성분 법정 단위 하드코딩 매칭 룰 (단위 스나이퍼)]**
   - 기계적 넘겨짚기 절대 금지! 영양성분 단위는 반드시 아래 **[정답지]**와 100% 일치해야 합니다. (g vs mg 오타 적발 시 🚨부적합)
   - [kcal]: 열량 / [g]: 탄수화물, 당류, 식이섬유, 단백질, 지방, 포화지방, 트랜스지방
   - [mg]: 나트륨, 콜레스테롤, 비타민B군(B1,B2,B6,C,판토텐산), 칼슘, 인, 칼륨, 철, 마그네슘, 아연, 구리, 망간
   - [µg]: 비타민D, B12, K, 비오틴, 요오드, 셀레늄, 몰리브덴, 크롬
   - [특수 복합]: 비타민A(µg RE / RAE), 비타민E(mg α-TE), 나이아신(mg NE), 엽산(µg DFE)

🔥 **Rule 67. [영양정보표 하단 법정 안내문구 토시 검증 룰 (문구 스나이퍼)]**
   - 반드시 **"1일 영양성분 기준치에 대한 비율(%)은 2,000kcal 기준이므로 개인의 필요 열량에 따라 다를 수 있습니다."** (동의어 인정) 가 있어야 합니다.
   - 🚨 "1일 영양소 기준"처럼 법적 용어('영양성분')를 잘못 축약한 오타는 무조건 부적합 처리.
"""

# ==========================================
# 📚 4. 탭별 핵심 룰 슬라이싱
# ==========================================
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

COMMON_RULES = [36, 37, 42, 43, 45, 47, 63]
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 10, 21, 24, 28, 40, 46, 47, 50, 52, 64] + COMMON_RULES)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 6, 8, 12, 13, 14, 25, 28, 30, 34, 35, 38, 39, 44, 48, 52, 61, 65] + COMMON_RULES)
# 💡 [V160.0 패치] Tab 3에 단위 스나이퍼(66) 및 문구 스나이퍼(67) 룰 강제 배정
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 6, 10, 11, 21, 23, 25, 26, 27, 31, 32, 33, 35, 40, 41, 66, 67] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면(통합 스캐너) 관련 핵심 룰]\n" + get_sliced_rules([7, 24, 38, 56, 57, 59, 64] + COMMON_RULES)

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")

    for key in ["result_tab1", "result_tab2", "result_tab3", "result_tab4", "result_summary", "uploaded_content"]:
        if key not in st.session_state:
            st.session_state[key] = None

    print_css = """
    <style>
    @media print {
        [data-testid="stSidebar"], header, footer, [data-testid="stHeader"], [data-testid="stToolbar"],
        .stFileUploader, .stButton, .stRadio, .stTextInput, button { display: none !important; }
        [role="tablist"], [data-baseweb="tab-list"] { display: none !important; }
        html, body, .stApp, main, .block-container, [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"] {
            height: auto !important; min-height: 100% !important; max-height: none !important; overflow: visible !important; position: static !important; width: 100% !important; max-width: 100% !important; padding: 0 !important; margin: 0 !important; display: block !important;
        }
        table { page-break-inside: auto !important; width: 100% !important; border-collapse: collapse !important; }
        tr { page-break-inside: avoid !important; page-break-after: auto !important; }
        th, td { page-break-inside: avoid !important; border: 1px solid black !important; padding: 8px !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V160.0 - 단위 스나이퍼 & 정밀환산 탑재)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        st.markdown("#### 🏭 공장 알레르기 마스터 설정")
        factory_allergens = st.text_area(
            "우리 공장 취급 알레르기 물질 (쉼표로 구분)",
            "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류",
            help="교차오염 멘트의 누락/중복을 검증합니다."
        )
        st.markdown("---")
        product_type = st.radio("📌 1. 식품유형", (
            "일반식품 (두유류 등)", 
            "특수의료용도식품 / 환자식", 
            "냉장 축산물 (우유/가공유 등)"
        ))
        inspection_mode = st.radio("📌 2. 검토 모드", ("단품(팩/단일포장) 기본 검토", "선물세트 박스(외포장) 교차 검토"))
        doc_type = st.radio("📌 3. 증빙 서류 형태", ("통합 엑셀/PDF 자료", "개별 원료 한글라벨 무더기 (마스터표 생성)"))

        st.markdown("---")
        if inspection_mode == "선물세트 박스(외포장) 교차 검토":
            st.markdown("#### 📦 [타겟] 박스(외포장) 시안 업로드")
            img_main = st.file_uploader("1️⃣ 박스 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 박스 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 박스 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 박스 기타면/측면", type=["jpg", "png", "jpeg"])
            st.markdown("---")
            st.markdown("#### 🔍 [비교용] 팩(내포장) 시안 업로드")
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
            box_main, box_info, box_nutri, box_extra = None, None, None, None

        st.markdown("---")
        st.markdown("#### 📑 추가 증빙 서류 업로드")
        report_docs = st.file_uploader("📑 추가 시험성적서 및 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("📑 추가 배합비/원료 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            DEFAULT_DOCS_DIR = "./default_docs"
            if os.path.exists(DEFAULT_DOCS_DIR):
                for file_path in glob.glob(os.path.join(DEFAULT_DOCS_DIR, "*.pdf")):
                    user_content.append(f"### [자동로드_서류: {os.path.basename(file_path)}] ###")
                    up = genai.upload_file(file_path)
                    while up.state.name == "PROCESSING": time.sleep(1)
                    user_content.append(up)

            def process(f, label):
                user_content.append(f"### [{label}] ###")
                if f.type.startswith("image"):
                    user_content.append(Image.open(f))
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(f.getbuffer())
                        safe_temp_path = tmp.name
                    up = genai.upload_file(safe_temp_path)
                    while up.state.name == "PROCESSING": time.sleep(1)
                    user_content.append(up)
                    os.remove(safe_temp_path)

            for f, l in [(img_main, "타겟_시안_주표시면"), (img_info, "타겟_시안_정보표시면"), 
                         (img_nutri, "타겟_시안_영양성분표"), (img_extra, "타겟_시안_기타면_측면"),
                         (box_main, "정답지_팩_주표시면"), (box_info, "정답지_팩_정보표시면"), 
                         (box_nutri, "정답지_팩_영양성분표"), (box_extra, "정답지_팩_기타면_측면")]:
                if f: process(f, l)
            
            for docs in [report_docs, recipe_docs]:
                if docs:
                    for f in docs: process(f, "추가_근거_서류")
            return user_content

        st.markdown("---")
        if st.button("🚀 전체 시스템 파일 연동 (기본 폴더 자동 로드 포함)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다..."):
                st.session_state["uploaded_content"] = get_uploaded_content()
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_mission: str):
        if not st.session_state["uploaded_content"]:
            st.warning("🚨 좌측 사이드바 하단의 [🚀 전체 시스템 파일 연동] 버튼을 먼저 눌러주세요.")
            return None

        content = st.session_state["uploaded_content"]
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in [
            "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", 
            "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]

        pass1_prompt = f"[PASS 1 - 텍스트 추출 전용]\n{extract_mission}\n출력형식:\n=== [미션 A] ===\n\n=== [미션 B] ==="
        try:
            pass1_response = model.generate_content(content + [pass1_prompt], generation_config=config, safety_settings=safety)
            extracted_text = pass1_response.text
        except Exception as e: return f"🚨 Pass 1 오류: {e}"

        pass15_prompt = f"[PASS 1.5 - 환각/오타 자체검증]\n원본 이미지의 명백한 오타를 정상 단어로 교정하지 말고 원본 그대로 훼손시켜 복구하십시오!\n{extracted_text}"
        try:
            pass15_response = model.generate_content(content + [pass15_prompt], generation_config=config, safety_settings=safety)
            verified_text = pass15_response.text
        except Exception as e: verified_text = extracted_text

        docs_only = [item for i, item in enumerate(content) if not isinstance(item, Image.Image)]

        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용]
아래 [검증된 텍스트 데이터]만을 팩트로 사용하여 대조 판정하십시오.
[제품유형]: {product_type} / [검토모드]: {inspection_mode} / [공장 알레르기]: {factory_allergens}
[적용 룰]: {tab_rules}
========================================
{verified_text}
========================================
{judgment_prompt}
"""
        try:
            pass2_response = model.generate_content(docs_only + [pass2_prompt], generation_config=config, safety_settings=safety)
            return fix_markdown_table(f"<pass1_log>{extracted_text}</pass1_log>\n<pass15_log>{verified_text}</pass15_log>\n{pass2_response.text}")
        except Exception as e: return f"🚨 Pass 2 오류: {e}"

    def run_qc_model(prompt_text):
        if not st.session_state["uploaded_content"]: return None
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in [
            "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", 
            "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        full_prompt = f"[제품유형]:{product_type}\n{RULE_BOOK_FULL}\n====================\n{prompt_text}"
        try: return fix_markdown_table(model.generate_content(st.session_state["uploaded_content"] + [full_prompt], generation_config=config, safety_settings=safety).text)
        except Exception as e: return f"🚨 런타임 오류: {e}"

    def display_result(result, tab_name=""):
        if not result: return
        p1 = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        p15 = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)
        if p1:
            with st.expander(f"📋 Pass 1 추출 로그"): st.markdown(f"*{p1.group(1).strip()}*")
            result = result.replace(p1.group(0), "")
        if p15:
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 (실제 판정 사용)"): st.markdown(f"*{p15.group(1).strip()}*")
            result = result.replace(p15.group(0), "")
        st.markdown(result.strip())

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "📊 5️⃣ 종합 보고서"])

    # ── TAB 1: 주표시면 ──
    with tab1:
        if st.button("▶️ 주표시면 분석 시작 (교차 스파이봇 가동)", key="btn_main"):
            with st.spinner("【3-Pass】 앞면 분석 및 뒷면 교차 스캔 중..."):
                extract_mission = """🎯 [미션 A] '주표시면(앞면)' 제품명, 용량, 칼로리, 강조문구 추출.\n🕵️‍♂️ [뒷면 핀셋 스캔] 영양성분표의 '총 내용량', '총 열량', 앞면 강조 영양소의 '% 기준치' 추출."""
                judgment_prompt = """## 1️⃣ [주표시면 마케팅 뱃지 및 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망)
- ⭐ [Rule 3] 총내용량 및 총열량 강제 스캔:
- ⭐ [Rule 47] 앞면 용량/열량 교차 검증:
- ⭐ [Rule 50] 원액 고형분 병기:
- ⭐ [Rule 24] 무당/무가당 2대 의무 표기:
- ⭐ [Rule 52] 영양강조 컷오프(7.5/15%) 대조:"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【3-Pass】 원재료명 파싱 및 대조 진행 중..."):
                extract_mission = """🎯 [미션 A] '원재료명' 쉼표 기준 분리하여 세로 리스트 추출.\n🎯 [미션 B] '증빙 서류' 분석하여 혼합제제 하위 성분 100% 전개 표 생성."""
                judgment_prompt = """
🔥 [Rule 35 극강제 룰]: 펙틴 서류에 자당이 있어도 펙틴만 적은 것은 합법(부형제 생략)! 옥수수전분으로 만든 포도당은 포도당만 적어도 합법! 절대 누락으로 지적하지 마십시오.

## 1️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
| 시안 표기 원재료명 (나열 순서대로) | 매칭된 서류 원료명 | 원산지 순위 | 오탈자 검증 | 판정 (상세 사유 필수) |
|---|---|---|---|---|
| (미션 A 기준 복붙) | [내용] | [내용] | [내용] | [내용] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 시안에서 누락된 원료: """
                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 및 단위 스캔", key="btn_nutri"):
            with st.spinner("【3-Pass】 비중/오차 정밀 연산 및 단위 스나이퍼 가동 중..."):
                extract_mission = """🎯 [미션 A] '영양정보' 표 데이터(성분, 단위, 함량, %) 및 표 바깥 하단의 "1일 영양성분 기준치에 대한..." 문구 전체 추출.\n🎯 [미션 B] '시험성적서' 실측값 데이터(100mL 등) 추출."""
                judgment_prompt = """
⭐ [오차 검증 절대 규칙 (Rule 11 강제 적용)]:
비타민, 무기질 등은 (실측값 >= 표시량의 80%) 이면 무조건 합법(✅). 열량, 당류 등은 (실측값 <= 표시량의 120%) 이면 합법. 
안전빵(보수적 표기)으로 설계된 라벨 숫자를 환산값과 다르다고 지적하지 마십시오!

⭐ [액체 비중(Specific Gravity) 고려 원칙]: 
실험실 배합비(%)를 부피(mL)에 곱한 단순 환산값(예: 1.04g)과 라벨 표기값(예: 1.06g)이 달라도 절대 부적합 처리 금지! 비중 밀도 연산이므로 ✅합법 처리하십시오.

⭐ [단위 환산 및 연산 강제 지시]: 
성적서가 100mL 기준일 경우 반드시 배수를 곱하여 '환산 실측값'을 표에 명시하십시오.

## 4️⃣ [영양표시 오차 검증 및 % 기준치 연산]
| 영양성분 | 성적서 원본 (100mL/g당) | 🎯 환산 실측값 (총 내용량 기준) | 시안 표시량 | 허용오차 검증(환산값vs표시량) | 🎯 % 연산 검증 (표시량÷1일기준치×100) | 판정 (사유) |
|---|---|---|---|---|---|---|
| (내용) | (내용) | (내용) | (내용) | (내용) | (내용) | (내용) |

## 🔍 [영양성분표 치명적 오탈자 및 단위 스나이퍼 스캔]
- ⭐ [Rule 66] 단위 오기재 스나이퍼: (반드시 Rule 66 정답지와 대조하여 g, mg, µg 등 단위 오타 스캔)
- ⭐ [Rule 67] 하단 법정 문구 토시 검증 스나이퍼: (영양정보 하단의 "1일 영양소 기준" 등 불법 축약/오타 여부 스캔)"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 공통 의무표시 전 구역 통합 분석 시작", key="btn_extra"):
            with st.spinner("【3-Pass】 4장의 시안 전체에서 필수 의무표시 통합 스캔 중..."):
                extract_mission = """🎯 [미션 A] 4장 전체 통합 스캔. 1) 소비자상담 2) 반품교환 3) 1399 문구 4) HACCP 5) 알레르기 교차오염 박스 추출."""
                judgment_prompt = """## 5️⃣ [전 구역 통합 공통 표시사항 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망)
- ⭐ [Rule 59] 필수 의무표시 3종 (소비자, 반품, 1399) 전 구역 통합 누락 검증: (단 한 곳이라도 있으면 합법)
- ⭐ [Rule 38] 알레르기 교차오염 문구 적합성 (차집합 계산):
- ⭐ [Rule 56] HACCP 마크 텍스트 명칭 검증:"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    # ── TAB 5: 종합 보고서 ──
    with tab5:
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"], st.session_state["result_tab3"], st.session_state["result_tab4"]]):
                st.warning("🚨 1~4번 탭 중 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("최종 수정 지시서를 작성 중입니다..."):
                    def strip_logs(r):
                        if not r: return "분석 안 함"
                        return re.sub(r'<.*?>.*?</.*?>', '', r, flags=re.DOTALL).strip()
                    combined_results = f"[1번 탭]: {strip_logs(st.session_state.get('result_tab1'))}\n[2번 탭]: {strip_logs(st.session_state.get('result_tab2'))}\n[3번 탭]: {strip_logs(st.session_state.get('result_tab3'))}\n[4번 탭]: {strip_logs(st.session_state.get('result_tab4'))}"
                    summary_prompt = f"[지시]: 탭별 검토 내용 종합 결론 작성.\n\n[데이터]\n{combined_results}\n\n## 📋 [최종 종합 검토 리포트]\n- **최종 판정:**\n### 📌 [핵심 지적 사항 및 수정 지시]\n(부적합/확인요망 사항만 요약)\n### 🔍 [기타 주의사항]"
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])
            st.markdown("<hr class='hide-on-print'><div class='hide-on-print' style='text-align: right;'><button onclick='window.print();' style='background-color:#FF4B4B; color:white; padding:12px 24px; border-radius:6px; font-weight:bold;'>🖨️ 종합 보고서 인쇄</button></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    if check_password():
        main()
