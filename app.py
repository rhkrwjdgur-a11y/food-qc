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
import datetime

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

# ⭐ 최고급 Pro 모델 유지 (컨텍스트 윈도우 및 토큰 한도 최대치 확보)
MODEL_NAME = "gemini-2.5-pro"
# ⚡ 비용 절감용 초고속/경량 모델 (맞춤법 전용)
MODEL_NAME_FLASH = "gemini-2.5-flash"

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

🔥 [절대 생략 금지 및 100% 원본 보존의 법칙 (치명적 오류 방어)]:
어떠한 경우에도 텍스트를 임의로 요약하거나 `(...)`, `...`, `생략`, `이하 생략`, `등` 과 같은 기호나 단어를 사용하여 출력을 얼버무리지 마십시오. 
표(Table)를 작성할 때 원재료가 100개든 영양성분이 50개든 첫 줄부터 마지막 줄까지 100% 풀스펠링으로 끝까지 타이핑해야 합니다. 말줄임표나 생략 관련 단어를 하나라도 사용하는 순간 치명적인 시스템 오류로 간주됩니다.

🔥 [0순위 절대 방어막: 5% 미만 복합원재료 과잉 지적 금지 (Rule 5 적용)]:
어떤 첨가물이나 원료의 표기 누락(또는 용도 누락)을 지적하기 전에, **반드시 그 원료가 배합비 5% 미만인 복합원재료의 하위 성분인지 가장 먼저 확인하십시오.** 5% 미만 일반 복합원재료의 하위 성분이라면 [표 4, 5, 6] 첨가물 규정 등 모든 규정을 무시하고 **무조건 "전개/표시 의무 면제(✅)"로 판정**하십시오. (단, 알레르기 물질은 예외이며 혼합제제는 이 면제 룰에서 절대 제외됩니다.)

🔥 [식품첨가물 표기 특별 통제 원칙]: 
원재료명 란의 첨가물을 판정할 때, 반드시 아래 하드코딩된 DB를 먼저 대조하여 판정하십시오.
* [표 4 소속 (명칭+용도 병기 강제, 누락시 🚨부적합)]: {ADDITIVE_TABLE_4}
* [표 5 소속 (명칭 또는 간략명만 표시, 용도 생략해도 ✅합법)]: {ADDITIVE_TABLE_5}
* [표 6 소속 (명칭, 간략명, 주용도 중 선택 표시 ✅합법)]: {ADDITIVE_TABLE_6}

모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 마스터 룰북 원문 (100% 무손실 보존본)
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
   - **[Rank B: 원산지 산정용 순위 적용]**: 원산지 표시 의무는 전체 배합비 순위가 아닌, 아래 Rule 28에 따라 필터링된 **[Rank B]의 1위, 2위, 3위** 원료에만 발생합니다. (누락 시 🚨부적합). Rank B에서 4위 이하인 원료는 원산지 표시 의무가 없습니다.
   - **[98% 컷오프 예외]**: 단, Rank B 1순위 원료 단독으로 98% 이상이면 1순위만 표기, 1순위와 2순위 배합비의 합이 98% 이상이면 2순위까지만 표기해도 합법(✅)입니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 개별 향료명이 명시되어 있어도, 시안 원재료명에 단순히 '향료'로 묶어 표기 가능. (단, Rule 85 참고)

🔥 **Rule 3. [주표시면 vs 영양성분표 누락 교차검증 강제 룰]**
   - 주표시면(앞면)이나 기타면에 특정 영양성분(예: 나이아신, 비타민E 등)의 함량이나 명칭이 강조되어 있다면, 해당 성분은 반드시 뒷면 영양정보표 테두리 안에도 기재되어야 합니다.

🔥 **Rule 4. [배합비 데이터 누락 시 동적 추론(Dynamic Inference) 및 무죄 추정 룰]**
   - 증빙 서류에 배합비(%) 데이터가 없더라도 절대 판정을 포기(⚠️)하거나 멈추지 마라.
   - **[순위 추론]**: 시안(포장지)에 나열된 원재료의 텍스트 순서 자체가 '중량순(Rank A)'이라고 100% 신뢰하고 가정하라. 이를 바탕으로 Rule 28에 따른 원산지 타겟(Rank B 1~3위)을 스스로 소거법으로 도출하여 원산지 표시 여부를 깐깐하게 대조하라.
   - **[2% / 5% 룰 유연화]**: 정확한 %를 알 수 없으므로, 나열 순서에 대한 지적(Rule 34)은 무조건 합법(✅)으로 간주하라. 복합원재료 전개 생략(Rule 5)의 경우 부적합 처리하지 말고 "배합비 5% 미만 조건에 의한 합법적 생략인지 실무자 확인 요망"이라며 ⚠️(확인 요망) 처리하라.

🔥 **Rule 5. [복합원재료 5% 미만 전개 면제 및 🌟혼합제제 절대 예외 룰]**
   - **[대원칙]**: 배합비 5% 미만인 **'복합원재료(일반 가공식품)'**는 괄호를 열고 하위 성분을 전개할 의무가 아예 없습니다. 생략 합법(✅).
   - 🌟 **[첨가물 과잉 단속 금지 원칙]**: 위 조건에 따라, 5% 미만 '일반 복합원재료' 내부에 [표 4, 5, 6] 소속 식품첨가물이 들어있더라도 명칭/용도 표시 의무가 완전히 면제됩니다.
   - 🚨 **[혼합제제 절대 면제 불가 - Rule 44와 연계]**: 서류상 식품유형이 **'혼합제제'**인 원료는 이 5% 미만 면제 룰이 **절대로 적용되지 않습니다.** 혼합제제의 하위 성분을 검사할 때는 이 Rule 5를 완전히 머릿속에서 지우고, 무조건 **Rule 44**로 넘어가서 [표 4, 5, 6] 기준에 따라 첨가물 용도 표시 여부를 깐깐하게 따지십시오.

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

✅ **Rule 12. [원재료명 교차 검증 및 임의 추론 금지]**
   - 서류 없이 레시피 상상 금지.

🔥 **Rule 13. [알레르기 표기 시각적 한계 보완 및 실무 확인 룰]**
   - 알레르기 물질은 원재료명과 바탕색이 구분되는 '별도 란(박스)'에 기재해야 합니다.
   - **[AI 시각적 한계 보완]**: 텍스트 스캔 결과 시안에 **'OO 함유'**라는 독립 문구가 존재한다면 일단 알레르기 표시란 규정을 준수한 것으로 간주하여 **✅(적합)** 처리하고, 사유에 육안 확인 권장 멘트를 추가하십시오.

🔥 **Rule 14. [첨가물 표 4, 5, 6 교차 검증 및 표 6 주용도 합법성]**
   - **[표 4]**: 명칭과 용도(예: 감미료) 둘 다 표시 필수.
   - **[표 5]**: 명칭 또는 간략명 표시 필수 (용도만 표시 불가).
   - ⭐ **[표 6 특권]**: 명칭, 간략명, 또는 **'주용도(예: 유화제, 산도조절제, 팽창제 등)' 중 하나만 단독으로 표시해도 완벽한 합법(✅)**입니다. 

✅ **Rule 15. [기능성 오인 문구 및 신체 조직 작용 전면 통제]**
   - 신체의 기능·작용·효과를 직접 암시하거나 기만하는 표현 전면 금지(🚨부적합).

✅ **Rule 16. [원산지 100% 표기 룰]**
   - 단일 국가 100% 수입 원료만 100% 강조 가능.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지 첨가물 배제 강조 시 부적합(🚨).

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 영유아 타겟 명칭 사용 적발.

✅ **Rule 19. ['무당' vs '무가당' 분리 검증]**
   - 무당(Zero Sugar): 완제품 기준 100g(mL)당 0.5g 미만 시 합법. 무가당(No Added Sugar): 제조 공정 중 당류를 인위적으로 첨가하지 않은 경우.

🔥 **Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무 없음.

