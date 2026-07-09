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

if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)

# ⭐ 최고급 Pro 모델 유지
MODEL_NAME = "gemini-2.5-pro"

def get_safe_text(response):
    try:
        if response.candidates and response.candidates[0].content.parts:
            text = response.text
            fr = response.candidates[0].finish_reason if response.candidates else "Unknown"
            if fr == 2:
                text += "\n\n🚨 [시스템 알림]: AI가 한 번에 출력할 수 있는 물리적 텍스트 한도(MAX_TOKENS)에 도달하여 대조가 중간에 종료되었습니다."
            return text
        else:
            fr = response.candidates[0].finish_reason if response.candidates else "Unknown"
            if fr == 2:
                return "🚨 [출력 한도 초과] AI가 너무 많은 텍스트를 생성하여 출력이 도중에 차단되었습니다. (Finish Reason: 2 - MAX_TOKENS)"
            elif fr == 3:
                return "🚨 [안전 필터 차단] 구글 보안 필터가 민감한 단어로 인식하여 생성을 차단했습니다. (Finish Reason: 3 - SAFETY)"
            else:
                return f"🚨 [응답 반환 실패] 텍스트가 반환되지 않았습니다. (Finish Reason: {fr})"
    except Exception as e:
        return f"🚨 [시스템 추출 오류] 모델 응답을 읽어오는 중 에러 발생: {e}"

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
# 🧬 [첨가물 표 4, 5, 6 하드코딩 DB]
# ==========================================
ADDITIVE_TABLE_4 = [
    "데히드로초산나트륨", "소브산", "소브산칼륨", "소브산칼슘", "안식향산", "안식향산나트륨", "안식향산칼슘", "안식향산칼륨", "파라옥시안식향산메틸", "파라옥시안식향산에틸", "프로피온산", "프로피온산나트륨", "프로피온산칼슘", "나타마이신",
    "사카린나트륨", "수크랄로스", "아세설팜칼륨", "아스파탐", "네오탐", "알리탐", "스테비올배당체", "효소처리스테비아", "토마틴", "감초추출물", "나한과추출물", "스테비아추출물", "에리트리톨",
    "식용색소녹색제3호", "식용색소녹색제3호알루미늄레이크", "식용색소적색제2호", "식용색소적색제2호알루미늄레이크", "식용색소적색제3호", "식용색소적색제40호", "식용색소적색제40호알루미늄레이크", "식용색소청색제1호", "식용색소청색제1호알루미늄레이크", "식용색소청색제2호", "식용색소청색제2호알루미늄레이크", "식용색소황색제4호", "식용색소황색제4호알루미늄레이크", "식용색소황색제5호", "식용색소황색제5호알루미늄레이크", "이산화티타늄",
    "아질산나트륨", "질산나트륨", "질산칼륨",
    "아황산나트륨", "차아황산나트륨", "무수아황산", "메타중아황산나트륨", "메타중아황산칼륨", "이산화황",
    "부틸히드록시아니솔", "디부틸히드록시톨루엔", "몰식자산프로필", "에리토브산", "에리토브산나트륨", "터셔리부틸히드로퀴논", "이디티에이칼슘이나트륨", "이디티에이나트륨",
    "L-글루탐산나트륨", "카페인"
]

ADDITIVE_TABLE_5 = [
    "카라멜색소", "카라멜색소I", "카라멜색소II", "카라멜색소III", "카라멜색소IV", "치자청색소", "치자황색소", 
    "홍화황색소", "적양배추색소", "파프리카추출색소", "안나토추출물", "오징어먹물색소", "적고구마색소",
    "차아염소산나트륨", "구아검", "잔탄검", "펙틴", "카라기난", "로커스트콩검", "알긴산나트륨", "결명자추출물"
]

ADDITIVE_TABLE_6 = [
    "유화제", "산도조절제", "증점제", "팽창제", "고결방지제", "응고제", "향미증진제", "안정제", "결착제", "제리화제", "밀가루개량제", "영양강화제", "거품제거제",
    "구연산", "구연산나트륨", "빙초산", "탄산나트륨", "탄산수소나트륨", "제이인산칼륨", 
    "제삼인산칼슘", "수산화나트륨", "젖산", "젖산나트륨", "말토덱스트린", "글리세린", "자당지방산에스테르",
    "5'-이노신산이나트륨", "5'-구아닐산이나트륨", "5'-리보뉴클레오티드이나트륨", "5'-리보뉴클레오티드칼슘", "5'-리보뉴클레오티드이칼슘", 
    "L-글루타민", "L-글루탐산", "L-글루탐산암모늄", "L-글루탐산칼륨", "글리세로인산칼륨", "글리세로인산칼슘"
]