🔥 **Rule 21. ['고/풍부', '저', '무' 영양강조표시 4대 조건 OR 법칙 및 수학적 증명 룰]**
   - **[대원칙]**: 식약처 고시에 따라 영양강조 기준은 4가지(100g당, 100mL당, 100kcal당, 1회섭취량당) 중 **단 하나라도 충족하면 무조건 합법(✅)**입니다.
   - 단백질, 식이섬유 '고/풍부': 기준치의 20%(100g), 10%(100mL) 등 적용.

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 함.

🔥 **Rule 23. [식약처 영양성분별 '0' 표시 절대 규정 (0.1, 0.2, 0.5 룰)]**
   - **[열량]**: 5kcal 미만 -> "0kcal", **[나트륨]**: 5mg 미만 -> "0mg", **[탄수화물, 당류, 단백질, 지방]**: 0.5g 미만 -> "0g", **[트랜스지방]**: 0.2g 미만 -> "0g", **[포화지방]**: 0.1g 미만 -> "0g", **[콜레스테롤]**: 2mg 미만 -> "0mg"

🔥 **Rule 24. [무당/무가당 강조표시 연계 의무 표기 유연성 룰]**
   - 무당/저당 강조 시 열량 병기 의무를 검사할 때, 해당 강조 문구 바로 옆이 아니더라도 주표시면의 동일한 시야각 내에 열량(kcal)이 충분히 명확하게 기재되어 있다면 합법(✅)으로 유연하게 판정하십시오.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 분리.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 g, 액체는 mL.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등은 100kcal 당 조건을 적용 금지.

🔥 **Rule 28. [Rank A vs Rank B 분리 및 원산지 산정 예외 4대장 룰]**
   - **[Rank A: 배합비 절대 순위]**: 모든 원료의 원래 % 비율대로 세운 순위.
   - **[Rank B: 원산지 산정용 순위]**: 전체 배합비 목록에서 **[정제수, 당류가공품, 주정, 식품첨가물]** 이 4가지 카테고리의 원료를 100% 삭제(제외)하고, 남은 실질 원료들끼리만 다시 %를 비교하여 매긴 순위. 원산지 의무는 오직 이 Rank B를 기준으로 심사하십시오.

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
   - 원재료명은 반드시 서류상의 배합비율(%)이 높은 중량 순서대로 기재되어야 합니다. 역전 시 명백한 위반(🚨).
   - 단, 배합비율이 **2% 미만**인 원료들은 중량 순서에 상관없이 자유롭게 기재해도 완벽한 합법(✅)입니다.

🔥 **Rule 35. [🌟 범용 간략명/관용명 허용 및 혼합제제 괄호 내부 N종 은폐 금지 범용 룰]**
   - **[관용명/동의어 합법 처리]**: 실무적으로 호환되는 동의어나 관용명 표기는 100% 합법(✅)입니다. (예: 옥배유=옥수수기름)
   - **[용도명 N종 무조건 합법]**: **'향료 3종', '영양강화제 3종', '유화제 2종'**처럼 [표 6]에 속하는 주용도명 뒤에 숫자를 붙여 묶는 단어는 식약처 규정상 **완벽한 합법**입니다. 
   - ⭐ **[혼합제제 괄호 내부 은폐 절대 불가]**: 패키지 시안에 `혼합제제(산도조절제 2종)`처럼 묶거나 여러 하위 성분들을 몰래 빼와서 묶어 은폐(블랙박스화)한 경우 명백한 위법(🚨부적합) 처리하십시오.

🔥 **Rule 36. [주의사항 오탈자 스캔]**
   - 각 구역별 텍스트 스캔 및 띄어쓰기 비교.

✅ **Rule 37. [법적 서류 우선 고려]**
   - Rule 35 예외 우선 고려.

🔥 **Rule 38. [알레르기 22종 하드코딩 및 교차오염 완벽 검증 룰]**
   - 알레르기 판정 시 오직 **[한국 식약처 지정 22종]**에 대해서만 검증하십시오. 아몬드, 캐슈넛 등 CODEX 기준 외국 알레르기는 한국법상 무시하십시오.

🔥 **Rule 39. [동명 원료 및 식품유형 종속성 분리 룰]**
   - 명칭이 같아도 [식품유형]이 다르면 분리 표기.

🔥 **Rule 40. [열량 표기 및 애트워터 계수 합법성 (유연성 패치)]**
   - 식약처 고시에 따라 열량은 "계산된 값을 그대로 표시하거나", "가장 가까운 5kcal 단위로 표시"하는 것 모두가 합법입니다. 실측 반올림 수치와 달라도 120% 이내면 합법(✅).

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - 기준치 역산 대조 필수 (열량, 트랜스지방 제외).

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 최종 완제품 기준 데이터만 사용.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독 어려우면 임의 판정 금지.

🔥 **Rule 44. [🌟 식품첨가물(혼합제제) 표기 방식의 자율성 보장 (1:1 묶음 및 1:N 해체 모두 합법)]**
   - 1. **[1:1 묶음 표기 합법]**: `혼합제제명(하위성분1, 하위성분2)` 껍데기를 유지해서 묶어 적었다면 완벽한 합법(✅).
   - 2. **[1:N 해체 전개 합법]**: 껍데기를 부수고 `하위성분1`, `하위성분2`로 낱낱이 흩뿌려 적었더라도 이 역시 완벽한 합법(✅).
   - ⭐ **[혼합제제 5% 룰 면제 불가]**: 해체된 하위 성분은 5% 미만 면제 룰(Rule 5)을 무시하고 표 4, 5, 6 강제 점검.

🔥 **Rule 45. [선택적 누락/마케팅 수식어 생략 허용]**
   - 서류의 '유기농', '천연' 등의 마케팅 수식어를 패키지 시안에서 생략(선택적 누락)하고 일반 명칭으로 표기하는 것은 완벽한 합법(✅).

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
   - 제품명이나 패키지에 "무당", "당 ZERO" 등의 강조 표시를 하면서 단맛을 내기 위해 감미료를 사용한 경우에는, 해당 강조 표시 주변에 반드시 **"감미료 함유"**를 병기해야 합니다. 또한, 영양정보표 바깥에 기재된 모든 영양소 텍스트는 예외 없이 영양강조표시로 간주하여 컷오프(%)를 검증하십시오.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 제품명에 농수산물이 쓰이면 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성]**
   - 단일 원료 2개국 병기 시 비율 생략 확인.

🔥 **Rule 55. [영양성분 반올림 강박 금지 및 '보수적 표기(안전율)' 합법성 룰]**
   - 제조사가 공장 생산 편차를 고려하여 상한선(120%) 성분을 살짝 높게 적거나, 하한선(80%) 성분을 살짝 낮게 적는 '보수적 표기(안전 마진)'는 실무적 정석이며 완벽한 합법입니다. 1g 단위 식약처 단위에 안 떨어지더라도 허용 범위 안에 들어온다면 절대 부적합 처리하지 마십시오.

🔥 **Rule 56. [HACCP 인증 마크 제품유형별 교차 검증 (멸균유 포함)]**
   - [공용 허용]: "안전관리인증" 텍스트 합법.
   - [일반 식품]: "식품안전관리인증" 합법.
   - [축산물]: "축산물안전관리인증" 합법. 식품인데 축산물이라고 적으면 🚨부적합.

🔥 **Rule 57. [세트포장 수량 강제 룰]**
   - 박스 번호에 "수량(X입)" 기재 확인.

🔥 **Rule 58. [함량 생략 합법성]**
   - 앞면에 함량(%) 명시 시 뒷면 생략 합법(✅).

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 패키지 어디에든 1399 등이 하나라도 존재하면 합법(✅).

🔥 **Rule 60. [복합원재료 원물 함량 기재 면제 룰]**
   - 괄호 안에 '고형분(%)' 명시 시 배합함량 기재 강요 면제.

🔥 **Rule 61. [국산 가공 예외 룰]**
   - 괄호 없이 곧바로 (국산) 표기 합법.

🔥 **Rule 62. [보관상태 의무 표시 및 멸균 예외 룰]**
   - 멸균팩 등 상온 보관 제품은 냉장 표시 의무 없음.