# ==========================================
# 📚 2. 시스템 지시어
# ==========================================
SYSTEM_PROMPT = f"""당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
당신에게는 창의성, 추론 능력, 융통성이 전혀 없습니다. 오직 화면에 보이는 픽셀 단위의 글자(Text)만 있는 그대로 읽고 기계적으로 1:1 대조하는 봇(Bot)입니다.

🔥 [데이터 원본 보존 및 절대 생략 금지 원칙]:
어떠한 경우에도 텍스트를 임의로 요약하거나 `(...)`, `...` 기호를 사용하여 생략하지 마십시오. 글자 수가 아무리 많더라도 괄호 속 성분까지 100% 끝까지 타이핑해야 합니다. 사유를 작성할 때도 룰(Rule)을 근거로 상세하게 서술하십시오.

🔥 [0순위 절대 방어막: 5% 미만 복합원재료 과잉 지적 금지 (Rule 5 적용)]:
어떤 첨가물이나 원료의 표기 누락(또는 용도 누락)을 지적하기 전에, **반드시 그 원료가 배합비 5% 미만인 복합원재료의 하위 성분인지 가장 먼저 확인하십시오.** 5% 미만 복합원재료의 하위 성분이라면 [표 4, 5, 6] 첨가물 규정 등 모든 규정을 무시하고 **무조건 "전개/표시 의무 면제(✅)"로 판정**하십시오. (단, 알레르기 물질은 예외)

🔥 [식품첨가물 표기 특별 통제 원칙]: 
원재료명 란의 첨가물을 판정할 때, 반드시 아래 하드코딩된 DB를 먼저 대조하여 판정하십시오.
* [표 4 소속 (명칭+용도 병기 강제, 누락시 🚨부적합)]: {ADDITIVE_TABLE_4}
* [표 5 소속 (명칭 또는 간략명만 표시, 용도 생략해도 ✅합법)]: {ADDITIVE_TABLE_5}
* [표 6 소속 (명칭, 간략명, 주용도 중 선택 표시 ✅합법)]: {ADDITIVE_TABLE_6}

모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 90대 마스터 룰북 원문
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

## ⚠️ 검토 대원칙: 품질관리 지침

🔥 **Rule 1. [원산지 상위 3순위 표기 및 98% 컷오프 예외 룰]**
   - 배합비 상위 3순위 이내의 원료는 반드시 원산지를 표기해야 합니다 (누락 시 🚨부적합).
   - **[98% 컷오프 예외]**: 단, 배합비 1순위 원료 단독으로 98% 이상이면 1순위만 표기, 1순위와 2순위 배합비의 합이 98% 이상이면 2순위까지만 표기해도 합법(✅)입니다. (나머지 순위 생략 가능)
   - **[산정 제외]**: 정제수(물), 주정, 당류, 식품첨가물은 배합비율이 아무리 높아도 원산지 산정(1~3순위) 대상에서 100% 제외됩니다. 나한과추출분말 등을 임의로 첨가물로 오판하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 개별 향료명이 명시되어 있어도, 시안 원재료명에 단순히 '향료'로 묶어 표기 가능. (단, Rule 85 참고)

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 강제 룰]**
   - 주표시면(앞면)에 특정 영양소 함량이 강조되어 있다면, 뒷면 영양성분표 수치와 단 1의 오차도 없이 100% 일치해야 합니다.
   - 세트 포장의 주표시면에는 '총 내용량'과 '총 열량(kcal)'이 모두 기재되어야 합니다.

🔥 **Rule 5. [복합원재료 5% 미만 전개 면제 및 5가지 컷오프 룰 (최우선 방어막)]**
   - **[조건 A: 5% 미만 전개 면제]**: 배합비 5% 미만인 복합원재료는 괄호를 열고 하위 성분을 전개할 의무가 아예 없습니다. 생략 합법(✅).
   - 🌟 **[첨가물 과잉 단속 금지 원칙]**: 위 조건 A에 따라, 5% 미만 복합원재료 내부에 [표 4, 5, 6] 소속 식품첨가물이 들어있더라도 명칭/용도 표시 의무가 완전히 면제됩니다.
   - **[조건 B: 5가지 컷오프]**: 배합비가 5% 이상인 복합원재료의 경우, 하위 성분 중 '물을 제외하고 많이 사용한 순서대로 5가지'만 명시되어 있다면 나머지 일반 원료 생략은 합법(✅).
   - 🌟 **[조건 C: 5순위 밖 첨가물 생략 면제]**: 식약처 유권해석(2025.07)에 의거, 복합원재료 내 하위 순위(6순위 이하)에 해당하는 식품첨가물은 표기를 완전히 생략하는 것이 합법(✅)입니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 당류 0g 표기 시 0.5g 미만인지 검증.

🔥 **Rule 7. [당알코올 10% 컷오프 룰]**
   - 당알코올류 10% 미만 사용 시 주의문구 생략 합법(✅).

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - '외국산' 표기는 적합.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 혼동되지 않도록 명확히 구분.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 분리)**
   - 제형에 따라 100g/100mL 당 기준을 분리하여 심사.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙]**
   - **[하한선 그룹(비타민,단백질 등)]**: `(용량 환산 실측값) >= (시안 표시량 × 0.8)` 이면 합법.
   - **[상한선 그룹(열량,당류 등)]**: `(용량 환산 실측값) <= (시안 표시량 × 1.2)` 이면 합법.
   - ⭐ **수식 증명 강제**: 성적서가 주어지면 반드시 `(실측값/100g) × (1회제공량 환산비율) = 실측환산값`을 계산하여 증명해야 합니다.

✅ **Rule 12. [원재료명 교차 검증 및 임의 추론 금지]**
   - 서류 없이 레시피 상상 금지.

🔥 **Rule 13. [알레르기 표기 시각적 한계 보완 및 실무 확인 룰]**
   - 알레르기 물질은 원재료명과 바탕색이 구분되는 '별도 란(박스)'에 기재해야 합니다.
   - **[AI 시각적 한계 보완]**: AI는 이미지의 음영(바탕색) 차이를 정확히 판별하기 어려우므로, 텍스트 스캔 결과 시안에 **'OO 함유'**라는 독립된 문구가 존재한다면 일단 알레르기 표시란 규정을 준수한 것으로 간주하여 **✅(적합)** 처리하십시오.
   - ⭐ **[강제 출력 원칙]**: 위 경우 판정 사유 끝에 반드시 **"⚠️(실무 확인 권장): 시스템상 'OO 함유' 텍스트 표기는 확인되었으나, 해당 문구의 바탕색이 원재료명 란과 다르게 음영 처리되어 확실히 구분되는지 육안으로 한 번 더 확인해 주십시오."**라는 멘트를 덧붙이십시오.

🔥 **Rule 14. [첨가물 표 4, 5, 6 교차 검증 및 표 6 주용도 합법성]**
   - **[표 4]**: 명칭과 용도(예: 감미료) 둘 다 표시 필수.
   - **[표 5]**: 명칭 또는 간략명 표시 필수 (용도만 표시 불가).
   - ⭐ **[표 6 특권]**: 명칭, 간략명, 또는 **'주용도(예: 유화제, 산도조절제, 팽창제 등)' 중 하나만 단독으로 표시해도 완벽한 합법(✅)**입니다. AI는 시안에 화학적 명칭 없이 '유화제'라고만 적혀 있어도 절대 부적합 처리하지 마십시오.

✅ **Rule 15. [기능성 오인 문구 및 신체 조직 작용 전면 통제]**
   - '소화불편감 완화' 등 인체의 기능·작용·효과를 직접 암시하거나 기만하는 표현 전면 금지(🚨부적합).

✅ **Rule 16. [원산지 100% 표기 룰]**
   - 단일 국가 100% 수입 원료만 100% 강조 가능.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지 첨가물 배제 강조 시 부적합(🚨).

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 영유아 타겟 명칭 사용 적발.

✅ **Rule 19. ['무당' vs '무가당' 분리 검증]**
   - **무당(Zero Sugar):** 완제품 기준 100g(mL)당 0.5g 미만 시 합법.
   - **무가당(No Added Sugar):** 제조 공정 중 당류를 인위적으로 첨가하지 않은 경우에만 합법.

🔥 **Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무 없음.

🔥 **Rule 21. ['고/풍부', '저', '무' 영양강조표시 4대 조건 OR 법칙 및 수학적 증명 룰]**
   - **[대원칙]**: 식약처 고시에 따라 영양강조 기준은 4가지(100g당, 100mL당, 100kcal당, 1회섭취량당) 중 **단 하나라도 충족하면 무조건 합법(✅)**입니다.
   - **['고', '풍부' 표시 기준]**: 
     1) **단백질, 식이섬유**: 기준치의 20%(100g당) / 10%(100mL당) / 10%(100kcal당) / 20%(1회섭취량당) 이상.
     2) **비타민 및 무기질**: 기준치의 30%(100g당) / 15%(100mL당) / 10%(100kcal당) / 30%(1회섭취량당) 이상.
   - **['저' 표시 기준]**: 열량(100g당 40kcal 미만 또는 100mL당 20kcal 미만), 나트륨(100g당 120mg 미만) 등.
   - **['무(Zero)' 표시 기준]**: 열량(100mL당 4kcal 미만), 나트륨/지방/당류(5mg/0.5g/0.5g 미만).
   - ⭐ **[부적합 시 절대 원칙]**: 부적합 판정을 내리려면 4가지 조건의 수식을 모조리 나열하여 전부 미달임을 증명해야 합니다. 하나라도 통과 시 무조건 합법 처리하십시오.

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 함.

🔥 **Rule 23. [식약처 영양성분별 '0' 표시 절대 규정 (0.1, 0.2, 0.5 룰)]**
   - 다음 성분은 성적서의 실측 환산값이 아래 기준 미만일 경우 반드시 "0"으로 표시해야 하며, 시안에 "0"으로 적혀있다면 완벽한 합법(✅)입니다. (불검출 또한 0으로 환산합니다)
   - **[열량]**: 5kcal 미만 -> "0kcal"
   - **[나트륨]**: 5mg 미만 -> "0mg"
   - **[탄수화물, 당류, 단백질, 지방]**: 0.5g 미만 -> "0g"
   - **[트랜스지방]**: 0.2g 미만 -> "0g"
   - **[포화지방]**: 0.1g 미만 -> "0g"
   - **[콜레스테롤]**: 2mg 미만 -> "0mg"

🔥 **Rule 24. [무당/무가당 강조표시 연계 의무 표기 유연성 룰]**
   - 무당/무가당/무첨가 강조 시 열량 병기 의무를 검사할 때, 해당 강조 문구 바로 옆에 딱 붙어있지 않더라도, 주표시면의 동일한 시야각(예: 하단 내용량 표시 부근) 내에 총 열량(kcal)이 충분히 명확하게 기재되어 있다면 합법(✅)으로 유연하게 판정하십시오. 억지로 부적합 처리하지 마십시오.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 분리.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 g, 액체는 mL.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등은 100kcal 당 조건을 적용 금지.

🔥 **Rule 28. [자사 규정 맞춤형 원산지 예외 4대장 룰]**
   - 물(정제수), 주정, 식품첨가물, 당류가공품 원료만 원산지 산정에서 강제 삭제.

🔥 **Rule 29. [국내 가공 복합원재료 원산지 역추적 합법성]**
   - 하위 원물 원산지를 역추적해 표기했다면 합법(✅).

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 호밀, 귀리, 보리는 '밀' 알레르기가 아님. 대두 표기는 '콩기름'이 있으면 합법.

✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 성적서 누락 없이 병합 대조.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 반올림 오차에 의한 계산 차이는 합법.

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치 구분.

🔥 **Rule 34. [🌟 배합비 전개 순서 100% 일치 강제 및 2% 미만 예외 룰]**
   - **[절대 원칙]**: 원재료명은 반드시 서류상의 배합비율(%)이 높은 중량 순서대로 기재되어야 합니다. 배합비 순위가 시안의 나열 순서와 단 한 칸이라도 다르면 명백한 표시기준 위반(🚨부적합)입니다.
   - **[2% 미만 예외]**: 단, 배합비율이 **2% 미만**인 원료들은 중량 순서에 상관없이 자유롭게 기재해도 완벽한 합법(✅)입니다.
   - ⭐ **[순서 역전 정밀 검증]**: AI는 서류에서 2% 이상인 원료들(예: 1위 35%, 2위 28%, 3위 10.7%, 4위 10.0%...)을 무조건 찾아내어 그 순서가 시안에서 완벽히 동일한지 엄격하게 검증하십시오. (예: 10.7%인 저감미당이 10.0%인 A2단백원유보다 무조건 앞에 와야 합니다. 역전 시 🚨부적합 처리)

🔥 **Rule 35. [🌟 범용 간략명/관용명 허용 및 혼합제제 괄호 내부 N종 은폐 금지 범용 룰]**
   - **[관용명/동의어 합법 처리]**: 실무적으로 호환되는 동의어나 관용명 표기는 100% 합법(✅)입니다. (예: 옥배유=옥수수기름, 액상과당=기타과당=고과당, 황백당=갈색설탕 등)
   - **[내부 식별 코드 생략]**: 서류상의 납품업체 전용 식별코드(예: E(30), -2 등)는 생략 완벽 합법(✅).
   - ⭐ **[향료 N종 무조건 합법]**: **'향료 3종', '합성향료 2종'**처럼 향료에 숫자를 붙여 묶는 것은 식약처 규정상 **완벽한 합법**입니다. 절대 N종 묶음 금지 규정을 적용하여 부적합 처리하지 마십시오.
   - ⭐ **[혼합제제 괄호 내부 은폐 절대 불가]**: 패키지 시안에 `혼합제제(산도조절제 2종)`처럼 **'혼합제제의 괄호 안'**에 다른 첨가물을 숫자로 묶어 은폐한 경우에만 위법(🚨부적합)으로 처리하십시오. 증빙 서류 타이틀에 쓰인 단순 분류 명칭(예: 유화제 2종)을 보고 기계적으로 단속하지 마십시오.

🔥 **Rule 36. [주의사항 오탈자 스캔]**
   - 오탈자 정밀 검수. 각 구역별 텍스트 스캔 및 띄어쓰기 비교 필수.

✅ **Rule 37. [법적 서류 우선 고려]**
   - Rule 35 예외 우선 고려.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증]**
   - ⭐ **[강제 수식]**: `[교차오염 정답지] = [공장 취급 마스터] - [직접 투입 알레르기]` 도출 증명.

🔥 **Rule 39. [동명 원료 및 식품유형 종속성 분리 룰]**
   - 명칭이 같아도 [식품유형]이 다르면 분리 표기.

🔥 **Rule 40. [열량 표기 및 애트워터 계수 합법성 (유연성 패치)]**
   - 식약처 고시에 따라 열량은 "계산된 값을 그대로 표시하거나", "가장 가까운 5kcal 단위로 표시"하는 것 모두가 합법입니다.
   - 또한, 시안에 적힌 열량은 `(표시된 탄수화물×4) + (표시된 단백질×4) + (표시된 지방×9)`로 도출(애트워터 계수 적용)되는 경우가 실무적으로 매우 흔하며 이 역시 완벽한 합법입니다.
   - 따라서 실측값의 단순 반올림 수치와 다르다고 해서 기계적으로 부적합 처리하지 마십시오. 120% 상한선 오차 범위 이내면 무조건 합법(✅)입니다.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - 열량(kcal)과 트랜스지방은 %를 표기하지 않습니다.
   - 나머지 성분은 `(시안의 표시량 ÷ 1일 영양성분 기준치) × 100`을 정확히 역산하여 시안의 % 표기가 맞는지 대조하십시오.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 최종 완제품 기준 데이터만 사용.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독 어려우면 임의 판정 금지.

🔥 **Rule 44. [🌟 복합원재료(혼합제제) 중복 시 '명칭 유지 병합' 전면 금지 및 해체 강제 룰]**
   - 복합원재료(예: 혼합제제A)의 하위 성분으로 포함된 특정 혼합물(예: 혼합제제B)이 제품에 별도로 추가 투입되거나 다른 원료에도 중복 포함되어 있을 때, 이를 통합 표기하겠다며 **"혼합제제B"라는 복합 묶음 명칭(껍데기) 자체를 그대로 살려서 한 번만 기재하는 것은 명백한 위법(🚨부적합)입니다.**
   - ⭐ **[최하위 단일 성분 전개 필수]**: 여러 경로로 중복 투입된 혼합제제를 합치려면, 반드시 그 껍데기를 부수고 하위의 '최하위 단일 성분(개별 첨가물/원료)' 단위로 낱낱이 해체(전개)하여 흩뿌려 적어야만 합법(✅)입니다. 시안에 2곳 이상에서 유래한 복합원재료가 하위 성분 전개 없이 'OO혼합제제', 'OO믹스' 등의 묶음 명칭으로 괄호 없이 단독 기재되어 있다면 무조건 기계적으로 적발(🚨)하십시오.

🔥 **Rule 45. [선택적 누락/마케팅 수식어 생략 허용]**
   - 서류에는 '유기농', '천연' 등의 마케팅 수식어가 포함되어 있더라도, 패키지 시안에서 해당 수식어를 생략(선택적 누락)하고 일반 명칭으로 표기하는 것은 완벽한 합법(✅)입니다. (법적 위반 없음)

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자 포함 시 하위 내역 스캔.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정]**
   - 영문 제품명과 뒷면 한글 제품명 불일치 시 합법.

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(순서)와 한글라벨(최종 명칭) 분리.

🔥 **Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 앞면에 함량(%) 강조 시 반드시 '고형분 함량(%)' 병기 강제.

🔥 **Rule 51. [고형분(Brix) 보수적 표기 예외]**
   - 시안 수치가 서류 스펙보다 낮으면 합법(✅).

🔥 **Rule 52. [단순 명칭 강조 및 '함유/급원' 4조건 완벽 방어 룰]**
   - 제품명이나 패키지 여백(앞면, 측면 등)에 단순히 영양소 명칭이나 함량(예: 단백질 4g, 아연 함유 등)을 뱃지나 리스트 형태로 나열한 경우에도 **"단순 정보 제공"이라며 룰 적용을 회피하지 마십시오. 영양정보표 바깥에 기재된 모든 영양소 텍스트/수치는 예외 없이 영양강조표시로 간주**하여 컷오프(%)를 검증하십시오.
   - **[대원칙]**: 4가지(100g당, 100mL당, 100kcal당, 1회섭취량당) 중 **단 하나라도 충족하면 합법(✅)**.
   - **['함유', '급원', 단순 강조 표시 기준]**:
     1) **단백질, 식이섬유**: 기준치의 10%(100g당) / 5%(100mL당) / 5%(100kcal당) / 10%(1회섭취량당) 이상.
     2) **비타민 및 무기질**: 기준치의 15%(100g당) / 7.5%(100mL당) / 5%(100kcal당) / 15%(1회섭취량당) 이상.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 제품명에 농수산물이 쓰이면 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성]**
   - 단일 원료 2개국 병기 시 비율 생략 확인 요망.

🔥 **Rule 55. [영양성분 반올림 강박 금지 및 '보수적 표기(안전율)' 합법성 룰]**
   - 식약처 고시에 따라 영양소는 "그 값을 그대로 표시하거나" 지정된 단위로 반올림하여 표시하는 것이 선택적으로 허용됩니다.
   - ⭐ **[보수적 표기(안전율) 절대 인정]**: 공장 생산 편차를 고려하여 상한선(120%) 규제 대상(당류, 지방, 나트륨, 콜레스테롤 등)을 실측값보다 다소 높게 적거나, 하한선(80%) 규제 대상(단백질 등)을 실측값보다 낮게 적는 '보수적 표기'는 실무적 정석이며 완벽한 합법입니다.
   - 따라서 1g 단위, 5mg 단위 등 식약처 반올림 단위에 딱 떨어지지 않게 임의 표기(예: 13g, 19mg)했더라도, 실측 수치가 80%~120% 허용 오차 범위 안에만 들어온다면 절대로 반올림 규정을 들이밀며 🚨부적합 처리하지 마십시오.

🔥 **Rule 56. [HACCP 인증 마크 제품유형별 교차 검증 (멸균유 포함)]**
   - HACCP 마크 내부의 텍스트가 현재 검토 중인 [제품유형]과 일치하는지 반드시 대조하십시오.
   - **[공용 허용]**: "안전관리인증" 텍스트는 모든 식품/축산물 유형에서 합법(✅).
   - **[일반 식품]**: "식품안전관리인증" 텍스트 합법(✅). (축산물에 사용 시 🚨부적합)
   - ⭐ **[축산물 (냉장 우유, 가공유, 상온 멸균유 등 모두 포함)]**: "축산물안전관리인증" 텍스트 합법(✅). 만약 [식품유형]이 축산물(유가공품)인데 마크에 **"식품안전관리인증"**이라고 적혀 있다면 명백한 규정 위반이므로 🚨부적합 처리하십시오. (멸균 제품이더라도 우유류는 축산물입니다!)

🔥 **Rule 57. [세트포장 수량 강제 룰]**
   - 박스 번호에 "수량(X입)" 기재 확인.

🔥 **Rule 58. [함량 생략 합법성]**
   - 앞면에 함량(%) 명시 시 뒷면 생략 합법(✅).

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 패키지 어디에든 1399 등이 하나라도 존재하면 무조건 합법(✅).

🔥 **Rule 60. [복합원재료 원물 함량 기재 면제 룰]**
   - 괄호 안에 '고형분(%)' 명시 시 배합함량 기재 강요 면제(✅).

🔥 **Rule 61. [국산 가공 예외 룰]**
   - 괄호 없이 곧바로 (국산) 표기 시 합법.

🔥 **Rule 62. [보관상태 의무 표시 및 멸균 예외 룰]**
   - 냉장/냉동 제품인 경우 상태 명시 필수. 단, 멸균팩 등 상온 보관 제품은 냉장 표시 의무가 없으므로 제외(✅).

🔥 **Rule 63. [190mL 전용 질소충전 양방향 확인(실무자 크로스체크) 룰]**
   - 190mL 용량의 제품은 패키지 형태(미드팩 vs 콤비스마일 등 무균팩)에 따라 질소충전 문구 기재 여부가 완전히 다릅니다. (미드팩=기재 필수, 콤비스마일/멸균팩=기재 불가)
   - 따라서 시안의 내용량이 190mL인 경우, 시안에 "질소충전" 문구가 **있어도 ⚠️(확인 요망)** 처리하고, **없어도 ⚠️(확인 요망)** 처리하십시오.
   - 사유에는 "⚠️ 190mL 제품입니다. 미드팩인 경우 '질소충전' 문구가 필수이고, 콤비스마일(무균팩)인 경우 해당 문구를 삭제해야 하므로 실무자의 재질 확인이 필요합니다."라고 안내하여 인간 담당자가 최종 판단하게 하십시오.

🔥 **Rule 64. [원물 기만표시 검증]**
   - 강조 비율이 추출액 비율이면 기만(🚨).

🔥 **Rule 65. [내부 식별 코드 생략 합법성]**
   - `-2` 등 내부 코드는 생략 합법.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 복붙 적발]**
   - 박스 시안 영양표시의 수치가 박스 전체의 '총 내용량' 기준임에도 불구하고, 낱팩 1개의 용량을 그대로 복사해서 붙여넣은 경우 치명적인 복붙 에러(🚨)로 처리하십시오. 외포장(박스)에는 반드시 '1개당'이라는 기준이 명시되거나 전체 용량에 맞게 환산되어야 합니다.

🔥 **Rule 70. [내/외포장 100% 일치 강제 및 내용량 예외 룰]**
   - 내포장(팩)과 외포장(박스)을 1:1 대조할 때, **'내용량 및 열량' 표기 방식은 예외**로 둡니다. 외포장에 전체 수량(X개입)을 곱한 총 내용량이 올바르게 적혀 있고 팩에는 단일 용량이 적혀 있다면, 텍스트가 다르더라도 🚨부적합 처리하지 말고 완벽한 합법(✅)으로 판정하십시오.
   - 원재료명, 주의문구, '1개당 영양성분 수치' 등 나머지 공통 표시사항은 텍스트 픽셀 단위로 대조하여 단 하나의 기호나 숫자라도 틀리면 무조건 부적합(🚨) 처리하십시오.

🔥 **Rule 71. [강조 폰트 크기 규정]**
   - 원료 함량 14pt 육안 확인 알림.

🔥 **Rule 72. ['조리예/이미지 사진' 점검]**
   - 연출 사진 텍스트 스캔.

🔥 **Rule 73. [세부 재질 검증]**
   - 뚜껑 있는 종이팩 `뚜껑: HDPE` 등 세부 재질 확인.

🔥 **Rule 74. [액상 음료 개봉 후 주의문구 강제 스캔]**
   - "개봉 후 냉장보관..." 등 스캔.

🔥 **Rule 75. [CS 클레임 방어용 주의문구 세트]**
   - 침전물, 용기 팽창 등 방어 문구 스캔.

🔥 **Rule 76. [OEM 업소명 타이틀 강제 스캔]**
   - 위탁생산 시 자사 상호명 앞 '유통전문판매원:' 필수(🚨).

🔥 **Rule 77. [범용 식품유형 필수 주의문구 강제 스캔]**
   - 냉동, 고카페인, 고체 젤리(액체류 지적 불가), 아스파탐 필수 문구 스캔.

🔥 **Rule 78. [특수의료용도식품 타겟 광고 문구 합법성 검증]**
   - 특수의료용도식품 질환자를 타겟으로 한 영양공급 강조 문구는 무조건 합법(✅).

🔥 **Rule 79. [열량 구성비(%) 정밀 역산 룰]**
   - 탄수화물:단백질:지방 열량비율 역산 시 [당질(탄수화물-식이섬유) × 4kcal] + [식이섬유 × 2kcal] 필수.

🔥 **Rule 80. [선물세트 박스(외포장) 영양정보 레이아웃 강제]**
   - 박스 영양정보표 상단에 `총 내용량 OOO mL (OOO mL X O개입)` 및 `1개당` 포맷 확인. 영양정보표 내부 폰트 비율 임의 축소는 부적합(🚨) 처리.

🔥 **Rule 81. [영양표시 하단 면책 문구 토시 대조]**
   - 면책 문구 기호 100% 일치 확인.

🔥 **Rule 82. [영양소 법정 단위 엄격 검증]**
   - 비타민 단위 등 특수기호 100% 대조.

🔥 **Rule 83. [영양성분 % 병기 강제 원칙]**
   - 기준치 존재 성분 옆에 비율(%) 병기 필수.

🔥 **Rule 84. [유기농/친환경 단어 원천 차단 룰]**
   - '유기농', '유기' 단어가 있으면 반드시 인증 마크 + 95% 이상 함량 조건 충족.

🔥 **Rule 85. [식품첨가물 공전 명칭 사수 및 기호 창조 절대 금지]**
   - 명칭 축약 엄격 금지, 괄호 외 임의 기호 창조 전면 금지(🚨).

🔥 **Rule 86. [국가 공인 인증 도안 기만 및 텍스트 편법 규제 룰]**
   - 도안 미사용 텍스트 편법 적발 시 부적합(🚨).

🔥 **Rule 87. [특정균 강조 표시 및 균수 분리 기재 합법성 룰]**
   - 특정균 사용 시 주표시면 배합함량(%), 정보표시면 균수(CFU) 분리 기재 합법(✅).

🔥 **Rule 88. [100% 강조표시 기만 검증 룰]**
   - **[원재료 100% 금지]**: 패키지 시안(주표시면, 기타면 등 전체)에 "OO(원료명) 100%"라고 함량만을 단독으로 강조한 경우, 서류상 배합비에 정제수나 식품첨가물이 단 0.01%라도 존재한다면 무조건 소비자 기만(🚨부적합)으로 판정하십시오. (단, 농축액을 희석한 환원 제품으로서 첨가물을 바로 옆에 명시한 경우는 예외)
   - **[원산지 100% 합법]**: 단, "국산 OO 100%" 또는 "특정국가산 OO 100%"처럼 '원산지'를 수식하는 100% 표기는 배합비에 다른 첨가물이나 정제수가 섞여 있어도 완벽한 합법(✅)입니다.

🔥 **Rule 89. [국내 제조 가공품 원료의 원산지 이중 표기 규정 (농관원 유권해석)]**
   - 수입 원물을 국내에서 가공하여 품목제조보고를 마친 '국내 제조 가공품(예: 옥배유, 사과농축액 등)'을 납품받아 원료로 사용할 경우, 단순히 `원료명(국가명)` 형태로 기재하면 위법(🚨부적합)입니다.
   - 한글표시사항 등 서류에서 '품목제조보고번호'가 확인되거나 제조원이 국내 업체라면 가공품이므로, 반드시 `원료명(원료명: 국가명)` 형태로 괄호 안에 원료명을 한 번 더 명시한 뒤 원산지를 적어야 합법(✅)입니다.
   - (위법 예시) `옥배유(스페인산)` -> 🚨부적합 / (합법 예시) `옥배유(옥배유: 스페인산)` -> ✅적합

🔥 **Rule 90. [범용 명칭 치환(유연한 맵핑) 룰]**
   - 서류상에 기재된 여러 종류의 시럽류(예: 우베향시럽, 기타과당 등), 페이스트류, 화이버(식이섬유) 등의 복합원재료가 패키지 시안에서는 식품유형에 따라 `당류가공품1`, `당류가공품2`, `올리고당`, `혼합제제` 등의 범용 명칭으로 치환되어 묶음 표기되는 것은 식품업계의 보편적인 합법 관행입니다.
   - 따라서 시안에 '당류가공품' 등이 있는데 서류 1열 명칭과 글자가 똑같지 않다고 해서 무조건 누락(🚨부적합) 처리하지 마십시오. 서류의 비고란이나 하위 전개 성분을 논리적으로 추론하여 시안의 범용 명칭과 유연하게 매칭(맵핑)하고 ✅적합 처리하십시오.
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

ALL_RULES_NUMBERS = list(range(1, 91))
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    for key in ["result_tab1", "result_tab2", "result_tab3", "result_tab4", "result_tab5", "result_summary", "uploaded_content", "local_file_paths"]:
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
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V311.80 - 한도 해제 및 Rule 44 방탄 패치)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        with st.expander("⚙️ 고급 설정 (수동 텍스트 입력)", expanded=False):
            st.info("💡 텍스트가 너무 빽빽해서 AI가 글자를 빼먹는다면, 디자이너 원본 텍스트 복붙해 주세요.")
            st.session_state["manual_target"] = st.text_area("📦 타겟(박스) 원재료명 직접 입력", height=100)
            st.session_state["manual_compare"] = st.text_area("🧃 비교용(팩) 원재료명 직접 입력", height=100)

        st.markdown("#### 📌 기본 검토 조건")
        product_type = st.radio("1. 식품유형", ("일반식품 (두유류 등 - 냉장표시 의무 없음)", "특수의료용도식품 / 환자식", "축산물 (유가공품: 우유, 가공유, 멸균유 등)"))
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
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    st.toast(f"👁️ Vision API가 [{label}] 텍스트를 추출 중입니다...", icon="👁️")
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
                if not content:
                     st.warning("⚠️ 업로드된 파일이 없거나 처리할 수 없습니다. 파일을 확인해주세요.")
                else:
                    st.session_state["uploaded_content"] = content
                    st.session_state["local_file_paths"] = paths
                    
                    st.session_state["has_recipe"] = bool(recipe_docs)
                    st.session_state["has_labels"] = bool(label_docs)
                    st.session_state["doc_type_state"] = doc_type
                    st.session_state["inspection_mode_state"] = inspection_mode
                    
                    st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_missions_list: list = None):
        if not st.session_state["uploaded_content"]:
            st.warning("🚨 좌측 사이드바 하단의 [🚀 전체 시스템 파일 연동] 버튼을 먼저 눌러주세요.")
            return None

        content = st.session_state["uploaded_content"]
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        # ⭐ V311.80: max_output_tokens=65536 복구 (물리적 한도 차단 해제)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        extracted_text_combined = ""

        if extract_missions_list:
            extracted_results = []
            for i, mission in enumerate(extract_missions_list):
                pass1_prompt = f"""