🔥 **Rule 63. [190mL 전용 질소충전 양방향 확인 룰]**
   - 190mL 팩은 미드팩은 필수, 무균팩은 삭제. 둘 다 실무자 확인 요망(⚠️) 처리.

🔥 **Rule 64. [원물 기만표시 검증]**
   - 강조 비율이 추출액 비율이면 기만(🚨).

🔥 **Rule 65. [내부 식별 코드 생략 합법성]**
   - -2 등 내부 코드는 생략 합법.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 복붙 적발]**
   - 박스 시안에 낱팩 1개 용량을 복붙하면 치명적 에러(🚨). '1개당' 기준 명시 필수.

🔥 **Rule 70. [내/외포장 100% 일치 강제 및 내용량/타이포그래피 예외 룰]**
   - 내포장(팩)과 외포장(박스) 대조 시 '내용량 및 열량' 표기 방식은 전체 수량 명시로 예외 인정.
   - 마침표, 띄어쓰기, 아래첨자 동등성 등 단순 타이포그래피 차이도 합법(✅) 인정.

🔥 **Rule 71. [강조 폰트 크기 규정]**
   - 원료 함량 14pt 육안 확인 알림.

🔥 **Rule 72. ['조리예/이미지 사진' 점검]**
   - 연출 사진 텍스트 스캔.

🔥 **Rule 73. [세부 재질 검증]**
   - 세부 재질 확인.

🔥 **Rule 74. [액상 음료 주의문구 식품유형 종속성 룰]**
   - 식품유형이 '음료류'일 경우에만 개봉 후 주의문구 스캔. 우유류는 적용 대상 아님.

🔥 **Rule 75. [CS 클레임 방어용 주의문구 세트]**
   - 침전물, 용기 팽창 등 문구 스캔.

🔥 **Rule 76. [OEM 업소명 타이틀 강제 스캔]**
   - 유통전문판매원 필수.

🔥 **Rule 77. [식품유형별 법정 의무 주의사항 동적(Dynamic) 스캔 룰]**
   - 고정된 문구만 찾지 말고 업로드된 법령을 기반으로 해당 제품유형 전용 문구(아스파탐 등)를 동적으로 스캔.

🔥 **Rule 78. [특수의료용도식품 타겟 광고 문구 합법성 검증]**
   - 환자 타겟 영양공급 강조는 무조건 합법(✅).

🔥 **Rule 79. [열량 구성비(%) 정밀 역산 룰]**
   - 식이섬유를 고려한 열량 구성비 정밀 역산 수행.

🔥 **Rule 80. [선물세트 박스(외포장) 영양정보 레이아웃 강제]**
   - 박스 영양정보표 상단 레이아웃 준수 검증.

🔥 **Rule 81. [영양표시 하단 면책 문구 토시 대조]**
   - 기호 100% 일치 확인.

🔥 **Rule 82. [영양소 법정 단위 엄격 검증]**
   - 비타민 단위 등 특수기호 대조.

🔥 **Rule 83. [영양성분 % 병기 강제 원칙]**
   - 기준치 존재 성분 옆에 비율 병기 필수.

🔥 **Rule 84. [유기농/친환경 단어 원천 차단 룰]**
   - 인증 마크 필수 확인.

🔥 **Rule 85. [식품첨가물 공전 명칭 사수 및 기호 창조 절대 금지]**
   - 명칭 축약 엄격 금지.

🔥 **Rule 86. [국가 공인 인증 도안 기만 및 텍스트 편법 규제 룰]**
   - 도안 없는 텍스트 편법 적발.

🔥 **Rule 87. [특정균 강조 표시 및 균수 분리 기재 합법성 룰]**
   - 배합함량과 균수 분리 표기 합법.

🔥 **Rule 88. [100% 강조표시 기만 검증 룰]**
   - **[원재료 100% 금지]**: 서류에 첨가물이 0.01%라도 있는데 "OO 100%" 강조 시 소비자 기만(🚨).
   - **[원산지 100% 합법]**: "국산 OO 100%" 등 원산지 수식은 첨가물이 섞여 있어도 합법(✅).

🔥 **Rule 89. [국내 제조 가공품 원료의 원산지 이중 표기 규정]**
   - 수입 원물을 국내에서 가공한 원료(Rank B 1~3위 타겟)는 반드시 `원료명(원료명: 국가명)` 형태로 괄호 안에 원료명을 한 번 더 명시하고 원산지를 적어야 합법(✅).

🔥 **Rule 90. [범용 명칭 치환(유연한 맵핑) 룰]**
   - 서류의 시럽/페이스트 등이 시안에서 당류가공품, 올리고당, 혼합제제 등 범용 명칭으로 묶인 것은 실무상 합법이므로 유연하게 맵핑(✅).

🔥 **Rule 91. ['혼합제제' 명칭 단축 표기 절대 합법성]**
   - 식품첨가물혼합제제 등을 단순히 '혼합제제'로 줄여 쓰는 것은 완벽한 합법(✅).

🔥 **Rule 92. [부분 캡처 이미지 한계에 따른 누락 항목 조건부 보류(⚠️) 룰]**
   - 업로드된 이미지가 크롭된 경우, 반품처/상담실 등 행정정보가 잘려 안 보일 수 있으니 🚨부적합 처리하지 말고 ⚠️(확인 요망)으로 유연하게 판정.
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