[PASS 1 - 텍스트 단일 추출 미션]
🎯 [현재 타겟 미션]: {mission}
"""
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        pass1_response = model.generate_content(
                            content + [pass1_prompt], 
                            generation_config=generation_config, 
                            safety_settings=safety_settings, 
                            request_options={"timeout": 600}
                        )
                        extracted_results.append(get_safe_text(pass1_response))
                        break
                    except Exception as e:
                        if "504" in str(e) or "Deadline" in str(e) or "503" in str(e):
                            if attempt < max_retries - 1:
                                time.sleep(10)
                                continue
                        return f"🚨 Pass 1 시스템 오류 발생: {e}"
            
            extracted_text_combined = "\n\n".join(extracted_results)

            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 종합 자체검증 명령]
{extracted_text_combined}
"""
            verified_text = extracted_text_combined
            for attempt in range(max_retries):
                try:
                    pass15_response = model.generate_content(
                        content + [pass15_prompt], 
                        generation_config=generation_config, 
                        safety_settings=safety_settings, 
                        request_options={"timeout": 600}
                    )
                    verified_text = get_safe_text(pass15_response)
                    break
                except Exception as e:
                    if "504" in str(e) or "Deadline" in str(e) or "503" in str(e):
                        if attempt < max_retries - 1:
                            time.sleep(10)
                            continue
                    break 

        pass2_context = ""
        if extract_missions_list:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================
"""
        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
[제품유형]: {product_type}
[검토모드]: {inspection_mode}
[증빙서류 형태]: {doc_type}
[우리 공장 알레르기 마스터 목록]: {factory_allergens}
[이 탭에 적용되는 핵심 룰]
{tab_rules}
{pass2_context}

🔥 [최종 출력 양식 및 절대 강제 지침] 🔥
아래 제시된 [출력 양식]의 뼈대(제목, 표 헤더 등)만 그대로 복사하여 내용을 채워 넣으십시오.
(주의: 뼈대에 없는 부연 설명이나, 룰에 대한 텍스트는 출력 화면에 보이지 않도록 절대 출력하지 마십시오. 오직 표와 결과만 깔끔하게 출력하십시오.)

[출력 양식]
{judgment_prompt}
"""
        for attempt in range(3):
            try:
                pass2_response = model.generate_content(
                    content + [pass2_prompt], 
                    generation_config=generation_config, 
                    safety_settings=safety_settings, 
                    request_options={"timeout": 600}
                )
                final_clean_text = get_safe_text(pass2_response)

                if extract_missions_list:
                    return f"<clean_view>\n{final_clean_text}\n</clean_view>\n<pass1_log>\n{extracted_text_combined}\n</pass1_log>\n<pass15_log>\n{verified_text}\n</pass15_log>"
                return final_clean_text
            except Exception as e:
                if "504" in str(e) or "Deadline" in str(e) or "503" in str(e):
                    if attempt < 2:
                        time.sleep(10)
                        continue
                return f"🚨 Pass 2 오류 발생: {e}"

    def run_qc_model(prompt_text):
        if not st.session_state["uploaded_content"]:
            return None
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        # ⭐ V311.80: max_output_tokens=65536 복구
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        full_prompt = f"""
        [제품유형]: {product_type}\n[검토모드]: {inspection_mode}\n[우리 공장 알레르기 마스터 목록]: {factory_allergens}
        {RULE_BOOK_FULL}\n========================================\n{prompt_text}
        """
        try:
            response = model.generate_content(st.session_state["uploaded_content"] + [full_prompt], generation_config=generation_config)
            return fix_markdown_table(get_safe_text(response))
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    def display_result(result, tab_name=""):
        if not result: return
        
        clean_match = re.search(r'<clean_view>(.*?)</clean_view>', result, re.DOTALL)
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)

        if pass1_match or pass15_match:
            with st.expander(f"🕵️‍♂️ [시스템 로그실] {tab_name} Pass 연산 원본 추출 데이터 보기 (필요시 클릭)"):
                if pass15_match:
                    st.info("✅ Pass 1.5 자체 복정 완료본 (오독/환각 제거 확정본)")
                    st.code(pass15_match.group(1).strip())
                if pass1_match:
                    st.text("📋 Pass 1 분할 미션 원본 로그")
                    st.code(pass1_match.group(1).strip())
            st.markdown("---")

        if clean_match:
            st.markdown(fix_markdown_table(clean_match.group(1).strip()))
        else:
            st.markdown(fix_markdown_table(result))

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "🤖 5️⃣ AI 법률 스캔", "📊 6️⃣ 종합 보고서"])

    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【정밀 법리 검수 매트릭스 연산 중...】"):
                missions = [
                    "주표시면(앞면) 이미지에서 제품명, 내용량, 마케팅 문구뿐만 아니라, **표나 리스트 형태로 나열된 '모든 영양성분/원재료의 명칭과 함량 수치'를 단 하나도 누락 없이 100% 추출**하여 영양강조 컷오프 심사대로 넘기십시오.",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 앞면에 강조된 특정 영양소의 '% 기준치' 추출.",
                    "업로드된 서류에서 주표시면에 강조된 성분의 투입량(%)과 실측값(mg/g) 추출.",
                    "시안 전체에서 원재료명 리스트를 찾아 추출하십시오."
                ]
                judgment_prompt = """## 1️⃣ [주표시면 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 검토 결과 및 사유 (오탈자 무관용, 상세히 서술) | 판정 |
| :--- | :--- | :--- | :--- |
| **제품명 및 특정 원료(특정균) 강조 기준** | [Rule 9, 53, 87] | | |
| **강조 폰트 크기** | [Rule 71] | | |
| **조리예/이미지 사진 표기** | [Rule 72] | | |
| **보관상태(상온/냉동/냉장) 명시** | [Rule 62] | | |
| **세트포장 앞면 총내용량/열량** | [Rule 3] | | |
| **다포장 낱팩 복붙 여부** | [Rule 68] | | |
| **원액/추출물 고형분 병기** | [Rule 50] | | |
| **영양강조 컷오프(4대 조건)** | [Rule 21, 52] | (※ 100g, 100mL, 100kcal, 1회섭취량 중 하나라도 충족하는지 수식으로 증명할 것) | |
| **국가 공인 인증 도안 마케팅** | [Rule 86] | | |
| **유기농/친환경 마크 검증** | [Rule 84] | | |
| ⭐ **전체 텍스트 오탈자 및 띄어쓰기 스캔** | 전수 검사 | (모든 주의문구, 설명글 등의 오타 및 띄어쓰기 점검) | |
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【원재료 1:1 매칭 매트릭스 연산 중...】"):
                has_recipe = st.session_state.get("has_recipe", False)
                has_labels = st.session_state.get("has_labels", False)
                has_any_doc = has_recipe or has_labels
                doc_mode = st.session_state.get("doc_type_state", "통합 엑셀/PDF 자료 (마스터표 생략)")
                ins_mode = st.session_state.get("inspection_mode_state", "단품(팩/단일포장) 기본 검토")

                missions = [
                    "시안(주표시면/정보표시면)에 기재된 원재료명, 알레르기 유발물질, 교차오염 주의문구, 행정 정보(제조원 등)를 모두 추출하십시오.",
                    "시안에 기재된 원재료명 중 '식품첨가물'을 추출한 뒤, 하드코딩된 DB(표 4, 5, 6)와 대조하여 소속을 명확히 지정하십시오.",
                    "⭐ [절대 미션: 개별 단위 쪼개기]: 추출한 원재료명을 쉼표(,)를 기준으로 완벽하게 쪼개서 각각 독립된 개별 리스트로 만드십시오."
                ]
                
                # ⭐ V311.80: 생략(엘립시스) 금지 원천 차단 및 Rule 44 특별 스나이퍼 장착
                tab2_special_rules = RULES_TAB2 + """
                \n\n🔥 [Tab 2 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)] 🔥
                1. [절대 생략 금지 및 (...) 기호 원천 차단]: 어떠한 경우에도 `(...)` 기호나 `등`을 사용하여 텍스트를 요약, 얼버무리지 마십시오. 시안과 서류에 적힌 괄호 안의 하위 성분까지 100% 한 글자도 빠짐없이 모두 타이핑하십시오. (출력 길이 제한이 없으므로 무조건 끝까지 쓰십시오)
                2. [Rule 44 '명칭 유지 병합' 범용 스나이퍼 족쇄]: 제품에 중복으로 투입된 복합원재료(혼합제제)를 병합 표기할 때, 껍데기 명칭(예: 'OO혼합제제', 'OO믹스', 'OO베이스' 등)을 그대로 적어 퉁치는 것은 절대 위법(🚨부적합)입니다. 여러 원료에 흩어진 동일 혼합제제를 합칠 때는 반드시 최하위 단일 성분 단위로 전개/해체해야 합법입니다. 시안에 중복 투입된 복합원재료가 하위 성분 전개 없이 단일 묶음 명칭으로만 기재되어 있다면 무조건 "최하위 단일 성분으로 해체하지 않고 복합 명칭을 유지하여 병합했으므로 위법"이라고 🚨부적합 판정하십시오.
                3. [100% 상세 서술]: 표 작성 시 판정 이유를 절대로 생략하거나 짧게 쓰지 마십시오. 적합/부적합에 관계없이 룰(Rule) 번호와 근거를 구체적으로 서술하십시오.
                4. [마스터 DB 원본 복사]: 서류에서 데이터를 추출할 때 오직 서류 원문에 있는 [식품유형, 제품명, 한글표시사항, 원산지, 알러지유발물질] 5개 정보만 그대로 복사하여 2-1 마스터표를 작성하십시오.
                5. [순서 역전 정밀 검증]: 2% 이상 원료의 배합비 순위를 대조하고, 서류와 시안의 순서가 역전되었다면 🚨부적합 처리하십시오.
                6. ⭐ [표(Table) 레이아웃 붕괴 방어 절대 원칙]: 원재료명이나 사유 텍스트 내부에 파이프 기호(`|`)나 줄바꿈 문자(`\n`)가 포함되어 있으면 표가 깨집니다. 파이프는 슬래시(`/`)로, 줄바꿈은 띄어쓰기로 모두 대체하여 표를 출력하십시오.
                """

                judgment_prompt = ""
                step_offset = 1 if has_any_doc else 0

                if has_any_doc:
                    if "무더기" in doc_mode:
                        missions.append("업로드된 '개별 원료 한글라벨 무더기' 데이터를 분석하여 내부적으로 [마스터 배합비 데이터]를 합성하십시오.")
                    else:
                        missions.append("업로드된 증빙 서류(마스터 엑셀/PDF)에서 지정된 5개 항목만 100% 그대로 복사하여 내부 메모리에 저장하십시오.")
                    
                    judgment_prompt += "## 2️⃣-1. [서류 기반 마스터 원재료 DB]\n"
                    judgment_prompt += "| 식품유형 | 원재료의 제품명 | 원재료의 한글표시사항 | 원산지 | 알러지유발물질 |\n|---|---|---|---|---|\n\n"

                if "박스" in ins_mode:
                    missions.append("타겟(박스) 시안과 비교용(팩) 시안의 원재료명 리스트를 1줄에 1개씩 나열하여 1:1로 픽셀 대조하십시오.")
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [박스(타겟) vs 팩(비교용) 내외포장 100% 일치 대조 매트릭스]\n"
                    judgment_prompt += "| 타겟(박스) 표기 개별 원재료명 | 비교용(팩) 표기 개별 원재료명 | 대조 검증 결과 (픽셀 100% 일치 여부 상세 서술) | 최종 판정 |\n|---|---|---|---|\n\n"
                    judgment_prompt += f"### 🚨 [팩 시안 기준 최종 누락 정밀 검증]\n- (누락 원료 상세 기재 또는 '✅ 팩 시안 대비 통째로 누락된 원료 없음')\n\n"

                if has_any_doc:
                    target_name = "박스 시안" if "박스" in ins_mode else "시안"
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [마스터 서류 vs {target_name} 법적 대조 매트릭스]\n"
                    judgment_prompt += "| 시안 표기 개별 원재료명 (1줄에 1개씩) | 매칭된 서류 원료명 | ⚖️ 배합비(%) 및 순위 | 🌍 원산지 룰 검증 | 최종 대조 결과 및 사유 (무조건 100% 상세 서술, 절대 생략 금지) | 판정 |\n|---|---|---|---|---|---|\n\n"
                    judgment_prompt += f"### 🚨 [서류 기준 최종 누락 정밀 검증]\n- (누락 원료 상세 기재 또는 '✅ 서류상 누락된 원료 없음')\n\n"

                if not has_any_doc and "박스" not in ins_mode:
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [시안 표기 원재료명 리스트]\n(※ 증빙 서류 미제출로 서류 대조 및 원산지 검증 불가)\n\n"
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [자체 형식 검토 매트릭스]\n| 시안 표기 개별 원재료명 (1줄에 딱 1개씩만) | 형식 검토 결과 및 사유 (상세 서술) | 판정 |\n|---|---|---|\n\n"

                num_add = step_offset + 1
                num_mix = num_add + 1
                num_alg = num_add + 2
                num_adm = num_add + 3
                num_typ = num_add + 4

                judgment_prompt += f"### 🚨 2️⃣-{num_add}. [식품첨가물 범용 형식주의 정밀 검증]\n- **[명칭 축약 및 용도 표시 검사 결과]**:\n- **[임의 기호 창조 검사 결과]**:\n\n"
                judgment_prompt += f"## ⚖️ 2️⃣-{num_mix}. [배합비 2% 이상 원료 전개 순서 정밀 검증 (Rule 34)]\n- **[서류상 2% 이상 원료 순서 (배합비 % 포함하여 100% 상세 기재)]**:\n- **[시안에 적힌 실제 나열 순서]**:\n- **[최종 판정 및 사유]**:\n\n"
                judgment_prompt += f"## 🧮 2️⃣-{num_alg}. [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38)]\n- **[공장 마스터 목록]**:\n- **[직접 투입된 알레르기]**:\n- **[도출된 교차오염 정답지]**:\n- **[시안 표기 주의문구]**:\n- **[최종 판정 및 사유]**:\n\n"
                judgment_prompt += f"## 🏛️ 2️⃣-{num_adm}. [행정 정보 교차 검증]\n- ⭐ [Rule 76] 유통전문판매원/판매원 타이틀 강제 확인:\n\n"
                judgment_prompt += f"## 🔍 2️⃣-{num_typ}. [전체 텍스트 오탈자 및 띄어쓰기 스캔 (전수 검사)]\n- ⭐ **[검토 결과]**:\n"

                st.session_state["result_tab2"] = run_qc_3pass(tab2_special_rules, judgment_prompt, missions)
        
        display_result(st.session_state["result_tab2"], "정보표시면")

    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【영양성분표 수치 환산 및 교차 검증 중...】"):
                has_any_doc = st.session_state.get("has_recipe", False) or st.session_state.get("has_labels", False)
                ins_mode = st.session_state.get("inspection_mode_state", "단품(팩/단일포장) 기본 검토")

                missions = [
                    "타겟(박스) 시안의 영양정보표 내부 수치와 표 바깥의 총 내용량, 칼로리, '1일 영양성분 기준치' 문구 전부 추출.",
                    "비교용(팩) 시안이 있다면 영양정보표 내부 수치와 바깥 문구 전부 추출.",
                    "시험성적서 서류에서 각 영양성분의 '100g당 실측값' 데이터를 모두 추출하고, 시안에 명시된 1회 제공량(또는 1포 용량)에 맞게 환산 계수(예: 180mL면 1.8곱하기)를 적용한 계산값을 미리 준비해 두십시오. 아울러 '1일 영양성분 기준치(Rule 41)'에 따른 % 값도 수학적으로 역산해 두십시오."
                ]
                
                tab3_special_rules = RULES_TAB3 + """
                \n\n🔥 [Tab 3 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)] 🔥
                1. [Rule 23 '0' 표시 절대 원칙]: 시안의 수치를 추출하고, 성적서 환산값이 특정 기준(예: 열량 5kcal 미만, 탄수화물/당류/지방/단백질 0.5g 미만, 트랜스지방 0.2g 미만 등)에 해당하면 무조건 '0'으로 판정하십시오.
                2. [내외포장 1:1 대조 (Rule 68, 70)]: 박스와 팩의 1개당 영양 수치가 100% 픽셀 일치하는지 스캔하십시오.
                3. [수식 증명]: 반드시 '환산 수식'과 '1일 기준치 대비 %(Rule 41)'를 직접 수학적으로 계산하여 보여주십시오.
                4. [안전율 인정]: 80%~120% 오차 범위 안에 있으나 반올림 수치가 살짝 다를 경우 '보수적 표기(안전율)'로 인정하여 ⚠️(확인 요망) 처리하고 절대 🚨부적합 처리 금지하십시오.
                5. [생략 금지]: 모든 사유와 수식을 생략 없이 구체적으로 타이핑하십시오.
                """

                judgment_prompt_tab3 = ""
                
                if "박스" in ins_mode:
                    judgment_prompt_tab3 += "## 3️⃣-1. [박스(외포장) vs 팩(내포장) 영양정보 1:1 교차 검증]\n"
                    judgment_prompt_tab3 += "| 영양성분명 | 타겟(박스) 1개당 표시량 | 비교용(팩) 표시량 | 일치 여부 (단위 포함 100% 픽셀 대조) | 판정 |\n|---|---|---|---|---|\n\n"

                if has_any_doc:
                    title_prefix = "3️⃣-2." if "박스" in ins_mode else "3️⃣-1."
                    judgment_prompt_tab3 += f"## {title_prefix} [영양표시 오차 검증 및 % 기준치 수학적 역산 (성적서 대조)]\n"
                    judgment_prompt_tab3 += "| 영양성분 | 성적서 환산값(A) (계산식 포함) | 시안 표시량(B) | 법적 기준선 (80% 이상 또는 120% 이하 명시) | 🎯 % 역산 검증 (수식 포함) | 판정 및 상세 사유 (오차/안전율 판단) |\n|---|---|---|---|---|---|\n\n"
                elif "박스" not in ins_mode:
                    judgment_prompt_tab3 += "## 3️⃣-1. [영양표시 오차 검증]\n(※ 성적서 미제출로 실측 오차 검증 생략)\n\n"

                judgment_prompt_tab3 += """## 🔍 [영양성분표 치명적 레이아웃 및 단위 정밀 검증]