ALL_RULES_NUMBERS = list(range(1, 93))
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
    
    # ⭐ 상단 고정 헤더 영역 (현재 검토 중인 제품명 표시)
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V326.00 - 점진적 릴레이 탐색 적용본)")
    
    current_product = st.session_state.get("current_product_name", "지정되지 않음")
    st.markdown(f"#### 🟢 **현재 검토 중인 제품:** `{current_product}`")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        st.markdown("#### 🏷️ 작업 식별용 정보")
        product_input = st.text_input("현재 검토 중인 제품명 (멀티태스킹 방지용)", "예: 세브란스케어 당밸런스 150")
        if product_input:
            st.session_state["current_product_name"] = product_input

        with st.expander("⚙️ 고급 설정 (수동 텍스트 입력)", expanded=False):
            st.info("💡 텍스트가 너무 빽빽해서 AI가 숫자를 빼먹는다면, 원본 텍스트를 직접 복붙해 주세요.")
            st.session_state["manual_target"] = st.text_area("📦 타겟(박스) 원재료명/영양정보 직접 입력", height=100)
            st.session_state["manual_compare"] = st.text_area("🧃 비교용(팩) 원재료명/영양정보 직접 입력", height=100)

        st.markdown("#### 📌 기본 검토 조건")
        product_type = st.radio("1. 식품유형", ("일반식품 (음료류, 두유류 등 - 액상 음료 기준 적용)", "특수의료용도식품 / 환자식", "축산물 (유가공품: 우유, 가공유, 멸균유 등 - 강화우유 포함)"))
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
        if st.button("🚀 전체 시스템 파일 연동 및 캐싱 (Vision API 가동)"):
            with st.spinner("파일을 구글 시스템에 연동하고 메모리에 캐싱(Caching) 중입니다..."):
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
                    
                    try:
                        if "qc_cache_name" in st.session_state and st.session_state["qc_cache_name"]:
                            try:
                                genai.caching.CachedContent.get(st.session_state["qc_cache_name"]).delete()
                            except:
                                pass
                        
                        cache_contents = content + [f"\n\n========================================\n[식품 QC 마스터 통합 룰북 원문]\n{RULE_BOOK_FULL}"]
                        cache = genai.caching.CachedContent.create(
                            model=f"models/{MODEL_NAME}",
                            display_name="food_qc_cache",
                            system_instruction=SYSTEM_PROMPT,
                            contents=cache_contents,
                            ttl=datetime.timedelta(minutes=120) 
                        )
                        st.session_state["qc_cache_name"] = cache.name
                        st.success("✅ 파일 등록 및 구글 서버 캐싱 완료! (향후 2시간 동안 API 비용 90% 절감)")
                    except Exception as e:
                        error_msg = str(e)
                        st.session_state["qc_cache_name"] = None
                        
                        if "32768" in error_msg or "too small" in error_msg.lower():
                            st.success("✅ 파일 등록 완료! (데이터가 가벼워 캐싱 대기 없이 초고속 일반 모드로 진행합니다 ⚡)")
                        else:
                            st.warning(f"⚠️ 캐싱을 건너뛰고 일반 모드로 진행합니다. (사유: {error_msg})")

    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_missions_list: list = None):
        if not st.session_state["uploaded_content"]:
            st.warning("🚨 좌측 사이드바 하단의 [🚀 전체 시스템 파일 연동] 버튼을 먼저 눌러주세요.")
            return None

        use_cache = False
        cache_name = st.session_state.get("qc_cache_name")
        if cache_name:
            try:
                cache = genai.caching.CachedContent.get(cache_name)
                model_pro = genai.GenerativeModel.from_cached_content(cached_content=cache)
                use_cache = True
            except:
                model_pro = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        else:
            model_pro = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)

        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        def get_payload(prompt_text):
            if use_cache:
                return [prompt_text]
            else:
                return st.session_state["uploaded_content"] + [f"========================================\n[식품 QC 마스터 통합 룰북 원문]\n{RULE_BOOK_FULL}"] + [prompt_text]

        extracted_text_combined = ""
        pass18_result = "맞춤법 전용 스캔 생략됨 (본 탭은 추출 미션 없음)"
        verified_text = ""

        if extract_missions_list:
            extracted_results = []
            for i, mission in enumerate(extract_missions_list):
                pass1_prompt = f"""
[PASS 1 - 텍스트 단일 추출 미션]
🎯 [현재 타겟 미션]: {mission}

🔥 [절대 생략 금지 원칙]:
어떠한 경우에도 텍스트를 임의로 요약하거나 `(...)`, `...`, `이하 생략` 등의 단어를 사용하여 생략하지 마십시오. 글자 수가 아무리 많더라도 100% 끝까지 풀스펠링으로 타이핑해야 합니다. (말줄임표 사용 시 치명적인 시스템 오류로 간주합니다.)
"""
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        pass1_response = model_pro.generate_content(
                            get_payload(pass1_prompt), 
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
[PASS 1.5 - 추출 텍스트 종합 자체검증 및 🧹 OCR 환각(노이즈) 자동 정제 명령]
당신은 단순한 텍스트 결합기가 아니라 '최고급 AI 데이터 정제 필터'입니다.
아래 추출된 텍스트(시안에서 읽어온 글자)에는 이미지 인식 한계로 인한 기계적 OCR 노이즈가 섞여 있을 수 있습니다.
(예: '알파갈락[토시다아제', '변성전1분', '비[타민B12', '비타민B,질산염' 등 단어 중간의 뜬금없는 기호나 숫자 난입)

함께 업로드된 [마스터 서류(배합비/한글라벨)]의 완벽 문맥을 바탕으로, 시안 텍스트에 낀 명백한 OCR 노이즈를 스스로 찾아내어 원래의 깨끗한 단어로 자동 교정(Auto-Correction)하십시오.
디자이너의 오타가 아니라 기계의 시력 문제로 발생한 찌꺼기(기호, 숫자)를 지우개로 지워 깨끗한 원본 상태로 복원하는 것이 핵심입니다.

[추출된 원본 텍스트]
{extracted_text_combined}

교정이 완료된 최종 확정 텍스트만 출력하십시오. 절대 내용을 축약하거나 말줄임표(...)를 쓰지 마십시오.
"""
            verified_text = extracted_text_combined
            for attempt in range(max_retries):
                try:
                    pass15_response = model_pro.generate_content(
                        get_payload(pass15_prompt), 
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

            pass18_prompt = f"""
[PASS 1.8 - 맞춤법 및 띄어쓰기 전용 스캐너]
지금부터 당신은 국립국어원 맞춤법 검사기입니다. 앞서 추출된 텍스트 내용 전체를 픽셀 단위로 스캔하여 오직 '띄어쓰기 오류', '오탈자', '부자연스러운 접미사(예: 특성 상 -> 특성상, 있으니음용 -> 있으니 음용)'만을 족집게처럼 찾아내십시오. 
식품 법규 룰 대조나 적합/부적합 판정 등은 절대 금지합니다.
⭐ [절대 금지 명령]: 어떠한 경우에도 '부적합', '위법', '규정 위반' 같은 법률적/규정적 단어를 사용하지 마십시오. 당신이 법적 판단을 내리는 순간 치명적 에러로 간주합니다.

🔥 [오탈자와 띄어쓰기 분리 출력 강제]:
발견된 내역을 반드시 다음 두 가지 카테고리로 엄격히 분리하여 [원문] -> [수정 권장] 리스트 형태로 출력하십시오. 발견된 사항이 없으면 '특이사항 없음'을 출력하십시오.
1. 🔠 [오탈자 스캔 결과] (명백히 틀린 글자)
2. 📏 [띄어쓰기 스캔 결과] (붙여쓰거나 띄어써야 할 곳)
"""
            for attempt in range(max_retries):
                try:
                    model_flash = genai.GenerativeModel(MODEL_NAME_FLASH, system_instruction=SYSTEM_PROMPT)
                    pass18_response = model_flash.generate_content(
                        [pass15_prompt + "\n\n" + pass18_prompt],
                        generation_config=generation_config, 
                        safety_settings=safety_settings, 
                        request_options={"timeout": 600}
                    )
                    pass18_result = get_safe_text(pass18_response)
                    break
                except Exception as e:
                    if "504" in str(e) or "Deadline" in str(e) or "503" in str(e):
                        if attempt < max_retries - 1:
                            time.sleep(10)
                            continue
                    pass18_result = f"🚨 Pass 1.8(맞춤법 봇) 에러: {e}"
                    break

        pass2_context = ""
        if extract_missions_list:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}

[맞춤법/오탈자 교정 데이터 - Pass 1.8 맞춤법 전용 봇 결과]
{pass18_result}
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

🔥 [영역 침범 절대 금지 및 강제 종료 명령] 🔥
당신은 현재 해당 탭의 미션만 수행하는 국소적 봇입니다. 절대로 지시받지 않은 다른 구역(예: 1번 탭 검사 중인데 2,3,4번 탭 내용)의 표를 임의로 창조하여 덧붙이지 마십시오. 
오직 아래에 제시된 [출력 양식] 표 딱 하나만 채워 넣고, 그 즉시 출력을 강제 종료(Stop)하십시오.

🔥 [최종 출력 양식 및 절대 강제 지침] 🔥
아래 제시된 [출력 양식]의 뼈대(제목, 표 헤더 등)만 그대로 복사하여 내용을 채워 넣으십시오.
(주의: 뼈대에 없는 부연 설명이나, 룰에 대한 텍스트는 출력 화면에 보이지 않도록 절대 출력하지 마십시오. 오직 표와 결과만 깔끔하게 출력하십시오.)

🔥 [절대 금지어 및 생략 방어 족쇄]: 
표 내부를 작성할 때 절대 `...`, `(...)`, `생략`, `이하 생략`, `등` 과 같은 기호나 단어를 사용하여 텍스트를 임의로 축약하지 마십시오. 
원재료가 100개이든 영양성분이 50개이든 첫 번째부터 마지막까지 단 하나도 빼놓지 말고 100% 전부 표에 나열하십시오. 표가 중간에 끊기거나 말줄임표가 발견되면 치명적인 시스템 오류로 간주됩니다.

🔥 [가독성 향상 HTML 강제 명령 (매우 중요!)]:
판정 및 사유 칼럼의 텍스트가 줄글로 뭉쳐지면 실무자가 읽기 매우 힘듭니다.
반드시 **<br>** 태그를 적극 사용하여 줄바꿈을 하고, **볼드체**를 활용하여 대시보드처럼 직관적으로 요약 작성하십시오.

🔥 [사유 작성 규칙 (중복 금지)]: 
표의 '사유' 칼럼 안에 '✅ 적합', '🚨 부적합' 같은 판정 단어나 이모지를 중복해서 쓰지 마십시오. 판정 결과는 오직 우측 끝의 '판정' 칼럼에만 단독으로 기재하십시오.

[출력 양식]
{judgment_prompt}
"""
        for attempt in range(3):
            try:
                pass2_response = model_pro.generate_content(
                    get_payload(pass2_prompt), 
                    generation_config=generation_config, 
                    safety_settings=safety_settings, 
                    request_options={"timeout": 600}
                )
                final_clean_text = get_safe_text(pass2_response)

                if extract_missions_list:
                    return f"<clean_view>\n{final_clean_text}\n</clean_view>\n<pass1_log>\n{extracted_text_combined}\n</pass1_log>\n<pass15_log>\n{verified_text}\n</pass15_log>\n<pass18_log>\n{pass18_result}\n</pass18_log>"
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
            
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        
        dynamic_prompt = f"""
        [제품유형]: {product_type}\n[검토모드]: {inspection_mode}\n[우리 공장 알레르기 마스터 목록]: {factory_allergens}
        ========================================\n{prompt_text}
        """
        
        cache_name = st.session_state.get("qc_cache_name")
        if cache_name:
            try:
                cache = genai.caching.CachedContent.get(cache_name)
                model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                payload = [dynamic_prompt]
            except:
                model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                payload = st.session_state["uploaded_content"] + [f"[식품 QC 마스터 룰북]\n{RULE_BOOK_FULL}"] + [dynamic_prompt]
        else:
            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            payload = st.session_state["uploaded_content"] + [f"[식품 QC 마스터 룰북]\n{RULE_BOOK_FULL}"] + [dynamic_prompt]
            
        try:
            response = model.generate_content(payload, generation_config=generation_config)
            return fix_markdown_table(get_safe_text(response))
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    def display_result(result, tab_name=""):
        if not result: return
        
        clean_match = re.search(r'<clean_view>(.*?)</clean_view>', result, re.DOTALL)
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)
        pass18_match = re.search(r'<pass18_log>(.*?)</pass18_log>', result, re.DOTALL)

        if pass1_match or pass15_match or pass18_match:
            with st.expander(f"🕵️‍♂️ [시스템 로그실] {tab_name} Pass 연산 원본 추출 데이터 보기 (필요시 클릭)"):
                if pass18_match:
                    st.info("🎯 Pass 1.8 맞춤법 전용 스캐너 (초고속 Flash 모델 구동 완료)")
                    st.code(pass18_match.group(1).strip())
                if pass15_match:
                    st.info("✅ Pass 1.5 자체 복정 및 OCR 노이즈 정제 완료본")
                    st.code(pass15_match.group(1).strip())
                if pass1_match:
                    st.text("📋 Pass 1 분할 미션 원본 로그")
                    st.code(pass1_match.group(1).strip())
            st.markdown("---")

        if clean_match:
            st.markdown(fix_markdown_table(clean_match.group(1).strip()), unsafe_allow_html=True)
        else:
            st.markdown(fix_markdown_table(result), unsafe_allow_html=True)

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "🤖 5️⃣ AI 법률 스캔", "📊 6️⃣ 종합 보고서"])

    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【정밀 법리 검수 매트릭스 연산 중...】"):
                # ⭐ [V326.00 패치] 추출 격리 + 점진적 릴레이 탐색 미션 적용
                missions = [
                    "⭐ [정밀 추출 명령]: 텍스트와 영양성분 수치 추출은 반드시 '주표시면(앞면)' 이미지에서만 수행하여 다른 면의 글자가 섞이는 환각을 방지하십시오.",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 앞면에 강조된 특정 영양소의 '% 기준치'를 교차 추출.",
                    "업로드된 서류에서 주표시면에 강조된 성분의 투입량(%)과 실측값(mg/g) 추출.",
                    "⭐ [점진적 탐색 및 룰 검증 명령 (인간의 시선 흐름)]: '국가 공인 인증 도안(HACCP 등)', '유기농 마크', '당 ZERO 등 영양강조 뱃지'를 검증할 때, 먼저 주표시면(앞면)을 확인하십시오.",
                    "▶ 주표시면에 없다면? 즉시 '해당 없음' 처리하지 말고, 함께 업로드된 다른 면(정보표시면, 기타면 등)의 이미지들을 순차적으로 스캔하십시오.",
                    "▶ 타 면에서 발견 시: '주표시면에는 없으나 측면(또는 후면)에서 HACCP 마크 확인됨'이라고 적고, 룰(Rule 56 등)에 따라 공식 명칭이 적법한지 끝까지 검사하여 ✅적합/🚨부적합을 판정하십시오.",
                    "▶ 모든 면에서 미발견 시: 패키지 전체 이미지를 다 뒤져도 없을 경우에만 비로소 '패키지 전체 스캔 결과 해당 마케팅/인증 내역 없음'으로 사유를 적고 ✅ 적합(해당 없음) 처리하십시오."
                ]
                judgment_prompt = """## 1️⃣ [주표시면 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 상세 사유 (오탈자 무관용, <br> 태그로 줄바꿈 필수) | 판정 |
| :--- | :--- | :--- | :--- |
| **제품명 및 특정 원료(특정균) 강조 기준** | [Rule 9, 53, 87] | | |
| **강조 폰트 크기** | [Rule 71] | | |
| **조리예/이미지 사진 표기** | [Rule 72] | | |
| **보관상태(상온/냉동/냉장) 명시** | [Rule 62] | | |
| **세트포장 앞면 총내용량/열량** | [Rule 3] | | |
| **다포장 낱팩 복붙 여부** | [Rule 68] | | |
| **원액/추출물 고형분 병기** | [Rule 50] | | |
| **영양강조 컷오프(4대 조건)** | [Rule 21, 52] | (※ 100g, 100mL, 100kcal, 1회섭취량 중 하나라도 충족하는 수식으로 증명할 것) | |
| **당류 강조 및 감미료 병기 의무** | [Rule 21, 52] | (※ '당 ZERO' 등 당류 강조 시 감미료 함유 표기 여부. 강조 없으면 '해당 없음' 기재) | |
| **국가 공인 인증 도안 마케팅** | [Rule 86] | | |
| **유기농/친환경 마크 검증** | [Rule 84] | | |
| ⭐ **오탈자 스캔 (명백한 글자 오류)** | 전수 검사 | (Pass 1.8의 🔠 오탈자 결과만 분리해서 기재) | |
| ⭐ **띄어쓰기 스캔 (간격 오류)** | 전수 검사 | (Pass 1.8의 📏 띄어쓰기 결과만 분리해서 기재) | |
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
                    "시안(주표시면/정보표시면)에 기재된 원재료명, 알레르기 유발물질, 교차오염 주의문구, 행정 정보(제조원 등)를 모두 추출하십시오. (절대 말줄임표(...) 사용 금지, 모든 원재료명을 끝까지 출력할 것)",
                    "시안에 기재된 원재료명 중 '식품첨가물'을 추출한 뒤, 하드코딩된 DB(표 4, 5, 6)와 대조하여 소속을 명확히 지정하십시오.",
                    "⭐ [절대 미션: 개별 단위 쪼개기 및 괄호 보존 법칙]: 추출한 원재료명을 쉼표(,)를 기준으로 개별 리스트로 쪼개되, **괄호 `()`나 대괄호 `[]` 안에 있는 쉼표는 절대 쪼개지 말고 한 덩어리로 무조건 유지하십시오.** 부모 명칭에 하위 성분을 괄호로 다 적었다면 (예: `혼합제제(A, B)`), 밑에 하위 성분(A, B)을 위한 개별 행을 중복해서 파생 생성하지 마십시오. 시안 텍스트를 `[...]`로 절대 축약하지 말고 100% 풀스펠링으로 전수 타이핑하십시오."
                ]
                
                if "박스" in ins_mode:
                    missions.append("⭐ [내외포장 1:1 분할 매칭 강제명령]: 타겟(박스) 시안과 비교용(팩) 시안의 원재료명 전체 텍스트를 표의 한 칸(행)에 통째로 때려 넣는 행위를 절대 금지합니다. 반드시 쉼표(,)를 기준으로 각각의 개별 원재료를 쪼개어, 표의 1개 행(Row) 당 딱 1개의 원재료만 1:1로 나란히 매칭되도록 길게 표를 작성하십시오.")
                
                tab2_special_rules = RULES_TAB2 + """
                \n\n🔥 [Tab 2 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)] 🔥
                1. [마스터표 강제 완성 및 절대 생략 금지]: 서류나 시안의 원재료 데이터가 아무리 길어도 표 작성 시 절대로 중간에 끊거나 `(...)`, `...`, `생략` 등의 단어를 사용하여 요약하지 마십시오. 원본 데이터의 1행부터 마지막 행까지 100% 전수 조사하여 끝까지 표를 완성하십시오. 이 지시를 어기면 치명적 에러로 간주됩니다.
                2. [사전 연산 강제 출력]: 표를 그리기 전에 반드시 `## 🧠 [사전 연산: 원산지 Rank B 및 혼합제제 해체 알고리즘]` 블록을 작성하여 스스로 논리를 확정 지은 후 표를 작성하십시오.
                3. ⭐ [1:N 해체 전개 합법성 인정 방패]: 표를 작성할 때 서류의 '혼합제제' 1개가 시안의 여러 개별 하위 성분(비타민C, 덱스트린 등)으로 쪼개져 매칭되는 것은 Rule 44에 따른 완벽한 합법입니다. 각 줄을 대조할 때 '다른 성분을 누락하고 일부만 표기했다'고 지적하는 바보 같은 짓을 절대 하지 마십시오. 개별 전개된 모든 성분에 대해 "✅ 적합 (Rule 44에 따른 합법적인 1:N 해체 전개)"라고 기재하십시오.
                4. [마스터 DB 원본 복사]: 서류에서 데이터를 추출할 때 오직 서류 원문에 있는 [식품유형, 제품명, 한글표시사항, 원산지, 알러지유발물질] 5개 정보만 그대로 복사하여 2-1 마스터표를 작성하십시오.
                5. [순서 역전 정밀 검증 (Rank A 적용)]: 모든 원료의 절대 배합비 순위(Rank A) 중 2% 이상인 원료의 순위를 대조하고, 서류와 시안의 순서가 역전되었다면 🚨부적합 처리하십시오. (단, 배합비 없으면 동적 추론 허용)
                6. ⭐ [표(Table) 레이아웃 붕괴 방어 및 가독성 강제]: 원재료명이나 사유 텍스트 내부에 파이프 기호(`|`)가 포함되어 있으면 표가 깨집니다. 파이프는 슬래시(`/`)로 대체하십시오. 사유가 길어질 경우 하나의 덩어리(줄글)로 쓰지 말고, 반드시 `<br>` 태그를 사용하여 핵심 내용별로 줄바꿈을 하여 직관적으로 읽기 편하게 작성하십시오.
                """

                judgment_prompt = "## 🧠 [사전 연산: 원산지 Rank B 및 혼합제제 해체 알고리즘]\n"
                judgment_prompt += "(AI는 아래 5단계를 단답형으로 100% 명확히 작성하여 논리를 확정한 후 대조 표를 작성할 것)\n"
                judgment_prompt += "1. **[Rank B 제외 대상 필터링]**: 마스터표 원료 중 [정제수, 당류가공품, 주정, 식품첨가물] 카테고리에 해당하여 원산지 의무가 완전히 면제되는 원료 목록:\n   - [삭제 원료명]: \n"
                judgment_prompt += "2. **[Rank B Top 3 확정]**: 위 대상을 제외하고 남은 실질 원료들의 배합비율 기준 상위 1, 2, 3위 원료 (배합비율 없으면 시안 나열 순서대로 강제 추론):\n   - 1위: [ ], 2위: [ ], 3위: [ ]\n"
                judgment_prompt += "3. ⭐ **[Rule 1: 98% 컷오프 예외 판정]**: Rank B 1순위 원료의 배합비가 98% 이상인가? (98% 이상일 경우 '2위 및 3위 원료 원산지 표기 면제 확정'이라고 명확히 락온(Lock-on) 할 것):\n"
                judgment_prompt += "4. **[Rule 89 타겟 락온]**: 국내 가공품 이중 표기(Rule 89) 검사를 수행할 타겟 (오직 위 2번의 Rank B 1~3위 원료 중에서만 선정. 단, 98% 예외 룰 적용 시 1위만 타겟팅. 당류가공품 등에는 절대 적용 불가):\n   - [적용 대상 원료]: \n"
                judgment_prompt += "5. **[복합원재료 vs 혼합제제 전개 라우팅]**: 서류상 혼합물들에 대하여 전개/면제 여부 사전 확정:\n   - [전개 면제 합법 (배합비 5% 미만인 일반 복합원재료)]: \n   - [전개 필수 (식품유형이 '혼합제제'이므로 배합비율 무관하게 Rule 44 적용)]: \n\n"

                step_offset = 1 if has_any_doc else 0

                if has_any_doc:
                    if "무더기" in doc_mode:
                        missions.append("업로드된 '개별 원료 한글라벨 무더기' 데이터를 분석하여 내부적으로 [마스터 배합비 데이터]를 합성하십시오.")
                    else:
                        missions.append("⭐ [절대 미션: 마스터표 100% 전수 복사]: 업로드된 증빙 서류(배합비 엑셀/PDF 등)의 첫 행부터 마지막 행까지 단 한 줄도 생략하지 말고 100% 전수 추출하여 5개 항목(식품유형, 제품명, 한글표시사항, 원산지, 알러지)을 복사하십시오. (서류에 '영양강화제 3종' 등 별도 그룹이 있다면 다른 원료와 섞지 말고 있는 그대로 독립적으로 추출할 것)")
                    
                    judgment_prompt += "## 2️⃣-1. [서류 기반 마스터 원재료 DB]\n"
                    judgment_prompt += "| 식품유형 | 원재료의 제품명 | 원재료의 한글표시사항 | 원산지 | 알러지유발물질 |\n|---|---|---|---|---|\n\n"

                if "박스" in ins_mode:
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [박스(타겟) vs 팩(비교용) 내외포장 원재료명 100% 일치 대조 매트릭스]\n"
                    judgment_prompt += "| 타겟(박스) 표기 개별 원재료명 (행정정보 제외) | 비교용(팩) 표기 개별 원재료명 | 대조 상세 사유 (<br> 태그 활용, 절대 판정 단어 중복 기재 금지) | 판정 |\n|---|---|---|---|\n\n"
                    judgment_prompt += f"### 🚨 [팩 시안 기준 최종 누락 정밀 검증]\n- (누락 원료 상세 기재 또는 '✅ 팩 시안 대비 통째로 누락된 원료 없음')\n\n"

                if has_any_doc:
                    target_name = "박스 시안" if "박스" in ins_mode else "시안"
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [마스터 서류 vs {target_name} 법적 대조 매트릭스]\n"
                    judgment_prompt += "| 시안 표기 개별 원재료명 (생략 절대 금지) | 매칭된 서류 원료명 | ⚖️ 배합비(%) 및 순위 | 🌍 원산지 룰 검증 | 상세 사유 (<br> 태그 필수, 절대 판정 단어 중복 금지) | 판정 |\n|---|---|---|---|---|---|\n\n"
                    judgment_prompt += f"### 🚨 [서류 기준 최종 누락 정밀 검증]\n- (누락 원료 상세 기재 또는 '✅ 서류상 누락된 원료 없음')\n\n"

                if not has_any_doc and "박스" not in ins_mode:
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [시안 표기 원재료명 리스트]\n(※ 증빙 서류 미제출로 서류 대조 및 원산지 검증 불가)\n\n"
                    step_offset += 1
                    judgment_prompt += f"## 2️⃣-{step_offset}. [자체 형식 검토 매트릭스]\n| 시안 표기 개별 원재료명 (생략 금지) | 형식 검토 사유 (<br> 태그 사용) | 판정 |\n|---|---|---|\n\n"

                num_add = step_offset + 1
                num_mix = num_add + 1
                num_alg = num_add + 2
                num_adm = num_add + 3
                num_typ = num_add + 4

                judgment_prompt += f"### 🚨 2️⃣-{num_add}. [식품첨가물 범용 형식주의 정밀 검증]\n- **[명칭 축약 및 용도 표시 검사 결과]**:\n- **[임의 기호 창조 검사 결과]**:\n\n"
                judgment_prompt += f"## ⚖️ 2️⃣-{num_mix}. [배합비 2% 이상 원료 전개 순서 정밀 검증 (Rule 34)]\n- **[서류상 2% 이상 원료 순서 (배합비 % 포함하여 100% 상세 기재)]**:\n- **[시안에 적힌 실제 나열 순서]**:\n- **[최종 판정 및 사유]**:\n\n"
                judgment_prompt += f"## 🧮 2️⃣-{num_alg}. [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38)]\n- **[공장 마스터 목록]**:\n- **[직접 투입된 알레르기]**:\n- **[도출된 교차오염 정답지]**:\n- **[시안 표기 주의문구]**:\n- **[최종 판정 및 사유]**:\n\n"
                judgment_prompt += f"## 🏛️ 2️⃣-{num_adm}. [행정 정보 교차 검증]\n- ⭐ [Rule 76] 유통판매원/판매원 타이틀 강제 확인:\n\n"
                judgment_prompt += f"## 🔍 2️⃣-{num_typ}. [오탈자 및 띄어쓰기 스캔 (전수 검사)]\n- 🔠 **[오탈자 스캔 결과]**: (Pass 1.8 바탕 오탈자만 기재)\n- 📏 **[띄어쓰기 스캔 결과]**: (Pass 1.8 바탕 띄어쓰기만 기재)\n"

                st.session_state["result_tab2"] = run_qc_3pass(tab2_special_rules, judgment_prompt, missions)
        
        display_result(st.session_state["result_tab2"], "정보표시면")

    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【영양성분표 수치 환산 및 교차 검증 중...】"):
                has_any_doc = st.session_state.get("has_recipe", False) or st.session_state.get("has_labels", False)
                ins_mode = st.session_state.get("inspection_mode_state", "단품(팩/단일포장) 기본 검토")

                missions = [
                    "⭐ **[영양정보표 2단/다단 레이아웃 100% 전수 스캔 강제 명령]**: 영양정보표 이미지를 스캔할 때 중간에 표가 2단(좌/우)으로 나뉘거나 하단에 수십 개의 미량 영양소(인, 요오드, 비타민 등)가 나열되어 있다면, 절대 중간에 읽기를 멈추지 마십시오. 이미지의 최하단 픽셀까지 샅샅이 스캔하여 시안에 적힌 30~50개의 모든 영양소 텍스트를 단 하나도 빠짐없이 100% 추출해 내십시오. (말줄임표 절대 금지)",
                    "비교용(팩) 시안이 있다면 영양정보표 내부 수치와 바깥 문구 전부 추출.",
                    "⭐ **[다중 성적서 100% 매칭 명령]**: 업로드된 여러 장의 시험성적서(비타민, 미네랄, 아미노산 등)를 모두 뒤져서, 시안에 적힌 영양소들의 실측값을 반드시 찾아내어 끝까지 준비해 두십시오.",
                    "⭐ **[OCR 소수점 오독 방지 절대 명령]**: 영양성분표의 소수점(예: 0.28)이나 아주 작은 숫자를 추출할 때 마지막 자리 숫자가 누락되지 않도록 픽셀 단위로 두 번, 세 번 의심하고 철저하게 정확히 추출하십시오."
                ]
                
                tab3_special_rules = RULES_TAB3 + """
                \n\n🔥 [Tab 3 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)] 🔥
                1. [표 출력 다이어트 및 절대 생략 금지]: 수식이 길어 출력이 끊기는 현상을 방지하기 위해 표의 컬럼을 최소화했습니다. 하지만 **영양성분의 개수 자체는 절대 줄여서는 안 됩니다.** 시안에 30개의 영양소가 적혀있다면 첫 번째부터 30번째 영양소까지 무조건 100% 전부 표에 나열하십시오. `...`나 `이하 생략`을 쓰는 것은 중대한 범죄(에러)입니다.
                2. [Rule 23 '0' 표시 절대 원칙]: 시안의 수치를 추출하고, 성적서 환산값이 특정 기준(예: 열량 5kcal 미만, 탄수화물/당류/지방/단백질 0.5g 미만, 트랜스지방 0.2g 미만 등)에 해당하면 무조건 '0'으로 판정하십시오.
                3. [내외포장 1:1 대조 (Rule 68, 70)]: 박스와 팩의 1개당 영양 수치가 100% 픽셀 일치하는지 스캔하십시오.
                4. ⭐ [절대 주의: 부등호 방향 및 안전율 판정]: 
                   - 판정의 주어는 무조건 **'실측값(A)'**입니다.
                   - 하한선 그룹(비타민, 미네랄, 단백질 등): `실측값(A) >= 커트라인(B의 80%)` 이면 무조건 합법(✅)입니다.
                   - 상한선 그룹(열량, 당류, 나트륨, 지방 등): `실측값(A) <= 커트라인(B의 120%)` 이면 무조건 합법(✅)입니다.
                5. ⭐ [수학적 투명성 강제 (수석님 특별 지시사항)]: 
                   - 표의 셀 내용이 줄글로 길어지면 눈이 아프니, 반드시 `<br>` 태그를 사용하여 명확하게 문단을 나누십시오.
                   - '1일 기준치 % 검증' 칼럼: `예) 3% (60/2000) 일치` 형식으로 분수 역산식을 기재하십시오. (열량, 트랜스지방 등 기준치가 없는 성분은 '해당 없음' 기재)
                   - '상세 사유' 칼럼: `예) 표시량 대비 99.5% 수준으로 적합` 형식으로 안전율 코멘트만 심플하게 작성하십시오. 판정 단어(적합/부적합)를 중복해서 쓰지 마십시오.
                6. ⭐ [비현실적 수치 경고 (안전율 괴리 경고)]: 
                   - 법적 기준을 통과(합법)했더라도, 하한선 그룹에서 실측값이 표시량의 130%를 초과하거나, 상한선 그룹에서 실측값이 표시량의 80% 미만으로 너무 차이가 나면 판정 사유에 `<br>⚠️ **(실무 확인 권장)**` 경고를 추가하여 안전율 괴리를 지적하십시오.
                """

                judgment_prompt_tab3 = ""
                
                if "박스" in ins_mode:
                    judgment_prompt_tab3 += "## 3️⃣-1. [박스(외포장) vs 팩(내포장) 영양정보 1:1 교차 검증]\n"
                    judgment_prompt_tab3 += "| 영양성분명 (100% 전수 기재) | 타겟(박스) 1개당 표시량 | 비교용(팩) 표시량 | 상세 사유 (<br> 태그 사용) | 판정 |\n|---|---|---|---|---|\n\n"

                if has_any_doc:
                    title_prefix = "3️⃣-2." if "박스" in ins_mode else "3️⃣-1."
                    judgment_prompt_tab3 += f"## {title_prefix} [영양표시 오차 검증 (다중 성적서 100% 전수 대조 매트릭스)]\n"
                    judgment_prompt_tab3 += "| 영양성분 | 🧪 성적서 환산값(A) | 📦 시안 표시량(B) | ⚖️ 허용오차 커트라인 | 📊 1일 기준치 % 검증 | 🎯 상세 사유 (안전율 평가 위주) | 판정 |\n|---|---|---|---|---|---|---|\n\n"
                elif "박스" not in ins_mode:
                    judgment_prompt_tab3 += "## 3️⃣-1. [영양표시 오차 검증]\n(※ 성적서 미제출로 실측 오차 검증 생략)\n\n"

                judgment_prompt_tab3 += """## 🔍 [영양성분표 치명적 레이아웃 및 꼼수 정밀 검증]