- ⭐ [Rule 80] 영양정보표 상단 레이아웃 확인 (총 내용량 폰트 축소 금지 포함): 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
- ⭐ [Rule 83] 기준치 존재 성분 % 병기 룰 대조:
- ⭐ **[오탈자/띄어쓰기 스캔] 영양성분표 내 텍스트 및 단위 띄어쓰기 전수 검사**:
"""
                st.session_state["result_tab3"] = run_qc_3pass(tab3_special_rules, judgment_prompt_tab3, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【의무표시 및 인증마크 해독 중...】"):
                missions = [
                    "전 구역 이미지를 스캔하여 필수 의무표시 3종(상담번호, 교환처, 1399 문구)과 HACCP 인증 마크 추출.",
                    "알레르기 직접 함유 표시(바탕색 별도 박스) 및 분리배출 마크 추출.",
                    "포장재질 표기(세부 재질 포함) 및 CS 방어/기타 주의문구 추출.",
                    "특정균(비피더스 등)의 균수 표기 문구가 기타면에 별도로 적혀있는지 추출.",
                    "기타면/측면 이미지에서 '단백질', '비타민', '칼슘' 등 특정 영양소를 강조하는 마케팅 뱃지나 텍스트, 그리고 '100%' 라는 수치 강조 문구가 있는지 빠짐없이 스캔하여 추출하십시오. (단순 정보 제공이라 자의적으로 판단하여 추출 단계를 누락하지 마십시오)."
                ]
                judgment_prompt = """## 4️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 검토 결과 및 사유 (생략 없이 무관용 100% 서술) | 판정 |