- ⭐ **[Rule 3 앞뒷면 교차 검증 (강조 영양소 누락 적발)]**: 주표시면이나 기타면에 강조된 영양소(예: 나이아신, 비타민E 등)가 영양정보표 리스트 안에 법적 명칭으로 누락 없이 모두 기재되어 있는지 확인 (누락 시 🚨부적합 처리): 
- ⭐ [Rule 80] 영양정보표 상단 레이아웃 확인 (총 내용량 폰트 축소 금지 포함): 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
- 🔠 **[오탈자 스캔 결과]**: (Pass 1.8 바탕 오탈자만 기재)
- 📏 **[띄어쓰기 스캔 결과]**: (Pass 1.8 바탕 띄어쓰기만 기재)
"""
                st.session_state["result_tab3"] = run_qc_3pass(tab3_special_rules, judgment_prompt_tab3, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【의무표시 및 인증마크 해독 중...】"):
                # ⭐ [V326.00 패치] 추출 격리 + 점진적 릴레이 탐색 미션 적용
                missions = [
                    "⭐ [정밀 추출 명령]: 바코드, 분리배출 마크 등은 '기타면/측면' 이미지에서 우선적으로 정밀하게 추출하십시오.",
                    "⭐ [점진적 탐색 및 룰 검증 명령 (인간의 시선 흐름)]: '의무표시 3종(1399 등)', '용기 세부 재질', '식품유형별 주의문구' 등을 검증할 때, 먼저 기타면 이미지를 확인하십시오.",
                    "▶ 기타면에 없다면? 즉시 '부적합'이나 '확인 요망' 처리하지 말고, 함께 업로드된 주표시면이나 정보표시면 이미지를 스캔하십시오.",
                    "▶ 타 면에서 발견 시: '기타면에는 없으나 정보표시면에서 재질 표기(또는 주의문구) 확인됨'이라고 적고 룰에 따라 적법성을 판정하십시오.",
                    "▶ 모든 면에서 미발견 시: 패키지 전체를 뒤져도 의무 문구가 없을 경우에만 법적 누락으로 간주하여 🚨 부적합 또는 ⚠️ 확인 요망 처리하십시오."
                ]
                judgment_prompt = """## 4️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 상세 사유 (<br> 태그 사용, 생략 없이 서술) | 판정 |