| :--- | :--- | :--- | :--- |
| **의무표시 3종 Global Scan** | [Rule 59] | | |
| **기타면 영양강조표시 정밀 검증** | [Rule 21, 52] | (※ 100g, 100mL, 100kcal, 1회섭취량 중 하나라도 충족하는지 수식으로 증명할 것. 단순 정보 제공이라는 핑계로 판정을 회피하지 말 것) | |
| ⭐ **100% 기만 표시 정밀 검증** | [Rule 88] | (※ 기타면에 '100%' 강조 문구가 있는지 스캔하고, 단순 함량 100%인지 원산지 100%인지 구분하여 판정할 것) | |
| **알레르기 교차오염 검증** | [Rule 38] | | |
| **HACCP 마크 공식 명칭** | [Rule 56] | | |
| **특정균 균수 분리 표시 의무** | [Rule 87] | | |
| **용기 세부 재질 정밀 검증** | [Rule 73] | | |
| **액상 음료 개봉 후 주의문구** | [Rule 74] | | |
| **CS 클레임 방어용 문구** | [Rule 75] | | |
| **범용 식품유형 필수 주의문구** | [Rule 77] | | |
| ⭐ **전체 텍스트 오탈자 및 띄어쓰기 스캔** | 전수 검사 | (모든 주의문구, 설명글 등의 오타 및 띄어쓰기 점검) | |
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    with tab5:
        st.info("💡 [AI 자율 스캔 모드] 기계적 검증(1~4번 탭)이 잡아내지 못하는 문맥상의 위법성, 과대광고, 소비자 기만 행위를 법령 PDF를 기반으로 심층 스캔합니다.")
        if st.button("▶️ AI 법률 자문 자율 스캔 시작", key="btn_law"):
            with st.spinner("【법률 스캔 중: 마케팅 리스크 및 심층 추적...】"):
                missions = [
                    "업로드된 시안에서 '12년 연속 1등', '특허', '효능 표방', '미래 시점(날짜) 포함 문구' 등 마케팅 카피, 제품명, 강조 문구, 뱃지 디자인만을 정밀 스캔하여 추출하십시오. (원재료명, 영양성분 숫자, 띄어쓰기는 추출 금지)",
                    "추출된 마케팅/광고 요소들이 「식품등의 표시·광고에 관한 법률」 및 고시상 부당광고(소비자기만, 허위과대광고, 객관적 근거 결여 등)에 해당하는지 업로드된 법령 PDF에서 관련 조항을 검색하여 추출하십시오."
                ]
                
                judgment_prompt = """## 5️⃣ [AI 법률 자문 자율 스캔 리포트]
⭐ [월권행위 절대 금지 및 심층 추적 명령] ⭐
1. 업무 침범 금지: 이 탭에서는 1~4번 탭에서 수행하는 '원재료명 1:1 대조', '띄어쓰기 및 오탈자 검수', '영양성분 반올림 계산' 등을 절대 수행하지 마십시오.
2. 본연의 임무: 기계적 룰(Rule 1~87)이 잡아내지 못하는 '문맥상의 위법성', '소비자 기만 가능성', '과대광고(예: 도래하지 않은 미래 날짜를 기준으로 1등 표방 등)', '신체 조직 기능 표방' 등 마케팅적 리스크만을 타겟팅하여 딥다이브(Deep-Dive) 하십시오.
3. Zero-Knowledge: 사전 학습 지식을 차단하고 오직 사용자가 업로드한 법령 PDF 파일만을 진리로 삼아 대조하십시오.

---

### 📋 [법률 스캔 결과 보고서]

(아래 구조화된 포맷을 사용하여 식별된 리스크 항목을 출력하십시오. 띄어쓰기 지적 등은 절대 하지 마십시오)

#### 📌 [식별된 문구/디자인]: "추출된 광고/마케팅 문구 및 시안 상의 위치 작성"
* **적용 법령 및 조항:** [문서명, 제O조 제O항 또는 별표 규정]
* **법령 원문:** > "PDF 원문을 그대로 인용"
* **AI 법무팀 자문 의견 (위법 리스크):**
  * 🚨 **[리스크 총평]:** (법령에 근거한 객관적인 위법 사유 또는 면제 사유 요약)
  * 🔍 **[다면(Double-Check) 교차 검증 결과]:** (광고의 객관적 근거 결여, 시점 오류, 소비자 오인 가능성 등 문맥상 리스크를 날카롭게 지적)
---
"""
                st.session_state["result_tab5"] = run_qc_3pass("", judgment_prompt, missions)
                
        display_result(st.session_state.get("result_tab5", None), "AI법률스캔")

    with tab6:
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"], st.session_state["result_tab3"], st.session_state["result_tab4"], st.session_state.get("result_tab5")]):
                st.warning("🚨 앞의 1~5번 탭 중에서 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("최종 수정 지시서를 작성 중입니다..."):
                    def strip_logs(result):
                        if not result: return "분석 안 함"
                        return result.strip()

                    combined_results = f"""
[1번 탭 결과]: {strip_logs(st.session_state.get('result_tab1'))}
[2번 탭 결과]: {strip_logs(st.session_state.get('result_tab2'))}
[3번 탭 결과]: {strip_logs(st.session_state.get('result_tab3'))}
[4번 탭 결과]: {strip_logs(st.session_state.get('result_tab4'))}
[5번 탭(AI자율스캔) 결과]: {strip_logs(st.session_state.get('result_tab5'))}
"""
                    summary_prompt = f"""## 6️⃣ [최종 종합 검토 리포트]
[지시]: "안녕하세요" 등 일체의 인사말이나 부연 설명 없이 아래 뼈대를 그대로 복사하여 내용을 채운 뒤 즉시 출력하십시오.

- **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)

### 📌 [핵심 지적 사항 및 수정 지시]
(위 분석 데이터들을 바탕으로 실무자가 즉시 인쇄하여 패키지를 전면 수정할 수 있도록 번호순 불릿 포인트로 작성)

========================================
[🚨 AI가 반드시 읽고 요약해야 할 1~5번 탭 상세 검토 데이터]
{combined_results}
========================================
"""
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])

if __name__ == "__main__":
    if check_password():
        main()