| :--- | :--- | :--- | :--- |
| **의무표시 3종 Global Scan** | [Rule 59] | | |
| **기타면 영양강조표시 정밀 검증** | [Rule 21, 52] | (※ 100g, 100mL, 100kcal, 1회섭취량 중 하나라도 충족하는지 수식으로 증명할 것) | |
| ⭐ **100% 기만 표시 정밀 검증** | [Rule 88] | (※ 기타면에 '100%' 강조 문구가 있는지 스캔하고, 단순 함량 100%인지 원산지 100%인지 구분하여 판정할 것) | |
| **알레르기 교차오염 검증** | [Rule 38] | | |
| **HACCP 마크 공식 명칭** | [Rule 56] | | |
| **특정균 균수 분리 표시 의무** | [Rule 87] | | |
| **용기 세부 재질 정밀 검증** | [Rule 73] | | |
| ⭐ **식품유형별 동적 주의문구 스캔** | [Rule 74, 77] | (※ 현재 설정된 제품유형에 맞춰 필수 주의문구가 누락 없이 존재하는지 확인) | |
| **CS 클레임 방어용 문구** | [Rule 75] | | |
| ⭐ **오탈자 스캔 (명백한 글자 오류)** | 전수 검사 | (Pass 1.8의 🔠 오탈자 결과만 분리해서 기재) | |
| ⭐ **띄어쓰기 스캔 (간격 오류)** | 전수 검사 | (Pass 1.8의 📏 띄어쓰기 결과만 분리해서 기재) | |
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    with tab5:
        st.info("💡 [AI 자율 스캔 모드] 기계적 검증(1~4번 탭)이 잡아내지 못하는 문맥상의 위법성, 과대광고, 소비자 기만 행위를 법령 PDF를 기반으로 심층 스캔합니다.")
        if st.button("▶️ AI 법률 자문 자율 스캔 시작", key="btn_law"):
            with st.spinner("【법률 스캔 중: 마케팅 리스크 및 심층 추적...】"):
                missions = [
                    "⭐ [타겟 격리 명령]: 다중 포장(박스 vs 팩) 검토 모드일 경우, 함께 제공된 '비교용 팩(내포장)' 이미지는 완전히 백지화(Ignore)하십시오. 오직 박스(타겟) 시안에 인쇄된 문구와 디자인만을 대상으로 법률 스캔을 진행하십시오.",
                    "업로드된 시안에서 '12년 연속 1등', '특허', '효능 표방', '미래 시점(날짜) 포함 문구' 등 마케팅 카피, 제품명, 강조 문구, 뱃지 디자인만을 정밀 스캔하여 추출하십시오. (원재료명, 영양성분 숫자, 띄어쓰기는 추출 금지)",
                    "추출된 마케팅/광고 요소들이 「식품등의 표시·광고에 관한 법률」 및 고시상 부당광고(소비자기만, 허위과대광고, 객관적 근거 결여 등)에 해당하는지 업로드된 법령 PDF에서 관련 조항을 검색하여 추출하십시오."
                ]
                
                judgment_prompt = """## 5️⃣ [AI 법률 자문 자율 스캔 리포트]
⭐ [월권행위 절대 금지 및 타겟 격리 명령] ⭐
1. 업무 침범 금지: 이 탭에서는 1~4번 탭에서 수행하는 '원재료명 1:1 대조', '띄어쓰기 및 오탈자 검수', '영양성분 반올림 계산' 등을 절대 수행하지 마십시오.
2. 자율 스캔 임무: 어떠한 제약도 두지 말고, PDF 원문 전체를 활용하여 위법 리스크를 스스로 찾아내어 리포트하십시오.
3. Zero-Knowledge: 사전 학습 지식을 차단하고 오직 사용자가 업로드한 법령 PDF 파일만을 진리로 삼아 대조하십시오.
4. ⭐ [타겟 격리]: 다중 포장(박스 vs 팩) 모드일 경우, 함께 제공된 '비교용 팩' 이미지는 100% 무시하고 오직 타겟인 '박스' 시안만 보고 평가하십시오.

---

### 📋 [법률 스캔 결과 보고서]

#### [파트 1: 마케팅 및 부당한 표시 리스크]
(허위/과대광고, 소비자 기만, 신체 효능 표방 등 적극적 위반 사례 검토)

#### 📌 [식별된 문구/디자인]: "추출된 광고/마케팅 문구 및 시안 상의 위치 작성"
* **적용 법령 및 조항:** [문서명, 제O조 제O항 또는 별표 규정]
* **법령 원문:** > "PDF 원문을 그대로 인용"
* **AI 법무팀 자문 의견 (위법 리스크):**
  * 🚨 **[리스크 총평]:** (법령에 근거한 객관적인 위법 사유 또는 면제 사유 요약)
  * 🔍 **[다면(Double-Check) 교차 검증 결과]:** (광고의 객관적 근거 결여, 시점 오류, 소비자 오인 가능성 등 문맥상 리스크를 날카롭게 지적)

---

#### [파트 2: 법정 의무 표시사항 누락 리스크]
(제품 식품유형(예: 음료류, 가공두유 등)에 따라 법적으로 패키지에 반드시 기재해야 하는 주의문구(예: 알레르기, 보관방법 등)가 누락되었는지 PDF를 뒤져서 검토)

#### 📌 [누락 리스크 항목]: "식품유형별 의무 주의사항 등"
* **적용 법령 및 조항:** [문서명, 제O조 제O항 또는 별표 규정]
* **법령 원문:** > "PDF 원문을 그대로 인용"
* **AI 법무팀 자문 의견 (위법 리스크):**
  * 🚨 **[리스크 총평]:** (법령에 근거하여 시안에서 누락된 의무 표기 지적)
  * 🔍 **[다면(Double-Check) 교차 검증 결과]:** (타 면에 기재되었을 가능성 등 종합적 판단)
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
