import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import re
import tempfile
import socket
import io
import json
import datetime

# ==========================================
# [UI 레이아웃 픽스] 반드시 최상단에 위치해야 넓은 화면이 유지됩니다!
# ==========================================
st.set_page_config(page_title="식품 QC 마스터", layout="wide")

import google.generativeai as genai
import glob

# [네트워크 방어] 파이썬 전체 대기 시간을 10분(600초)으로 연장
socket.setdefaulttimeout(600)

# ==========================================
# [Google Cloud Vision API 설정]
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
        return "[시스템 알림]: google-cloud-vision 라이브러리가 설치되지 않았습니다."
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
            return f"[Vision API 에러]: {response.error.message}"
        return response.full_text_annotation.text
    except Exception as e:
        return f"[Vision API 실행 오류]: {e}"

def check_password():
    def password_entered():
        if st.session_state["password"] == "2082":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("시스템 접속 비밀번호 입력", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("비밀번호 오류. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)

# ==========================================
# 모델 맵핑
# ==========================================
MODEL_NAME = "gemini-3.6-flash"
MODEL_NAME_FLASH = "gemini-3.5-flash-lite"

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
# [첨가물 표 4, 5, 6 하드코딩 DB]
# ==========================================
ADDITIVE_TABLE_4 = [
    "데히드로초산나트륨", "소브산", "소브산칼륨", "소브산칼슘", "안식향산", "안식향산나트륨", "안식향산칼슘", "안식향산칼륨", "파라옥시안식향산메틸", "파라옥시안식향산에틸", "프로피온산", "프로피온산나트륨", "프로피온산칼슘", "나타마이신",
    "사카린나트륨", "수크랄로스", "아세설팜칼륨", "아스파탐", "네오탐", "알리탐", "스테비올배당체", "효소처리스테비아", "토마틴", "감초추출물", "나한과추출물", "스테비아추출물", "에리트리톨",
    "식용색소녹색제3호", "식용색소녹색제3호알루미늄레이크", "식용색소적색제2호", "식용색소적색제2호알루미늄레이크", "식용색소적색제3호", "식용색소적색제40호", "식용색소적색제40호알루미늄레이크", "식용색소청색제1호", "식용색소청색제1호알루미늄레이크", "식용색소청색제2호", "식용색소청색제2호알루미늄레이크", "식용색소황색제4호", "식용색소황색제4호알루미늄레이크", "식용색소황색제5호", "식용색소황색제5호알루미늄레이크", "이산화티타늄",
    "아질산나트륨", "질산나트륨", "질산칼륨",
    "아황산나트륨", "차아황산나트륨", "무수아황산", "메타중아황산나트륨", "메타중아황산칼륨", "이산화황",
    "부틸히드록시아니솔", "디부틸히드록시톨루엔", "몰식자산프로필", "에리토브산", "에리토브산나트륨", "터셔리부틸히드로퀴논", "이디티에이칼슘이나트륨", "이디티에이나트륨",
    "카페인"
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
    "L-글루타민", "L-글루탐산", "L-글루탐산암모늄", "L-글루탐산칼륨", "글리세로인산칼륨", "글리세로인산칼슘", "L-글루탐산나트륨"
]

# ==========================================
# 시스템 지시어
# ==========================================
SYSTEM_PROMPT = f"""당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
당신에게는 창의성, 추론 능력, 융통성이 전혀 없습니다. 오직 화면에 보이는 픽셀 단위의 글자(Text)만 있는 그대로 읽고 기계적으로 1:1 대조하는 봇(Bot)입니다.

[절대 생략 금지 및 100% 원본 보존의 법칙 (치명적 오류 방어)]:
어떠한 경우에도 텍스트를 임의로 요약하거나 `(...)`, `...`, `생략`, `이하 생략`, `등` 과 같은 기호나 단어를 사용하여 출력을 얼버무리지 마십시오. 
표(Table)를 작성할 때 원재료가 100개든 영양성분이 50개든 첫 줄부터 마지막 줄까지 100% 풀스펠링으로 끝까지 타이핑해야 합니다. 말줄임표나 생략 관련 단어를 하나라도 사용하는 순간 치명적인 시스템 오류로 간주됩니다.

[0순위 절대 방어막: 5% 미만 복합원재료 과잉 지적 금지 (Rule 5 적용)]:
어떤 첨가물이나 원료의 표기 누락(또는 용도 누락)을 지적하기 전에, 반드시 그 원료가 배합비 5% 미만인 복합원재료의 하위 성분인지 가장 먼저 확인하십시오. 5% 미만 일반 복합원재료의 하위 성분이라면 [표 4, 5, 6] 첨가물 규정 등 모든 규정을 무시하고 무조건 "전개/표시 의무 면제(✅)"로 판정하십시오. (단, 알레르기 물질은 예외이며 혼합제제는 이 면제 룰에서 절대 제외됩니다.)

[식품첨가물 표기 특별 통제 원칙]: 
원재료명 란의 첨가물을 판정할 때, 반드시 아래 하드코딩된 DB를 먼저 대조하여 판정하십시오.
* [표 4 소속 (명칭+용도 병기 강제, 누락시 🚨부적합)]: {ADDITIVE_TABLE_4}
* [표 5 소속 (명칭 또는 간략명만 표시, 용도 생략해도 ✅합법)]: {ADDITIVE_TABLE_5}
* [표 6 소속 (명칭, 간략명, 주용도 중 선택 표시 ✅합법)]: {ADDITIVE_TABLE_6}

모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 ⚠️(확인 요망) 기호를 붙이십시오."""

# ==========================================
# 마스터 룰북 원문 (절대 축약 금지 - 100% 전체 포함본)
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## [1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)]
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

## 검토 대원칙: 품질관리 지침

**Rule 1. [원산지 상위 3순위 표기 및 98% 컷오프 예외 룰]**
   - [Rank B: 원산지 산정용 순위 적용]: 원산지 표시 의무는 전체 배합비 순위가 아닌, 아래 Rule 28에 따라 필터링된 [Rank B]의 1위, 2위, 3위 원료에만 발생합니다. (누락 시 🚨부적합). Rank B에서 4위 이하인 원료는 원산지 표시 의무가 없습니다.
   - [98% 컷오프 예외]: 단, Rank B 1순위 원료 단독으로 98% 이상이면 1순위만 표기, 1순위와 2순위 배합비의 합이 98% 이상이면 2순위까지만 표기해도 합법(✅)입니다.

**Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 개별 향료명이 명시되어 있어도, 시안 원재료명에 단순히 '향료'로 묶어 표기 가능. (단, Rule 85 참고)

**Rule 3. [주표시면 vs 영양성분표 누락 교차검증 강제 룰]**
   - [대원칙]: 주표시면(앞면)이나 기타면에 특정 영양성분(예: 나이아신, 비타민E 등)의 함량이나 명칭이 뱃지 등으로 강조되어 있다면, 해당 성분은 반드시 뒷면 영양정보표 테두리 안에도 법적 명칭으로 누락 없이 기재되어야 합니다.
   - 주표시면에는 자랑해놓고 영양정보표에 해당 항목이 아예 없다면 명백한 위법(🚨부적합)입니다.
   - 강조된 영양소 수치는 뒷면 표의 수치와 단 1의 오차도 없이 100% 일치해야 합니다.
   - 세트 포장의 주표시면에는 '총 내용량'과 '총 열량(kcal)'이 모두 기재되어야 합니다.

**Rule 4. [배합비 데이터 누락 시 동적 추론(Dynamic Inference) 및 무죄 추정 룰]**
   - 증빙 서류에 배합비(%) 데이터가 없더라도 절대 판정을 포기(⚠️)하거나 멈추지 마라.
   - [순위 추론]: 시안(포장지)에 나열된 원재료의 텍스트 순서 자체가 '중량순(Rank A)'이라고 100% 신뢰하고 가정하라. 이를 바탕으로 Rule 28에 따른 원산지 타겟(Rank B 1~3위)을 스스로 소거법으로 도출하여 원산지 표시 여부를 깐깐하게 대조하라.
   - [2% / 5% 룰 유연화]: 정확한 %를 알 수 없으므로, 나열 순서에 대한 지적(Rule 34)은 무조건 합법(✅)으로 간주하라. 복합원재료 전개 생략(Rule 5)의 경우 부적합 처리하지 말고 "배합비 5% 미만 조건에 의한 합법적 생략인지 실무자 확인 요망"이라며 ⚠️(확인 요망) 처리하라.

**Rule 5. [복합원재료 5% 미만 전개 면제 및 혼합제제 절대 예외 룰]**
   - [대원칙]: 배합비 5% 미만인 '복합원재료(일반 가공식품)'는 괄호를 열고 하위 성분을 전개할 의무가 아예 없습니다. 생략 합법(✅).
   - [첨가물 과잉 단속 금지 원칙]: 위 조건에 따라, 5% 미만 '일반 복합원재료' 내부에 [표 4, 5, 6] 소속 식품첨가물이 들어있더라도 명칭/용도 표시 의무가 완전히 면제됩니다.
   - [혼합제제 절대 면제 불가 - Rule 44와 연계]: 서류상 식품유형이 '혼합제제'인 원료는 이 5% 미만 면제 룰이 절대로 적용되지 않습니다. 혼합제제의 하위 성분을 검사할 때는 이 Rule 5를 완전히 머릿속에서 지우고, 무조건 Rule 44로 넘어가서 [표 4, 5, 6] 기준에 따라 첨가물 용도 표시 여부를 깐깐하게 따지십시오. "5% 미만 혼합제제이므로 용도 표시 면제"라고 판정하면 치명적인 시스템 오류입니다.
   - [조건 B: 5가지 컷오프]: 배합비가 5% 이상인 일반 복합원재료의 경우, 하위 성분을 많이 사용한 순서대로 5가지만 명시되어 있다면 나머지 생략은 합법(✅).

**Rule 6. 당류/시럽 필터링**
   - 당류 0g 표기 시 0.5g 미만인지 검증.

**Rule 7. [당알코올 10% 컷오프 룰]**
   - 당알코올류 10% 미만 사용 시 주의문구 생략 합법(✅).

**Rule 8. 수입 원료 원산지 유연성 보호**
   - '외국산' 표기는 적합.

**Rule 9. 식품유형 vs 제품명 구분**
   - 혼동되지 않도록 명확히 구분.

**Rule 10. 영양성분 강조표시 (액체/고체 분리)**
   - 제형에 따라 100g/100mL 당 기준을 분리하여 심사.

**Rule 11. [영양정보 단방향 허용오차 법칙 (산수/부등호 방향 절대 주의!)]**
   - [AI의 실수 방지 족쇄]: 80%나 120%를 '실측값'에 곱하지 마라! 무조건 기준이 되는 '시안 표시량'에 곱해서 합격 커트라인을 도출해라.
   - [하한선 그룹(비타민, 미네랄, 단백질, 탄수화물 등)]: `(실측값) >= (시안 표시량 × 0.8)` 이면 무조건 합법(✅).
   - [상한선 그룹(열량, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤, 나트륨)]: `(실측값) <= (시안 표시량 × 1.2)` 이면 무조건 합법(✅).

**Rule 12. [원재료명 교차 검증 및 임의 추론 금지]**
   - 서류 없이 레시피 상상 금지.

**Rule 13. [알레르기 표기 시각적 한계 보완 및 실무 확인 룰]**
   - 알레르기 물질은 원재료명과 바탕색이 구분되는 '별도 란(박스)'에 기재해야 합니다.
   - [AI 시각적 한계 보완]: AI는 이미지의 음영(바탕색) 차이를 정확히 판별하기 어려우므로, 텍스트 스캔 결과 시안에 'OO 함유'라는 독립 문구가 존재한다면 일단 알레르기 표시란 규정을 준수한 것으로 간주하여 ✅(적합) 처리하십시오.
   - [강제 출력 원칙]: 위 경우 판정 사유 끝에 반드시 "⚠️(실무 확인 권장): 시스템상 'OO 함유' 텍스트 표기는 확인되었으나, 해당 문구의 바탕색이 원재료명 란과 다르게 음영 처리되어 확실히 구분되는지 육안으로 한 번 더 확인해 주십시오."라는 멘트를 덧붙이십시오.

**Rule 14. [첨가물 표 4, 5, 6 교차 검증 및 표 6 주용도 합법성]**
   - [표 4]: 명칭과 용도(예: 감미료) 둘 다 표시 필수.
   - [표 5]: 명칭 또는 간략명 표시 필수 (용도만 표시 불가).
   - [표 6 특권]: 명칭, 간략명, 또는 '주용도(예: 유화제, 산도조절제, 팽창제 등)' 중 하나만 단독으로 표시해도 완벽한 합법(✅)입니다. AI는 시안에 화학적 명칭 없이 '유화제'라고만 적혀 있어도 절대 부적합 처리하지 마십시오.

**Rule 15. [기능성 오인 문구 및 신체 조직 작용 전면 통제]**
   - '소화불편감 완화' 등 인체의 기능·작용·효과를 직접 암시하거나 기만하는 표현 전면 금지(🚨부적합).

**Rule 16. [원산지 100% 표기 룰]**
   - 단일 국가 100% 수입 원료만 100% 강조 가능.

**Rule 17. ['無첨가' 마케팅 검증]**
   - 금지 첨가물 배제 강조 시 부적합(🚨).

**Rule 18. [타겟 오인 명칭 금지]**
   - 영유아 타겟 명칭 사용 적발.

**Rule 19. ['무당' vs '무가당' 범용 검증 및 대체당 합법성 룰]**
   - [무당(Zero Sugar)]: 완제품 100g(mL)당 당류 0.5g 미만 시 합법.
   - [무가당(No Added Sugar)]: 제조 공정 중 인위적 당류 첨가 금지.
   - [알룰로오스 예외 합법]: '알룰로오스'는 원재료 분류상 당류가공품이더라도 당류 저감 용도의 대체재이므로 '무가당/저당' 표시에 사용해도 무조건 합법(✅)이다.

**Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무 없음.

**Rule 21. ['고/풍부', '저', '무' 영양강조표시 4대 조건 OR 법칙 및 수학적 증명 룰]**
   - [대원칙]: 식약처 고시에 따라 영양강조 기준은 4가지(100g당, 100mL당, 100kcal당, 1회섭취량당) 중 단 하나라도 충족하면 무조건 합법(✅)입니다. (특히 용량 기준 미달 시 반드시 100kcal 환산 기준으로 통과하는지 교차 검증할 것)
   - ['고', '풍부' 표시 기준]: 
     1) 단백질, 식이섬유: 기준치의 20%(100g당) / 10%(100mL당) / 10%(100kcal당) / 20%(1회섭취량당) 이상.
     2) 비타민 및 무기질: 기준치의 30%(100g당) / 15%(100mL당) / 10%(100kcal당) / 30%(1회섭취량당) 이상.
   - ['저' 표시 기준]: 열량(100g당 40kcal 미만 또는 100mL당 20kcal 미만), 나트륨(100g당 120mg 미만) 등.
   - ['무(Zero)' 표시 기준]: 열량(100mL당 4kcal 미만), 나트륨/지방/당류(5mg/0.5g/0.5g 미만).
   - [부적합 시 절대 원칙]: 부적합 판정을 내리려면 4가지 조건의 수식을 모조리 나열하여 전부 미달임을 명백히 증명해야 합니다. 하나라도 통과 시 무조건 합법 처리하십시오.

**Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 함.

**Rule 23. [식약처 영양성분별 '0' 표시 절대 규정 및 '불검출' 바(-) 표기 룰]**
   - 다음 성분은 성적서의 실측 환산값이 아래 기준 미만일 경우 반드시 "0"으로 표시해야 하며, 시안에 "0"으로 적혀있다면 완벽한 합법(✅)입니다. (불검출 또한 0으로 환산합니다)
   - [열량]: 5kcal 미만 -> "0kcal"
   - [나트륨]: 5mg 미만 -> "0mg"
   - [탄수화물, 당류, 단백질, 지방]: 0.5g 미만 -> "0g"
   - [트랜스지방]: 0.2g 미만 -> "0g" (0.2g 이상~0.5g 미만은 "0.5g 미만" 표기)
   - [포화지방]: 0.5g 미만일 경우 "0g"으로 표시 가능. (5g 이하는 0.1g 단위 반올림)
   - [콜레스테롤]: 2mg 미만 -> "0mg"
   - ['불검출' 시안 표기 교차 검증 및 실무 권장 룰]: 
     - 시험성적서 상 '불검출'로 명확히 확인되는 성분(특히 콜레스테롤 등)에 대해, 시안에 "0"이라고 적혀 있을 경우: 단독으로 적합 처리하지 말고 ⚠️(실무 확인 권장)으로 판정하십시오. 사유에는 "⚠️ 성적서상 '불검출'이므로 식약처 최신 가이드라인에 따라 '-' (바) 기호로 표시가 가능합니다. 향후 미량 검출을 대비해 보수적으로 '0'을 유지할지, 아니면 고객사 요청(디자인)에 맞춰 '-'로 변경할지 실무자의 최종 확인 바랍니다." 라고 출력하십시오.
     - 시안에 이미 "-"로 적혀 있을 경우: 최신 가이드라인에 부합하는 완벽한 합법이므로 ✅적합 판정을 내리십시오.

**Rule 24. [무당/무가당/무첨가 강조표시 연계 의무: 열량 및 감미료 병기]**
   - [총 열량(kcal) 필수 표시]: 패키지에 무당/무가당/무첨가 강조 문구가 사용된 경우, 해당 글자 주변(동일 시야각)에 반드시 총 열량(kcal)이 명확하게 기재되어야 합니다. 누락 시 🚨부적합 처리.
   - [감미료 함유 문구 필수 (Rule 52 연계)]: 당류를 줄인 대신 합성/천연 감미료(수크랄로스, 아스파탐, 스테비올배당체 등)를 사용했다면, 강조 문구 주변에 반드시 "감미료 함유" 문구를 병기해야 합니다. (단, 알룰로오스만 사용 시에는 병기 면제 가능)

**Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 분리.

**Rule 26. [고체/액체 단위 구분]**
   - 고체는 g, 액체는 mL.

**Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등은 100kcal 당 조건을 적용 금지.

**Rule 28. [Rank A vs Rank B 분리 및 원산지 산정 예외 4대장 룰]**
   - AI는 배합비 순위를 검토할 때 반드시 두 가지 랭크를 분리해서 계산하십시오.
   - [Rank A: 배합비 절대 순위]: 모든 원료의 원래 % 비율대로 세운 순위. (Rule 34 나열 순서 검증에만 사용)
   - [Rank B: 원산지 산정용 순위]: 전체 배합비 목록에서 [정제수, 당류(설탕, 유기농설탕, 물엿, 과당, 올리고당, 당류가공품 등 일체), 주정, 식품첨가물] 이 4가지 카테고리의 원료를 100% 삭제(제외)하고, 남은 실질 원료들끼리만 다시 %를 비교하여 매긴 순위. 원산지 의무는 오직 이 Rank B를 기준으로 심사하십시오. (설탕 등 당류를 절대 포함시키지 마십시오.)

**Rule 29. [국내 가공 복합원재료 원산지 역추적 합법성]**
   - 하위 원물 원산지를 역추적해 표기했다면 합법(✅).

**Rule 30. [알레르기 오판 차단 룰]**
   - 호밀, 귀리, 보리는 '밀' 알레르기가 아님. 대두 표기는 '콩기름'이 있으면 합법.

**Rule 31. [다중 성적서 데이터 병합]**
   - 성적서 누락 없이 병합 대조.

**Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 반올림 오차에 의한 계산 차이는 합법.

**Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치 구분.

**Rule 34. [배합비 전개 순서 100% 일치 강제 및 2% 미만 예외 룰]**
   - [절대 원칙]: 원재료명은 반드시 서류상의 배합비율(%)이 높은 중량 순서대로 기재되어야 합니다. 배합비 순위가 시안의 나열 순서와 단 한 칸이라도 다르면 명백한 표시기준 위반(🚨부적합)입니다. (Rule 28의 Rank A 기준 적용)
   - [2% 미만 예외]: 단, 배합비율이 2% 미만인 원료들은 중량 순서에 상관없이 자유롭게 기재해도 완벽한 합법(✅)입니다.
   - [순서 역전 정밀 검증]: AI는 서류에서 2% 이상인 원료들(예: 1위 35%, 2위 28%, 3위 10.7%, 4위 10.0%...)을 무조건 찾아내어 그 순서가 시안에서 완벽히 동일한지 엄격하게 검증하십시오. (예: 10.7%인 저감미당이 10.0%인 A2단백원유보다 무조건 앞에 와야 합니다. 역전 시 🚨부적합 처리)

**Rule 35. [범용 간략명/관용명 허용 및 혼합제제 괄호 내부 N종 은폐 금지 범용 룰]**
   - [관용명/동의어 합법 처리]: 실무적으로 호환되는 동의어나 관용명 표기는 100% 합법(✅)입니다. (예: 옥배유=옥수수기름, 액상과당=기타과당=고과당, 황백당=갈색설탕 등)
   - [내부 식별 코드 생략]: 서류상의 납품업체 전용 식별코드(예: E(30), -2 등)는 생략 완벽 합법(✅).
   - [용도명 N종 무조건 합법]: '향료 3종', '영양강화제 3종', '유화제 2종'처럼 [표 6]에 속하는 주용도명 뒤에 숫자를 붙여 묶는 단어는 식약처 규정상 완벽한 합법입니다. 
   - [혼합제제 괄호 내부 은폐 절대 불가]: 패키지 시안에 `혼합제제(산도조절제 2종)`처럼 묶거나, 여러 혼합제제의 하위 성분들을 몰래 빼와서 임의로 `영양강화제 3종`처럼 묶어 은폐(블랙박스화)한 경우 명백한 위법(🚨부적합)으로 처리하십시오. 단, 애초에 레시피에 3가지 성분이 독립적으로 투입되어 그것들을 용도명으로 합법적으로 묶은 경우는 제외(적합)입니다.

**Rule 36. [주의사항 오탈자 스캔]**
   - 오탈자 정밀 검수. 각 구역별 텍스트 스캔 및 띄어쓰기 비교 필수.

**Rule 37. [법적 서류 우선 고려]**
   - Rule 35 예외 우선 고려.

**Rule 38. [알레르기 22종 하드코딩 및 교차오염 완벽 검증 룰]**
   - [알레르기 22종 절대 족쇄]: 알레르기 판정 시 오직 [한국 식약처 지정 22종: 난류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 아황산류, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣]에 대해서만 검증하십시오. 
   - [강제 수식 및 하청업체 전이 금지]: `[최종 교차오염 정답지] = [사용자가 텍스트창에 입력한 우리 공장 마스터 목록] - [직접 투입된 알레르기]`
   - [하청/원료사 교차오염 무조건 무시]: 개별 원재료(원료 스펙 서류)에 적힌 원료 공급사의 교차오염 물질(예: "본 원료는 고등어, 게를 사용하는 시설에서 제조...")은 완제품의 교차오염 목록에 절대 끌고 오지 마십시오! 오직 수석님이 설정한 '공장 마스터 목록'만을 기준으로 위 수학적 뺄셈식만 기계적으로 적용하십시오.

**Rule 39. [동명 원료 및 식품유형 종속성 분리 룰]**
   - 명칭이 같아도 [식품유형]이 다르면 분리 표기.

**Rule 40. [열량 표기 및 애트워터 계수 합법성 (유연성 패치)]**
   - 식약처 고시에 따라 열량은 "계산된 값을 그대로 표시하거나", "가장 가까운 5kcal 단위로 표시"하는 것 모두가 합법입니다.
   - 또한, 시안에 적힌 열량은 `(표시된 탄수화물×4) + (표시된 단백질×4) + (표시된 지방×9)`로 도출(애트워터 계수 적용)되는 경우가 실무적으로 매우 흔하며 이 역시 완벽한 합법입니다.
   - 따라서 실측값의 단순 반올림 수치와 다르다고 해서 기계적으로 부적합 처리하지 마십시오. 120% 상한선 오차 범위 이내면 무조건 합법(✅)입니다.

**Rule 41. [% 영양소 기준치 정밀 검증 및 다단 레이아웃 룰]**
   - 열량(kcal)과 트랜스지방은 %를 표기하지 않습니다.
   - 나머지 성분은 `(시안의 표시량 ÷ 1일 영양성분 기준치) × 100`을 정확히 역산하여 시안의 % 표기가 맞는지 대조하십시오.
   - 영양정보표가 좌우 2단(예: 100mL당 / 총 내용량당)으로 병기된 경우, 양쪽 수치가 성적서 대비 각각 올바르게 환산되었는지 이중 교차 검증하십시오.

**Rule 42. [완제품 서류 혼동 방지]**
   - 최종 완제품 기준 데이터만 사용.

**Rule 43. [시각적 한계 명시]**
   - 육안 판독 어려우면 임의 판정 금지.

**Rule 44. [식품첨가물(혼합제제) 표기 방식의 자율성 보장 (1:1 묶음 및 1:N 해체 모두 합법)]**
   - 혼합제제의 표기 방식은 디자이너의 편집(중복 투입 병합 등)에 따라 두 가지 형태가 모두 존재하며, 둘 다 완벽한 합법이다. AI는 표(Table)를 작성할 때 아래 두 가지 경우에 대해 절대 딴지를 걸지 마라.
   - 1. [1:1 묶음 표기 합법]: 디자이너가 서류에 있는 `혼합제제명(하위성분1, 하위성분2)` 껍데기를 그대로 유지해서 묶어 적었다면 완벽한 합법(✅)이다. "왜 개별 성분으로 해체하지 않았냐"고 절대 지적하지 마라.
   - 2. [1:N 해체 전개 합법]: 디자이너가 껍데기를 부수고 `하위성분1`, `하위성분2`로 낱낱이 흩뿌려 적었더라도 이 역시 완벽한 합법(✅)이다. "왜 혼합제제 명칭으로 묶지 않고 일부만 적었냐"고 절대 지적하지 마라.
   - 3. 즉, 묶어서 쓰든 풀어서 쓰든 하위 성분만 누락 없이 다 들어갔다면 무조건 양쪽 다 합법(✅)으로 통과시켜라.
   - [혼합제제 하위 성분은 5% 미만 룰(Rule 5) 적용 절대 금지]: 전개되어 나온 혼합제제의 하위 성분들은 그 즉시 독립된 첨가물로 취급됩니다. 따라서 배합비가 5% 미만이라도 Rule 5(면제)를 절대 적용하지 말고, 지체 없이 [표 4, 5, 6] 하드코딩 DB를 뒤져서 명칭/용도 병기 의무를 엄격하게 심사하십시오.

**Rule 45. [선택적 누락/마케팅 수식어 생략 허용]**
   - 서류에는 '유기농', '천연' 등의 마케팅 수식어가 포함되어 있더라도, 패키지 시안에서 해당 수식어를 생략(선택적 누락)하고 일반 명칭으로 표기하는 것은 완벽한 합법(✅)입니다. (법적 위반 없음)

**Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자 포함 시 하위 내역 스캔.

**Rule 47. [디자인적/물리적 차이 예외 인정]**
   - 영문 제품명과 뒷면 한글 제품명 불일치 시 합법.

**Rule 48. [서류 역할 분리 대조]**
   - 배합비(순서)와 한글라벨(최종 명칭) 분리.

**Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 앞면에 함량(%) 강조 시 반드시 '고형분 함량(%)' 병기 강제.

**Rule 51. [고형분(Brix) 보수적 표기 예외]**
   - 시안 수치가 서류 스펙보다 낮으면 합법(✅).

**Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 제품명에 농수산물이 쓰이면 원물 원산지 기재.

**Rule 54. [복수 원산지 혼합 비율 생략 합법성]**
   - 단일 원료 2개국 병기 시 비율 생략 확인 요망.

**Rule 55. [영양성분 반올림 강박 금지 및 '보수적 표기(안전율)' 합법성 룰]**
   - 식약처 고시에 따라 영양소는 "그 값을 그대로 표시하거나" 지정된 단위로 반올림하여 표시하는 것이 선택적으로 허용됩니다.
   - [보수적 표기(안전율) 절대 인정]: 공장 생산 편차를 고려하여 상한선(120%) 규제 대상(당류, 지방, 나트륨, 콜레스테롤 등) 실측값보다 다소 높게 적거나, 하한선(80%) 규제 대상(단백질 등)을 실측값보다 낮게 적는 '보수적 표기'는 실무적 정석이며 완벽한 합법입니다.
   - 따라서 1g 단위, 5mg 단위 등 식약처 반올림 단위에 딱 떨어지지 않게 임의 표기(예: 13g, 19mg)했더라도, 실측 수치가 80%~120% 허용 오차 범위 안에만 들어온다면 절대로 반올림 규정을 들이밀며 🚨부적합 처리하지 마십시오.

**Rule 56. [HACCP 인증 마크 제품유형별 교차 검증 (멸균유 포함)]**
   - HACCP 마크 내부의 텍스트가 현재 검토 중인 [제품유형]과 일치하는지 반드시 대조하십시오.
   - [공용 허용]: "안전관리인증" 텍스트는 모든 식품/축산물 유형에서 합법(✅).
   - [일반 식품]: "식품안전관리인증" 텍스트 합법(✅). (축산물에 사용 시 🚨부적합)
   - [축산물 (냉장 우유, 가공유, 상온 멸균유 등 모두 포함)]: "축산물안전관리인증" 텍스트 합법(✅). 만약 [식품유형]이 축산물(유가공품)인데 마크에 "식품안전관리인증"이라고 적혀 있다면 명백한 규정 위반이므로 🚨부적합 처리하십시오. (멸균 제품이더라도 우유류는 축산물입니다!)

**Rule 57. [세트포장 수량 강제 룰]**
   - 박스 번호에 "수량(X입)" 기재 확인.

**Rule 58. [함량 생략 합법성]**
   - 앞면에 함량(%) 명시 시 뒷면 생략 합법(✅).

**Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 패키지 어디에든 1399 등이 하나라도 존재하면 무조건 합법(✅).

**Rule 60. [복합원재료 원물 함량 기재 면제 룰]**
   - 괄호 안에 '고형분(%)' 명시 시 배합함량 기재 강요 면제(✅).

**Rule 61. [국산 가공 예외 룰]**
   - 괄호 없이 곧바로 (국산) 표기 시 합법.

**Rule 62. [보관상태 의무 표시 및 멸균 예외 룰]**
   - 냉장/냉동 제품인 경우 상태 명시 필수. 단, 멸균팩 등 상온 보관 제품은 냉장 표시 의무가 없으므로 제외(✅).

**Rule 63. [190mL 전용 질소충전 동적(Dynamic) 스캔 룰]**
   - 190mL 용량의 제품은 패키지 형태에 따라 질소충전 문구 기재 여부가 다릅니다 (미드팩=필수, 콤비스마일=불가).
   - AI는 먼저 시안에서 "질소충전" 또는 "질소가스" 텍스트가 실제로 존재하는지 이미지 스캔 결과를 확인한 후, 상황에 맞게 ⚠️(확인 요망) 사유를 다르게 출력하십시오.
   - [문구가 있을 경우]: "⚠️ 시안에서 190mL 용량과 '질소충전' 문구가 확인됩니다. 만약 해당 패키지가 미드팩(Mid-pak)이라면 적합하지만, 콤비스마일(무균팩)이라면 해당 문구를 삭제해야 합니다. 실무자의 재질 확인이 필요합니다."
   - [문구가 없을 경우]: "⚠️ 시안에서 190mL 용량은 확인되나 '질소충전' 문구가 없습니다. 만약 해당 패키지가 미드팩(Mid-pak)이라면 질소충전 문구를 추가해야 합니다. 실무자의 재질 확인이 필요합니다."

**Rule 64. [원물 기만표시 검증]**
   - 강조 비율이 추출액 비율이면 기만(🚨).

**Rule 65. [내부 식별 코드 생략 합법성]**
   - `-2` 등 내부 코드는 생략 합법.

**Rule 68. [다포장/세트포장 낱개 영양표시 복붙 적발]**
   - 박스 시안 영양표시의 수치가 박스 전체의 '총 내용량' 기준임에도 불구하고, 낱팩 1개의 용량을 그대로 복사해서 붙여넣은 경우 치명적인 복붙 에러(🚨)로 처리하십시오. 외포장(박스)에는 반드시 '1개당'이라는 기준이 명시되거나 전체 용량에 맞게 환산되어야 합니다.

**Rule 70. [내/외포장 100% 일치 강제 및 내용량/타이포그래피 예외 룰]**
   - 내포장(팩)과 외포장(박스)을 1:1 대조할 때, '내용량 및 열량' 표기 방식은 예외로 둡니다. 외포장에 전체 수량(X개입)을 곱한 총 내용량이 올바르게 적혀 있고 팩에는 단일 용량이 적혀 있다면, 텍스트가 다르더라도 합법(✅)입니다.
   - [타이포그래피 동등성 예외 강제]: 내외포장 대조 시 다음의 시각적/형식적 차이는 법적으로 완벽하게 동일한 것(✅적합)으로 면제 처리하십시오. 🚨부적합 처리하지 마십시오.
     1) 단순 기호의 유무: 마침표(.), 콜론(:), 쉼표(,), 띄어쓰기의 유무 차이. (예: `원재료명` vs `원재료명:` 은 동일함)
     2) 특수문자/아래첨자 호환: 화학명에 쓰이는 아래첨자(₁, ₂, ₃, ₆, ₁₂)와 일반 아라비아 숫자(1, 2, 3, 6, 12)는 100% 동일한 글자로 취급합니다. (예: `비타민B₁` vs `비타민B1` 은 동일함)
     3) OCR 자동 정제 결과 수용: 기계적 노이즈가 제거된 상태라면 원문과 다소 차이가 나더라도 합법으로 인정하십시오.
   - 위 예외를 제외한 원재료명, 주의문구, '1개당 영양성분 수치' 등 공통 표시사항은 텍스트 픽셀 단위로 대조하여 단 하나의 기호나 숫자라도 틀리면 부적합(🚨) 처리하십시오.

**Rule 71. [강조 폰트 크기 규정]**
   - 원료 함량 14pt 육안 확인 알림.

**Rule 72. ['조리예/이미지 사진' 점검]**
   - 연출 사진 텍스트 스캔.

**Rule 73. [세부 재질 검증]**
   - 뚜껑 있는 종이팩 `뚜껑: HDPE` 등 세부 재질 확인.

**Rule 74. [액상 음료 주의문구 식품유형 종속성 룰]**
   - 식품유형이 '음료류(혼합음료, 액상차, 과채음료 등)'인 경우에만 "개봉 후 냉장보관하시고 빨리 드시기 바랍니다" 문구를 강제 스캔하십시오. 
   - 시안의 식품유형이 '강화우유', '가공유' 등 우유류(축산물)인 경우, 이 룰을 절대 적용하지 말고 "우유류(축산물)이므로 음료류 주의문구 적용 대상 아님"이라며 무조건 면제(✅적합) 처리하십시오.

**Rule 75. [CS 클레임 방어용 주의문구 세트]**
   - 침전물, 용기 팽창 등 방어 문구 스캔.

**Rule 76. [OEM 업소명 타이틀 강제 스캔 및 축산물 종속성 검증]**
   - 위탁생산(OEM) 시 자사 상호명 앞에는 반드시 영업허가에 맞는 타이틀을 명시해야 합니다.
   - [축산물(유가공품) 절대 규칙]: 현재 검토 중인 [제품유형]이 '축산물(유가공품: 우유, 가공유 등)'이라면, 일반적인 '유통전문판매원'으로 적혀 있을 경우 명백한 위법(🚨부적합)입니다. 반드시 '축산물유통전문판매원'이라고 기재되어야 합법(✅적합)입니다. (제조원의 경우 '축산물가공장' 등으로 표기 가능)
   - [일반식품 절대 규칙]: 반대로 일반식품(음료류, 두유류 등)에 '축산물유통전문판매원'이라고 적으면 🚨부적합이며, '유통전문판매원' 또는 '판매원'이라고 적어야 합법입니다.

**Rule 77. [식품유형별 법정 의무 주의사항 동적(Dynamic) 스캔 룰]**
   - 단순히 고정된 문구만 찾지 마십시오. 검토 시작 시 부여된 `[제품유형]`을 바탕으로, 해당 식품유형에 법적으로 강제되는 전용 주의문구(예: 두유류의 전자레인지 가열 금지, 빙과류의 재냉동 금지, 당알코올 주의문구, 아스파탐 주의문구 등)가 시안에 누락 없이 존재하는지 동적으로 검증하십시오.

**Rule 78. [특수의료용도식품 타겟 광고 문구 합법성 검증]**
   - 특수의료용도식품 질환자를 타겟으로 한 영양공급 강조 문구는 무조건 합법(✅).

**Rule 79. [열량 구성비(%) 정밀 역산 룰]**
   - 탄수화물:단백질:지방 열량비율 역산 시 [당질(탄수화물-식이섬유) × 4kcal] + [식이섬유 × 2kcal] 필수.

**Rule 80. [선물세트 박스(외포장) 영양정보 레이아웃 강제]**
   - 박스 영양정보표 상단에 `총 내용량 OOO mL (OOO mL X O개입)` 및 `1개당` 포맷 확인. 영양정보표 내부 폰트 비율 임의 축소는 부적합(🚨) 처리.

**Rule 81. [영양표시 하단 면책 문구 토시 대조]**
   - 면책 문구 기호 100% 일치 확인.

**Rule 82. [영양소 법정 단위 엄격 검증]**
   - 비타민 단위 등 특수기호 100% 대조.

**Rule 83. [영양성분 % 병기 강제 원칙]**
   - 기준치 존재 성분 옆에 비율(%) 병기 필수.

**Rule 84. [유기가공식품 3단계 정밀 판정 룰 (95% / 70% 컷오프)]**
   - 시안(앞면/기타면 등)에 '유기농' 또는 '유기' 단어가 발견되면 반드시 배합비(%) 합계를 추적하여 아래 3단계에 따라 엄격히 판정하십시오.
   - [95% 이상]: 유기가공식품 인증 마크 사용 필수. 제품명 및 패키지 전면 강조 표기 완벽 합법(✅적합).
   - [70% 이상 ~ 95% 미만]: 인증 마크 사용 절대 불가(🚨부적합). 제품명에 '유기농' 사용 불가(🚨부적합). 단, 주표시면 등에 '유기농 원료 OO% 함유'처럼 유기농 원료의 총 함량을 명확하게 병기한 마케팅 문구는 합법(✅적합).
   - [70% 미만]: 인증 마크 불가(🚨). 제품명 불가(🚨). 패키지 전면/측면 등 마케팅 목적의 '유기농' 강조 문구 전면 금지(🚨부적합). 오직 뒷면 '원재료명' 리스트 내부에만 '유기농OOO' 표기 허용(✅적합).

**Rule 85. [식품첨가물 공전 명칭 사수 및 기호 창조 절대 금지]**
   - 명칭 축약 엄격 금지, 괄호 외 임의 기호 창조 전면 금지(🚨).

**Rule 86. [국가 공인 인증 도안 기만 및 텍스트 편법 규제 룰]**
   - 도안 미사용 텍스트 편법 적발 시 부적합(🚨).

**Rule 87. [특정균 강조 표시 및 균수 분리 기재 합법성 룰]**
   - 특정균 사용 시 주표시면 배합함량(%), 정보표시면 균수(CFU) 분리 기재 합법(✅).

**Rule 88. [100% 강조표시 기만 검증 룰]**
   - [원재료 100% 금지]: 패키지 시안(주표시면, 기타면 등 전체)에 "OO(원료명) 100%"라고 함량만을 단독으로 강조한 경우, 서류상 배합비에 정제수나 식품첨가물이 단 0.01%라도 존재한다면 무조건 소비자 기만(🚨부적합)으로 판정하십시오. (단, 농축액을 희석한 환원 제품으로서 첨가물을 바로 옆에 명시한 경우는 예외)
   - [원산지 100% 합법]: 단, "국산 OO 100%" 또는 "특정국가산 OO 100%"처럼 '원산지'를 수식하는 100% 표기는 배합비에 다른 첨가물이나 정제수가 섞여 있어도 완벽한 합법(✅)입니다.

**Rule 89. [국내 제조 가공품 원료의 원산지 이중 표기 규정 (농관원 유권해석)]**
   - [종속성 절대 원칙]: 이 룰은 Rule 28에 따라 원산지 표시 의무가 확정된 [Rank B의 1~3위] 원료에만 발동합니다. 당류가공품, 정제수 등 애초에 면제된 원료에는 절대로 이 룰을 적용하여 부적합 처리하지 마십시오.
   - 수입 원물을 국내에서 가공하여 품목제조보고를 마친 '국내 제조 가공품(예: 옥배유, 사과농축액 등)'을 납품받아 원료로 사용할 경우, 단순히 `원료명(국가명)` 형태로 기재하면 위법(🚨부적합)입니다.
   - 한글표시사항 등 서류에서 '품목제조보고번호'가 확인되거나 제조원이 국내 업체라면 가공품이므로, 반드시 `원료명(원료명: 국가명)` 형태로 괄호 안에 원료명을 한 번 더 명시한 뒤 원산지를 적어야 합법(✅)입니다.
   - (위법 예시) `옥배유(스페인산)` -> 🚨부적합 / (합법 예시) `옥배유(옥배유: 스페인산)` -> ✅적합

**Rule 90. [범용 명칭 치환(유연한 맵핑) 룰]**
   - 서류상에 기재된 여러 종류 시럽류, 페이스트류, 식이섬유 등의 복합원재료가 패키지 시안에서는 식품유형에 따라 `당류가공품1`, `당류가공품2`, `올리고당`, `혼합제제` 등의 범용 명칭으로 치환되어 묶음 표기되는 것은 식품업계의 보편적인 합법 관행입니다.
   - 시안에 '당류가공품' 등이 있는데 서류 명칭과 글자가 다르다고 무조건 누락(🚨부적합) 처리하지 마십시오. 서류의 비고란이나 하위 전개 성분을 논리적으로 추론하여 시안의 범용 명칭과 유연하게 매칭(맵핑)하고 ✅적합 처리하십시오.

**Rule 91. ['혼합제제' 명칭 단축 표기 절대 합법성]**
   - 서류상에 '식품첨가물혼합제제'나 고유명칭(예: 비타민미네랄혼합제제)으로 기재되어 있더라도, 패키지 시안에 단순히 '혼합제제'라고만 줄여서 표기하는 것은 실무상 완벽한 합법(✅)입니다. 이를 두고 규정 위반이나 명칭 축약 오류라며 🚨부적합 처리하지 마십시오.

**Rule 92. [부분 캡처 이미지 한계에 따른 누락 항목 조건부 보류 룰]**
   - 사용자가 업로드한 이미지는 패키지의 특정 구역만 자른 부분 이미지일 수 있습니다. 따라서 '식품유형', '반품/교환처', '소비자상담실', '1399 신고문구' 등의 일반/행정 정보가 현재 검토 중인 이미지에서 보이지 않는다고 해서 즉시 🚨부적합(누락) 판정을 내리지 마십시오.
   - 대신 ⚠️(확인 요망)으로 판정하고, 사유에 "현재 업로드된 부분 이미지에서는 해당 항목이 확인되지 않습니다. 패키지의 다른 면(주표시면, 측면 등)에 표기되어 있는지 실무자의 확인이 필요합니다."라고 부드럽게 안내하십시오. 

**Rule 93. [수출 겸용 소재지 주소란 '대한민국' 표기 예외 룰]**
   - 시안의 주소지 텍스트에 한하여 "대한민국"이 추가 표기되어 있다면 절대 부적합 처리하지 마십시오. 무조건 ⚠️(확인 요망)으로 판정하고, 수출용이 맞는지 실무 부서에 최종 확인하라고 안내하십시오.

**Rule 94. ['MADE IN KOREA' 스마트 조건부 스캔 룰]**
   - 시안에서 'MADE IN KOREA' 또는 '한국산' 텍스트가 발견되면, 반드시 원산지 목록과 교차 검증하십시오. 수입산 원료가 1%라도 존재하면 부가가치 기준 미달로 원산지 오인 기만행위(🚨부적합)입니다.

**Rule 95. [특정 지역명 마케팅(예: 시칠리아산) 및 원재료명 국가명 강제 룰]**
   - [주표시면/마케팅]: 지역명이 강조된 경우 ⚠️(실무 확인 권장) 처리. 공장 주소를 산지로 착각하지 않도록 명시적 원산지 증명서 유무를 실무자가 확인하게 하십시오.
   - [정보표시면(원재료명)]: 뒷면 원재료명 란에는 무조건 법정 국가명(예: 이탈리아산)으로만 기재해야 합니다. 지역명(예: 시칠리아산)으로 적혀있다면 즉시 🚨부적합 처리하십시오.

**Rule 96. [유기가공식품 인증 마크 법정 CMYK 배색 비율 강제 점검 룰]**
   - 인증 마크는 지정된 CMYK 비율(예: 검은색은 C20+K100)을 1% 오차 없이 준수해야 하므로, AI는 눈으로만 판단하지 말고 ⚠️(실무 확인 권장) 처리하여 AI 일러스트 원본을 확인하도록 지시하십시오.

**Rule 97. [영양성분 표시단위 결정 프로세스 스마트 DB 내장 룰]**
   - 시안의 '식품유형'을 파악하여 아래 1회 섭취참고량을 자동 대입하라. (음료류: 200ml, 발효유: 80ml, 농후발효유: 150ml, 환자식: 200ml)
   - 총 내용량이 100g(ml)과 [1회 섭취참고량]을 모두 초과하는데 오직 '총 내용량당' 단독으로만 영양표를 표기했다면 명백한 불법(🚨부적합) 처리하라.

**Rule 98. [다단 표기 & 단위포장 프리패스 룰]**
   - 1) 제품이 '1포당, 1개당' 등 단위포장된 경우 참고량 초과를 따지지 말고 즉시 합법 처리하라.
   - 2) '1포당'과 '총 내용량당'이 2단으로 병기된 다단 레이아웃은 모범적인 합법 표기이며 수학적 교차 검증만 수행하라.

**Rule 99. [성역 없는 마케팅 vs 원재료 전체 크로스체크 룰]**
   - 패키지 어디에서든 '무가당, 무첨가, 100%' 마케팅 문구가 발견되면, 즉시 모든 이미지의 원재료명 텍스트를 샅샅이 뒤져 모순을 적발하라.
"""

def get_sliced_rules(rule_numbers):
    rules = []
    lines = RULE_BOOK_FULL.split("\n")
    current_rule = []
    is_capturing = False
    for line in lines:
        if line.startswith("**Rule"):
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

ALL_RULES_NUMBERS = list(range(1, 100))
RULES_TAB1 = "[탭 1. 주표시면 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB2 = "[탭 2. 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB3 = "[탭 3. 영양성분표 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)
RULES_TAB4 = "[탭 4. 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules(ALL_RULES_NUMBERS)

# ==========================================
# 메인 앱 로직
# ==========================================
def main():
    current_year = datetime.datetime.now().year
    current_date = datetime.datetime.now().strftime("%Y년 %m월 %d일")

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
    
    st.title("식품 표시사항 정밀 검토 시스템 (V350.4)")
    
    current_product = st.session_state.get("current_product_name", "지정되지 않음")
    st.markdown(f"#### **현재 검토 중인 제품:** `{current_product}`")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("검토 설정 및 파일 업로드")
        
        # 1. 기본 검토 조건 구역
        st.markdown("### 1. 기본 검토 조건")
        product_input = st.text_input("현재 검토 중인 제품명 (멀티태스킹 방지용)", "예: 세브란스케어 당밸런스 150")
        if product_input:
            st.session_state["current_product_name"] = product_input

        # 상태값(key) 연동 패치
        product_type = st.radio("식품유형", ("일반식품", "특수의료용도식품", "축산물"), key="product_type")
        inspection_mode = st.radio("검토 모드", ("단품 기본 검토", "선물세트 교차 검토"), key="inspection_mode")
        doc_type = st.radio("증빙 서류 형태", ("통합 엑셀/PDF", "개별 한글라벨"), key="doc_type")
        factory_allergens = st.text_area("공장 알레르기 마스터", "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류", key="factory_allergens")
        
        st.markdown("---")
        
        # 2. 패키지 시안 업로드 구역
        st.markdown("### 2. 패키지 시안 업로드")
        if inspection_mode == "선물세트 교차 검토":
            st.markdown("#### 📦 [타겟] 박스(외포장) 시안")
            img_main = st.file_uploader("1. 박스 주표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_info = st.file_uploader("2. 박스 정보표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_nutri = st.file_uploader("3. 박스 영양성분표", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_extra = st.file_uploader("4. 박스 기타면/측면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.markdown("#### 🧃 [비교용] 팩(내포장) 시안")
            box_main = st.file_uploader("1. 팩 주표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            box_info = st.file_uploader("2. 팩 정보표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            box_nutri = st.file_uploader("3. 팩 영양성분표", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            box_extra = st.file_uploader("4. 팩 기타면/측면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
        else:
            st.markdown("#### 📄 단품 패키지 시안")
            img_main = st.file_uploader("1. 시안 주표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_info = st.file_uploader("2. 시안 정보표시면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_nutri = st.file_uploader("3. 시안 영양성분표", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            img_extra = st.file_uploader("4. 시안 기타면/측면", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
            box_main = box_info = box_nutri = box_extra = None

        st.markdown("---")

        # 3. 참고용 증빙 서류 업로드 구역
        st.markdown("### 3. 참고용 증빙 서류")
        report_docs = st.file_uploader("시험성적서 (영양성분 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        label_docs = st.file_uploader("원료 스펙 (원재료 대조용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("배합비/레시피 데이터", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        
        with st.expander("수동 텍스트 입력 (선택사항)", expanded=False):
            st.info("텍스트가 빽빽해 인식이 어려울 경우 직접 복붙해 주세요.")
            st.session_state["manual_target"] = st.text_area("타겟(박스) 원재료명/영양정보 직접 입력", height=100)
            st.session_state["manual_compare"] = st.text_area("비교용(팩) 원재료명/영양정보 직접 입력", height=100)

        st.markdown("---")

        # 파일 업로드 병렬 처리 로직
        def get_uploaded_content():
            uploaded_items = []
            local_paths = []
            tasks = []
            def add_to_tasks(file_list, label_prefix):
                if not file_list: return
                for i, f in enumerate(file_list):
                    ext = os.path.splitext(f.name)[1] or ".png"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(f.getbuffer())
                        tasks.append((tmp.name, f"{label_prefix}_{i+1}"))
            
            add_to_tasks(img_main, "시안_주표시면")
            add_to_tasks(img_info, "시안_정보표시면")
            add_to_tasks(img_nutri, "시안_영양성분표")
            add_to_tasks(img_extra, "시안_기타면")
            add_to_tasks(box_main, "비교용_팩_주표시면")
            add_to_tasks(box_info, "비교용_팩_정보표시면")
            add_to_tasks(box_nutri, "비교용_팩_영양성분표")
            add_to_tasks(box_extra, "비교용_팩_기타면")
            add_to_tasks(report_docs, "근거_시험성적서")
            add_to_tasks(label_docs, "원료_한글라벨")
            add_to_tasks(recipe_docs, "배합비_레시피")

            def upload_worker(idx, task):
                file_path, label = task
                content_parts = [f"### [{label}] ###"]
                for attempt in range(3):
                    try:
                        up = genai.upload_file(file_path)
                        while up.state.name == "PROCESSING":
                            time.sleep(2)
                            up = genai.get_file(up.name) 
                        content_parts.append(up)
                        return idx, content_parts
                    except Exception as e:
                        if attempt == 2: return idx, [f"[업로드 에러] {label}: {e}"]
                        time.sleep(3)

            results = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(upload_worker, i, task) for i, task in enumerate(tasks)]
                for future in as_completed(futures):
                    results.append(future.result())
            results.sort(key=lambda x: x[0])
            for r in results:
                uploaded_items.extend(r[1])
            return uploaded_items, local_paths

        if st.button("전체 시스템 파일 연동 및 캐싱"):
            with st.spinner("파일을 구글 서버에 연동 중입니다..."):
                t_upload_start = time.time()
                content, paths = get_uploaded_content()
                if content:
                    st.session_state["uploaded_content"] = content
                    st.session_state["has_recipe"] = bool(recipe_docs)
                    st.session_state["has_labels"] = bool(label_docs)
                    try:
                        cache_contents = content + [f"\n\n========================================\n[식품 QC 마스터 룰북]\n{RULE_BOOK_FULL}"]
                        cache = genai.caching.CachedContent.create(
                            model=f"models/{MODEL_NAME}",
                            display_name="food_qc_cache",
                            system_instruction=SYSTEM_PROMPT,
                            contents=cache_contents,
                            ttl=datetime.timedelta(minutes=60)
                        )
                        st.session_state["qc_cache_name"] = cache.name
                        st.success(f"파일 연동 완료! (소요시간: {time.time() - t_upload_start:.1f}초)")
                    except Exception as e:
                        st.warning(f"캐싱 건너뜀 (일반 모드로 진행): {e}")

    # ==========================================
    # 핵심 로직 (구간별 시간 측정 타이머 추가)
    # ==========================================
    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_missions_list: list = None):
        if not st.session_state.get("uploaded_content"):
            st.warning("먼저 파일을 연동해주세요.")
            return None

        # 탭 전체 시작 시간 기록
        t_tab_start = time.time()
        
        use_cache = False
        cache_name = st.session_state.get("qc_cache_name")
        if cache_name:
            try:
                cache = genai.caching.CachedContent.get(cache_name)
                model_pro = genai.GenerativeModel.from_cached_content(cached_content=cache)
                use_cache = True
            except:
                pass
        
        if not use_cache:
            model_pro = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)

        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety_settings = [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}]

        def get_payload(prompt_text):
            if use_cache: return [prompt_text]
            return st.session_state["uploaded_content"] + [f"[룰북]\n{RULE_BOOK_FULL}"] + [prompt_text]

        extracted_text_combined = ""
        pass18_result = "맞춤법 검사 생략됨"
        verified_text = ""

        # ==========================================
        # Pass 1 (미션 분할 병렬 추출)
        # ==========================================
        if extract_missions_list:
            t_pass1_start = time.time()
            extracted_results = [None] * len(extract_missions_list)
            
            def run_single_mission(idx, mission):
                pass1_prompt = f"[PASS 1 - 단일 추출 미션]\n[미션]: {mission}\n절대 생략 금지, 100% 원문 타이핑."
                for attempt in range(3):
                    try:
                        resp = model_pro.generate_content(get_payload(pass1_prompt), generation_config=generation_config, safety_settings=safety_settings)
                        return idx, get_safe_text(resp), None
                    except Exception as e:
                        if "429" in str(e): # 429 에러(속도 제한) 디버깅용 메시지
                            print(f"[디버그] 미션 {idx+1}에서 429 에러 발생 (재시도 중...)")
                        if attempt < 2: time.sleep(10); continue
                        return idx, None, str(e)

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(run_single_mission, i, m) for i, m in enumerate(extract_missions_list)]
                for future in as_completed(futures):
                    idx, text, err = future.result()
                    if err: extracted_results[idx] = f"[오류 - 미션 {idx+1}]: {err}"
                    else: extracted_results[idx] = text
            
            extracted_text_combined = "\n\n".join([res for res in extracted_results if res is not None])
            t_pass1_elapsed = time.time() - t_pass1_start
            
            # UI에 Pass 1 시간 찍기
            st.info(f"[시스템 로그] Pass 1 (미션 {len(extract_missions_list)}개 동시 추출) 소요시간: {t_pass1_elapsed:.1f}초")

            # ==========================================
            # Pass 1.5 & Pass 1.8 (병렬 실행)
            # ==========================================
            t_pass15_start = time.time()
            def run_pass15():
                p = f"[PASS 1.5 - OCR 정제]\n원본을 문맥에 맞게 오타만 정제하라.\n[원본]\n{extracted_text_combined}"
                for _ in range(3):
                    try: return get_safe_text(model_pro.generate_content(get_payload(p), generation_config=generation_config))
                    except: time.sleep(10)
                return extracted_text_combined

            def run_pass18():
                p = f"[PASS 1.8 - 맞춤법]\n법적 판단 금지, 띄어쓰기와 오탈자만 지적하라.\n[원본]\n{extracted_text_combined}"
                model_flash = genai.GenerativeModel(MODEL_NAME_FLASH, system_instruction=SYSTEM_PROMPT)
                for _ in range(3):
                    try: return get_safe_text(model_flash.generate_content([p], generation_config=generation_config))
                    except: time.sleep(10)
                return "[맞춤법 에러]"

            with ThreadPoolExecutor(max_workers=2) as executor:
                f15 = executor.submit(run_pass15)
                f18 = executor.submit(run_pass18)
                verified_text = f15.result()
                pass18_result = f18.result()
            
            t_pass15_elapsed = time.time() - t_pass15_start
            st.info(f"[시스템 로그] Pass 1.5 & 1.8 (정제 및 맞춤법 동시 실행) 소요시간: {t_pass15_elapsed:.1f}초")

        # ==========================================
        # Pass 2 (최종 마크다운 렌더링)
        # ==========================================
        t_pass2_start = time.time()
        pass2_context = f"\n[정제본]\n{verified_text}\n[맞춤법 결과]\n{pass18_result}\n" if extract_missions_list else ""
        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
[시스템 현재 날짜 및 기준 연도]: {current_date} (현재가 {current_year}년임을 절대 잊지 마십시오.)
[제품유형]: {st.session_state.get("product_type", "일반식품")}
[검토모드]: {st.session_state.get("inspection_mode", "단품")}
[증빙서류 형태]: {st.session_state.get("doc_type", "통합 엑셀/PDF")}
[이 탭에 적용되는 핵심 룰]
{tab_rules}
{pass2_context}

🛑 [최고 수준 경고: 영역 침범 및 과잉 생성(오지랖) 절대 금지] 🛑
당신은 현재 요청받은 특정 탭(Tab)의 뼈대만 채우는 '국소적 표 생성기'입니다.
업로드된 모든 이미지를 다 볼 수 있더라도, 절대로 묻지 않은 다른 영역의 내용(예: 종합 결론, 원재료 1:1 대조표, 영양성분 계산표 등)을 임의로 창조하여 표 밑에 덧붙이지 마십시오. 
오직 아래 제시된 [출력 양식]의 표만 딱 완성한 후, 단 한 줄의 부연 설명이나 꼬리말도 없이 그 즉시 출력을 강제 종료(Stop)하십시오. (어길 시 치명적 에러 간주)

[가독성 향상 HTML 강제 명령]:
판정 및 사유 칼럼의 텍스트가 줄글로 뭉쳐지면 실무자가 읽기 매우 힘듭니다.
반드시 **<br>** 태그를 적극 사용하여 줄바꿈을 하고, **볼드체**를 활용하여 직관적으로 요약 작성하십시오.

[출력 양식] 
아래 뼈대만 복사하고 내용을 채울 것. (생략 금지)
{judgment_prompt}
"""
        final_clean_text = "[Pass 2 에러]"
        for attempt in range(3):
            try:
                resp = model_pro.generate_content(get_payload(pass2_prompt), generation_config=generation_config, safety_settings=safety_settings)
                final_clean_text = get_safe_text(resp)
                break
            except Exception as e:
                if attempt < 2: time.sleep(10); continue
                final_clean_text = f"[Pass 2 최종 오류]: {e}"
        
        t_pass2_elapsed = time.time() - t_pass2_start
        st.info(f"[시스템 로그] Pass 2 (최종 표 작성/판정 - 병렬불가 구간) 소요시간: {t_pass2_elapsed:.1f}초")
        
        t_tab_total = time.time() - t_tab_start
        st.success(f"해당 탭 연산 완료! (총 소요시간: {t_tab_total:.1f}초)")

        if extract_missions_list:
            return f"<clean_view>\n{final_clean_text}\n</clean_view>\n<pass1_log>\n{extracted_text_combined}\n</pass1_log>\n<pass15_log>\n{verified_text}\n</pass15_log>\n<pass18_log>\n{pass18_result}\n</pass18_log>"
        return final_clean_text

    def run_qc_model(prompt_text):
        if not st.session_state["uploaded_content"]:
            return None
            
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        
        dynamic_prompt = f"""
        [시스템 현재 날짜 및 기준 연도]: {current_date} (현재가 {current_year}년임을 절대 잊지 마십시오.)
        [제품유형]: {st.session_state.get("product_type", "일반식품")}\n[검토모드]: {st.session_state.get("inspection_mode", "단품")}\n[우리 공장 알레르기 마스터 목록]: {st.session_state.get("factory_allergens", "")}
        ========================================\n{prompt_text}
        """
        
        cache_name = st.session_state.get("qc_cache_name")
        if cache_name:
            try:
                cache = genai.caching.CachedContent.get(cache_name)
                model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                payload = [dynamic_prompt]
            except Exception as e:
                if "403" in str(e) or "404" in str(e):
                    return "**[캐시 만료 안내]**<br>파일 연동 후 60분이 초과되어 데이터가 지워졌습니다. 좌측 사이드바에서 캐싱 버튼을 다시 눌러주세요."
                model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                payload = st.session_state["uploaded_content"] + [f"[식품 QC 마스터 룰북]\n{RULE_BOOK_FULL}"] + [dynamic_prompt]
        else:
            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            payload = st.session_state["uploaded_content"] + [f"[식품 QC 마스터 룰북]\n{RULE_BOOK_FULL}"] + [dynamic_prompt]
            
        try:
            response = model.generate_content(payload, generation_config=generation_config)
            return fix_markdown_table(get_safe_text(response))
        except Exception as e:
            if "403" in str(e) or "404" in str(e) or "CachedContent" in str(e):
                return "**[캐시 만료 안내]**<br>파일 연동 후 60분이 초과되어 데이터가 지워졌습니다. 좌측 사이드바에서 캐싱 버튼을 다시 눌러주세요."
            return f"[시스템 런타임 오류 발생]: {e}"

    # 로그실(Expander) UI 복구 패치
    def display_result(result, tab_name=""):
        if not result: return
        
        clean_match = re.search(r'<clean_view>(.*?)</clean_view>', result, re.DOTALL)
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)
        pass18_match = re.search(r'<pass18_log>(.*?)</pass18_log>', result, re.DOTALL)

        if pass1_match or pass15_match or pass18_match:
            with st.expander(f"🕵️‍♂️ [시스템 로그실] {tab_name} 연산 원본 데이터 보기 (필요시 클릭)"):
                if pass18_match:
                    st.info("[PASS 1.8: 맞춤법 전용 스캐너 (Flash 모델 구동)]")
                    st.code(pass18_match.group(1).strip())
                if pass15_match:
                    st.info("[PASS 1.5: 자체 복원 및 OCR 노이즈 정제 완료본]")
                    st.code(pass15_match.group(1).strip())
                if pass1_match:
                    st.text("[PASS 1: 분할 미션 원본 추출 로그]")
                    st.code(pass1_match.group(1).strip())
            st.markdown("---")

        if clean_match:
            st.markdown(fix_markdown_table(clean_match.group(1).strip()), unsafe_allow_html=True)
        else:
            st.markdown(fix_markdown_table(result), unsafe_allow_html=True)

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["1. 주표시면", "2. 정보표시면", "3. 영양성분표", "4. 기타면/측면", "5. AI 법률 스캔", "6. 종합 보고서"])

    with tab1:
        if st.button("주표시면 분석 시작", key="btn_main"):
            with st.spinner("데이터 스캔 및 판정 중..."):
                missions = [
                    "[정밀 추출 명령]: 텍스트와 영양성분 수치 추출은 기본적으로 '주표시면(앞면)'에서 수행하되, '무(ZERO), 무첨가, 100%' 등 마케팅 클레임의 진위 여부(Rule 99)를 교차 검증하기 위해 반드시 뒷면의 '원재료명' 란 전체 텍스트를 전수 스캔하십시오.",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 앞면에 강조된 특정 영양소의 '% 기준치'를 교차 추출.",
                    "업로드된 서류에서 주표시면에 강조된 성분의 투입량(%)과 실측값(mg/g) 추출.",
                    "['MADE IN KOREA' 족집게 스캔]: K-MILK 로고 하단, 바코드 구석, 주의문구 주변 등에 'MADE IN KOREA'나 '한국산'이라는 영문/한글 텍스트가 픽셀 단위로 숨어있는지 샅샅이 스캔하십시오.",
                    "[점진적 탐색 및 룰 검증 명령 (인간의 시선 흐름)]: '국가 공인 인증 도안(HACCP 등)', '유기농 마크', '당 ZERO 등 영양강조 뱃지'를 검증할 때, 먼저 주표시면(앞면)을 확인하십시오.",
                    "▶ 주표시면에 없다면? 즉시 '해당 없음' 처리하지 말고, 함께 업로드된 다른 면(정보표시면, 기타면 등)의 이미지들을 순차적으로 스캔하십시오.",
                    "▶ 타 면에서 발견 시: '주표시면에는 없으나 [측면/정보표시면]에 HACCP 마크(또는 유기농 마크)가 존재합니다'라고 위치를 명확히 밝히십시오. 그리고 해당 마크가 텍스트 꼼수가 아닌 정식 도안으로 잘 표현되어 있는지(Rule 86, 56 등) 확인한 후 '✅ 적합' 판정을 내리십시오.",
                    "▶ 모든 면에서 미발견 시: 패키지 전체 이미지를 다 뒤져도 없을 경우에만 비로소 '패키지 전체 스캔 결과 해당 마케팅/인증 내역 없음'으로 사유를 적고 ✅ 적합(해당 없음) 처리하십시오."
                ]
                
                judgment_prompt = """## 1. [사전 연산: 당류 은폐 및 마케팅 팩트체크 추적]
(※ AI는 표를 작성하기 전에 반드시 시안 전체의 텍스트를 스캔하여 아래 질문에 단답형으로 대답하여 논리를 확정할 것)
1. 시안에 '무가당', '설탕 무첨가', '당 ZERO' 등의 마케팅 문구가 존재하는가? [YES / NO]
2. (위 질문이 YES일 경우) 원재료명 텍스트 전체(혼합제제 괄호 내부 포함)를 픽셀 단위로 스캔했을 때, '포도당', '시럽', '물엿', '덱스트린', '과당', '설탕' 글자가 단 한 글자라도 존재하는가? [YES / NO] (YES일 경우 정확히 어떤 단어인지 기재할 것. 예: 포도당시럽분말)

## 2. [주표시면 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 상세 사유 (오탈자 무관용, <br> 태그로 줄바꿈 필수) | 판정 |
| :--- | :--- | :--- | :--- |
| **제품명 및 특정 원료(특정균/숫자) 강조** | [Rule 9, 46, 53, 87] | | |
| **특정 지역명(시칠리아산 등) 마케팅 강조** | [Rule 95] | (※ 100% 해당 지역산 증빙서류 확인바람 문구 필수 출력) | |
| **강조 폰트 크기** | [Rule 71] | | |
| **조리예/이미지 사진 표기** | [Rule 72] | | |
| **보관상태(상온/냉동/냉장) 명시** | [Rule 62] | | |
| **190mL 전용 질소충전 동적 확인** | [Rule 63] | (※ 내용량이 190mL일 경우 시안에서 '질소충전' 글자를 스캔한 후 상황별로 사유 작성) | |
| **세트포장 앞면 총내용량/열량** | [Rule 3] | | |
| **세트포장 수량(X입/개) 기재 확인** | [Rule 57] | | |
| **다포장 낱팩 복붙 여부** | [Rule 68] | | |
| **원액/추출물 고형분 병기** | [Rule 50] | | |
| **영양강조 컷오프(4대 조건)** | [Rule 21, 52] | (※ 100g, 100mL, 100kcal, 1회섭취량 중 하나라도 충족하는지 수식으로 증명할 것) | |
| **마케팅 강조 문구 팩트체크 (전면 Cross-Check)** | [Rule 17, 19, 88, 99] | (※ 앞면에 '무(ZERO)', '무첨가', '100%' 등의 마케팅 클레임이 존재한다면, 사전 연산 1번과 2번의 결과를 종합하여 모순 적발할 것. 발견 시 기만행위 🚨부적합 사유 작성) | |
| **국가 공인 인증 도안 마케팅** | [Rule 86] | | |
| **유기농/친환경 마크 및 CMYK 색상 검증** | [Rule 84, 96] | (※ 마크 색상 일러스트 원본 확인바람 문구 필수 출력) | |
| **'MADE IN KOREA' 숨김 텍스트 스캔** | [Rule 94] | (※ K-MILK 마크 하단 등 구석구석 스캔하여 발견 시 즉시 검증) | |
| **오탈자 스캔 (명백한 글자 오류)** | 전수 검사 | (Pass 1.8의 오탈자 결과만 분리해서 기재) | |
| **띄어쓰기 스캔 (간격 오류)** | 전수 검사 | (Pass 1.8의 띄어쓰기 결과만 분리해서 기재) | |
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    with tab2:
        if st.button("정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("원재료 1:1 매칭 매트릭스 연산 중..."):
                has_recipe = st.session_state.get("has_recipe", False)
                has_labels = st.session_state.get("has_labels", False)
                has_any_doc = has_recipe or has_labels
                doc_mode = st.session_state.get("doc_type", "통합 엑셀/PDF")
                ins_mode = st.session_state.get("inspection_mode", "단품 기본 검토")

                missions = [
                    "시안(주표시면/정보표시면)에 기재된 원재료명, 알레르기 유발물질, 교차오염 주의문구, 행정 정보(제조원 등)를 모두 추출하십시오. (절대 말줄임표(...) 사용 금지)",
                    "시안에 기재된 원재료명 중 '식품첨가물'을 추출한 뒤, 하드코딩된 DB(표 4, 5, 6)와 대조하여 소속을 지정하십시오.",
                    "[절대 미션: 개별 단위 쪼개기 및 괄호 보존 법칙]: 추출한 원재료명을 쉼표(,)를 기준으로 개별 리스트로 쪼개되, 괄호 `()`나 대괄호 `[]` 안에 있는 쉼표는 절대 쪼개지 말고 한 덩어리로 무조건 유지하십시오. 시안 텍스트를 절대 축약하지 마십시오."
                ]
                
                if "선물세트" in ins_mode:
                    missions.append("[내외포장 1:1 분할 매칭 강제명령]: 타겟(박스) 시안과 비교용(팩) 시안의 원재료명 전체 텍스트를 표의 한 칸(행)에 뭉뚱그려 넣는 행위를 절대 금지합니다. 반드시 쉼표(,) 기준으로 각각의 원재료를 쪼개어, 표의 1개 행(Row) 당 1개의 원재료만 1:1 나란히 매칭되도록 길게 작성하십시오.")
                
                tab2_special_rules = RULES_TAB2 + """
                \n\n[Tab 2 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)]
                1. [서류 미제출 시 행동 강령 (중요!)]: 현재 업로드된 증빙 서류가 없다면, 마스터표 작성란에 **"⚠️ 한글라벨/서류 미제출로 인해 마스터표 미작성"**이라고만 명확히 출력하십시오.
                2. [단독 검토 모드 자가 검증 강제]: 
                   - 증빙 서류가 없을 경우 대조표의 '서류 매칭 원료' 칸에는 모두 **"⚠️ 서류 없음"**이라고 적으십시오.
                   - **그러나 절대 검토를 포기하지 마십시오!** 오직 시안에 적힌 텍스트 자체만 보고, [Rule 14: 첨가물 용도명 기재 방식], [Rule 89, 95: 원산지/지역명 표기법] 등 범용적인 식품표시기준 규정에 위배됨이 없는지 스스로 검증하여 사유와 판정(✅적합 또는 🚨부적합)을 반드시 내리십시오.
                3. [박스 vs 팩 1:1 맵핑 강제 (Rule 70 적용)]: 선물세트 모드일 경우, 타겟(박스)과 팩(내포장) 텍스트가 100% 똑같더라도 절대 생략하거나 합치지 말고, 반드시 1개씩 쪼개어 1열씩 1:1 비교표를 완성하십시오.
                4. [투트랙 유연한 맵핑]: 당류/시럽류(`당류가공품`), 올리고당류, 첨가물은 문맥상 일치하면 억지 불일치 처리하지 말고 합법 치환(✅)으로 인정하십시오.
                """

                judgment_prompt = "## [사전 연산: 원산지 Rank B 및 혼합제제 해체 알고리즘]\n"
                judgment_prompt += "(AI는 아래 5단계를 단답형으로 100% 명확히 작성하여 논리를 확정한 후 대조 표를 작성할 것)\n"
                judgment_prompt += "1. **[Rank B 제외 대상 필터링]**: [삭제 원료명]\n"
                judgment_prompt += "2. **[Rank B Top 3 확정]**: (배합비율 없으면 시안 나열 순서대로 강제 추론) 1위: [ ], 2위: [ ], 3위: [ ]\n"
                judgment_prompt += "3. **[Rule 1: 98% 컷오프 예외 판정]**: \n"
                judgment_prompt += "4. **[Rule 89/95 타겟 락온]**: \n"
                judgment_prompt += "5. **[복합원재료 vs 혼합제제 전개 라우팅]**: \n\n"

                if doc_mode == "개별 한글라벨":
                    if has_any_doc:
                        judgment_prompt += "## 2-1. [서류 기반 원재료 마스터표 생성]\n| No | 배합비 순위 (Rank A) | 서류상 원재료명 | 배합비율(%) | 서류상 원산지 | 비고 (식품유형/혼합제제 하위성분 등) |\n|---|---|---|---|---|---|\n\n"
                    else:
                        judgment_prompt += "## 2-1. [서류 기반 원재료 마스터표 생성]\n**⚠️ 한글라벨/증빙 서류 미제출로 인해 마스터표 대조 기준 미작성**\n\n"
                else:
                    judgment_prompt += "## 2-1. [서류 기반 원재료 마스터표 생성]\n**(※ 통합 엑셀/PDF 서류 모드이므로 마스터표 생략 - 2-2 대조표로 직행)**\n\n"

                if "선물세트" in ins_mode:
                    judgment_prompt += "## 2-2. [내외포장 원재료명 1:1 대조 검증 (절대 생략 금지)]\n"
                    judgment_prompt += "주의: 타겟(박스)과 팩(내포장)의 텍스트가 100% 동일하더라도 표를 생략하거나 '내용 동일'로 퉁치지 마십시오. 모든 원재료를 쉼표(,) 기준으로 분리하여 1열씩 1:1로 끝까지 대조하십시오.\n"
                    judgment_prompt += "| No | 타겟(박스) 시안 원재료명 | 비교용 팩(내포장) 시안 원재료명 | 상세 사유 (타이포그래피 차이는 합법 처리) | 판정 |\n|---|---|---|---|---|\n\n"

                table_title = "## 2-3. [원재료명 1:1 정밀 대조 및 법규 검증]\n" if "선물세트" in ins_mode else "## 2-2. [원재료명 정밀 대조 및 법규 검증]\n"
                judgment_prompt += table_title
                judgment_prompt += "| No | 시안 원재료명 (표시 순서대로) | 서류 매칭 원료 | 상세 사유 (서류 없으면 시안 단독 규정 검증) | 판정 |\n|---|---|---|---|---|\n\n"
                
                judgment_prompt += "## 2-4. [알레르기 및 교차오염 완벽 검증]\n"
                judgment_prompt += "| 검토 항목 | 타겟(시안) 텍스트 | 상세 사유 및 교차오염 뺄셈 공식 증명 | 판정 |\n|---|---|---|---|\n"
                judgment_prompt += "| **알레르기 유발물질 (직접 투입)** | | | |\n"
                judgment_prompt += "| **교차오염 주의문구** | | | |\n\n"
                
                judgment_prompt += "## 2-5. [행정 및 기타 의무 표시사항]\n"
                judgment_prompt += "| 검토 항목 | 시안 텍스트 | 상세 사유 | 판정 |\n|---|---|---|---|\n"
                judgment_prompt += "| **품목보고번호/식품유형** | | | |\n"
                judgment_prompt += "| **영업소 명칭 및 소재지** | | | |\n"
                judgment_prompt += "| **부정/불량식품 신고 문구** | | | |\n"
                judgment_prompt += "| **분리배출 표시** | | | |\n"

                st.session_state["result_tab2"] = run_qc_3pass(tab2_special_rules, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    with tab3:
        if st.button("영양성분표 수치 자동 환산 및 대조", key="btn_nutri"):
            with st.spinner("영양성분 수치 역산 및 오차 매트릭스 검증 중..."):
                has_recipe = st.session_state.get("has_recipe", False)
                has_labels = st.session_state.get("has_labels", False)
                has_any_doc = has_recipe or has_labels
                ins_mode = st.session_state.get("inspection_mode", "단품 기본 검토")

                missions = [
                    "시안(영양성분표)에 기재된 1회 섭취량, 총 내용량, 각 영양소별 함량 및 1일 영양성분 기준치 비율(%)을 빠짐없이 추출하십시오.",
                    "시험성적서(통합 엑셀 또는 PDF)에서 100g 또는 100mL 당 영양성분 실측치(결과값)를 추출하십시오."
                ]
                if "선물세트" in ins_mode:
                     missions.append("[내외포장 1:1 분할 매칭 강제명령]: 타겟(박스) 시안과 비교용(팩) 시안의 영양성분표 수치를 표의 한 칸에 뭉뚱그려 넣지 마십시오. 반드시 각각의 영양성분(열량, 나트륨 등)을 1열씩 1:1로 나란히 매칭되도록 길게 표를 작성하십시오.")
                
                tab3_special_rules = RULES_TAB3 + """
                \n\n[Tab 3 특별 지시사항 (반드시 지킬 것 - 화면 출력 금지)]
                1. [영양소 순서 100% 고정]: 영양정보표는 반드시 **[열량, 나트륨, 탄수화물, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤, 단백질]** 순서로 출력하십시오. 시안에 다른 순서로 적혀있다면 🚨부적합 처리하십시오. (비타민, 미네랄 등은 단백질 이후에 배치)
                2. [단방향 허용오차 완벽 계산 (Rule 11)]: 성적서 실측값을 기준 삼아 1.2를 곱하는 멍청한 계산을 절대 하지 마십시오. **반드시 시안의 '표시량'을 기준으로 상한선(120%)과 하한선(80%) 커트라인을 구한 뒤, 실측값이 그 커트라인을 통과하는지(보수적 표기 합법성)를 평가하십시오.**
                3. [산수 오류 원천 봉쇄]: 열량 계산 시 애트워터 계수(탄4, 단4, 지9)를 적용하여 시안의 열량이 합법적인지 다각도로 교차 검증하십시오.
                4. [0 표기 및 불검출 룰 (Rule 23 적용)]: 실측값이 식약처 규정 미만(예: 나트륨 5mg 미만, 트랜스지방 0.2g 미만)일 경우, 시안에 0g/0mg으로 적혀 있는 것은 완벽한 합법입니다. 오차범위 초과라고 오판하지 마십시오.
                5. [다단 표기 & 단위포장 프리패스 (Rule 97, 98)]: 총 내용량이 1회 섭취참고량을 초과하더라도, 제품이 '1포당', '1개당' 등으로 개별 단위포장 되어있다면 기준 초과를 따지지 말고 즉시 합법(✅) 처리하십시오. 또한 '1팩당'과 '총내용량당'이 나란히 병기되어 있는 다단 레이아웃은 규정을 완벽히 준수한 모범 사례이므로 지적하지 마십시오.
                6. 🛑 [총 내용량 꼼수 계산 절대 금지]: '총 내용량당' 수치와 오차를 검증할 때, 절대 '1회 섭취량(1컵, 1개 등)'의 시안 표기량에 배수(x N)를 곱해서 도출하지 마십시오! 반드시 원본 [시험성적서 100g/mL 당 실측치]를 총 내용량 비율에 맞게 처음부터 다시 곱하여 정확한 기준값을 도출한 뒤 비교하십시오. (1회 섭취량의 반올림 오차가 누적 뻥튀기되는 것을 방지하기 위함입니다.)
                """

                judgment_prompt_tab3 = ""
                if "선물세트" in ins_mode:
                    judgment_prompt_tab3 += "## 3-1. [내외포장 영양성분표 1:1 대조 (절대 생략 금지)]\n"
                    judgment_prompt_tab3 += "| 영양성분명 | 타겟(박스) 1개당 시안 | 비교용(팩) 1개당 시안 | 상세 사유 (타이포그래피 차이는 합법 처리) | 판정 |\n|---|---|---|---|---|\n\n"
                
                if has_any_doc:
                    title_prefix = "3-3." if "선물세트" in ins_mode else "3-2."
                    
                    judgment_prompt_tab3 += f"## {title_prefix} [사전 연산: 생성해야 할 표 목록 확정 (절대 생략 금지)]\n"
                    judgment_prompt_tab3 += "[절대 명령]: 영양정보표 시안에 '1컵당'과 '총 내용량당'처럼 단위가 2개 이상 나란히 병기되어 있다면, 절대로 하나만 검사하고 끝내지 마십시오! 반드시 각각의 단위에 대해 독립된 표를 모두 생성하여 이중 검증해야 합니다.\n\n"
                    judgment_prompt_tab3 += "1. **시안에 존재하는 '맛/종류' 목록**: (실제 이름을 그대로 나열. 예시가 아니라 시안에 적힌 텍스트 그대로. 1개뿐이면 1개만 적을 것)\n"
                    judgment_prompt_tab3 += "2. **각 맛마다 실제로 병기된 '표시 단위' 개수 및 명칭**: (예: '1컵(80g)당' 1개, '총 내용량(320g)당' 1개 -> 총 2개 단위 확인됨)\n"
                    judgment_prompt_tab3 += "3. **[생성해야 할 표 목록]**: (맛 × 단위 조합을 하나씩 번호 매겨 전부 나열하라. 단위가 2개면 표도 무조건 2개 나와야 한다.)\n"
                    judgment_prompt_tab3 += "   - 표 1: [맛A] - [단위1]\n"
                    judgment_prompt_tab3 += "   - 표 2: [맛A] - [단위2]\n"
                    judgment_prompt_tab3 += "   - ... (실제 개수만큼 계속)\n"
                    judgment_prompt_tab3 += "4. **[총 표 개수 확정]**: 위에서 나열한 줄 수 = **N개**\n\n"

                    judgment_prompt_tab3 += "## [영양표시 오차 검증 매트릭스]\n"
                    judgment_prompt_tab3 += "[절대 명령]: 위 3번 목록에 적힌 순서 그대로, 목록에 있는 항목 이름을 표 제목에 그대로 복사하여 정확히 N개의 표를 만들어라.\n"
                    judgment_prompt_tab3 += "- 목록에 있는 표를 하나라도 빠뜨리면 안 된다. (특히 '총 내용량당' 표를 생략하면 치명적 오류 간주)\n"
                    judgment_prompt_tab3 += "- '총 내용량당' 수치 검증 시, 1회 섭취량 표기량에 배수(xN)를 곱하는 꼼수를 절대 쓰지 말고, 반드시 성적서(100g당) 실측값을 기준으로 총 내용량(총 중량) 비율에 맞게 재산출할 것.\n\n"

                    judgment_prompt_tab3 += "### [표 순번] [목록에서 그대로 가져온 맛-단위 이름]\n"
                    judgment_prompt_tab3 += "| 영양성분 | 성적서 환산값(A) | 시안 표시량(B) | 허용오차 커트라인 | 1일 기준치 % 검증 | 상세 사유 | 판정 |\n|---|---|---|---|---|---|---|\n\n"
                    judgment_prompt_tab3 += "(※ 위 표 뼈대를 목록의 N개 항목 순서대로 정확히 N번 복제하여 이어서 작성. 표마다 제목만 목록의 해당 항목으로 교체할 것.)\n\n"

                    judgment_prompt_tab3 += "## [출력 직전 자기 검증 (필수)]\n"
                    judgment_prompt_tab3 += "- 위 사전 연산 3번에서 확정한 표 개수(N): [ ]\n"
                    judgment_prompt_tab3 += "- 방금 실제로 그린 표 개수: [ ]\n"
                    judgment_prompt_tab3 += "- 두 숫자가 일치하는가? [YES/NO] (NO라면 누락된 표를 지금 즉시 추가로 작성할 것)\n\n"
                else:
                    judgment_prompt_tab3 += "## 3-2. [영양표시 오차 검증]\n(※ 성적서 미제출로 실측 오차 검증 생략)\n\n"

                st.session_state["result_tab3"] = run_qc_3pass(tab3_special_rules, judgment_prompt_tab3, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    with tab4:
        if st.button("기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("기타면 주의사항 및 텍스트 검증 중..."):
                missions = [
                    "시안(기타면/측면)에 기재된 모든 주의사항 문구, 제품 설명 텍스트, 품질보증 문구, 소비자 상담실 정보 등을 하나도 빠짐없이 전수 추출하십시오.",
                    "[절대 명령]: 추출한 문장 내에 있는 쉼표, 마침표, 줄바꿈 등을 임의로 수정하지 말고 원본 픽셀 그대로 타이핑하십시오."
                ]
                
                judgment_prompt = """## 4. [기타면/측면 법적 주의사항 검증]
| 검토 항목 | 관련 룰(Rule) | 시안 텍스트 | 상세 사유 (오탈자 무관용, <br> 태그로 줄바꿈 필수) | 판정 |
| :--- | :--- | :--- | :--- | :--- |
| **액상 음료 주의문구 강제 스캔** | [Rule 74] | | (※ 식품유형이 '음료류'인지 '우유류'인지 판단하여 사유 작성) | |
| **CS 방어용 주의문구 (침전물/팽창 등)** | [Rule 75] | | | |
| **식품유형별 법정 의무 주의문구** | [Rule 77] | | (※ 당알코올 주의, 렌지 가열 금지 등) | |
| **OEM 업소명 타이틀 및 축산물 종속성 검증** | [Rule 76] | | (※ 축산물인데 '유통전문판매원'으로 적었는지 집중 타격) | |
| **영양표시 하단 면책 문구 토시 대조** | [Rule 81] | | | |
| **특수의료용도식품 영양공급 문구** | [Rule 78] | | | |
| **수출 겸용 소재지 '대한민국' 표기 확인** | [Rule 93] | | | |
| **오탈자 스캔 (명백한 글자 오류)** | 전수 검사 | | (Pass 1.8의 오탈자 결과만 분리해서 기재) | |
| **띄어쓰기 스캔 (간격 오류)** | 전수 검사 | | (Pass 1.8의 띄어쓰기 결과만 분리해서 기재) | |
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    with tab5:
        if st.button("AI 법무팀장 자유 스캔 시작", key="btn_law"):
            with st.spinner("AI 법률 엔진 가동: 표시광고법 및 판례 기반 심층 스캔 중..."):
                free_style_prompt = """## 5. [AI 법무팀장 특별 감사 리포트 (자율 심층 스캔)]
당신은 대한민국 최고의 식품 전문 변호사이자 규제 당국(식약처)의 깐깐한 심사관입니다.

🛑 [절대 주의사항: 타 부서 영역 침범 금지] 🛑
- 단순 오탈자(예: 유유 -> 우유), 띄어쓰기, 영양성분 수치 계산 오류(콜레스테롤 오차 등)는 다른 부서(탭 1~3)에서 이미 모두 적발했습니다.
- 이 5번 탭에서는 **절대로 단순 오탈자나 수치 계산 오류를 중복으로 지적하지 마십시오.** (발견하더라도 철저히 무시하십시오)
- 오직 패키지의 **'마케팅 문구', '디자인', '강조 표시(예: 저지방, 100% 등)'**가 식품표시광고법상 기만행위나 과대광고에 해당하는지만 심층 분석하십시오.

[절대 명령]: 반드시 아래 두 가지 파트로 나누어 리포트를 작성하십시오.

### 1. 🎯 [마케팅 소구점 및 소비자 오인 분석]
- 패키지 전반에 걸친 마케팅/디자인 강조 문구("저지방", "100%", 유기농 표방, 특정 타겟층 명시 등)를 심층 스캔하십시오.
- 해당 마케팅 문구가 소비자를 기만하거나 오인하게 할 여지가 없는지 통찰력 있게 분석하여 줄글로 서술하십시오.

### 2. ⚖️ [표시광고법 및 규제 위반 리스크 스캔]
- 질병 예방/치료 효능 표방, 건강기능식품 오인, 거짓/과장 광고 등 법적 철퇴를 맞을 수 있는 리스크를 찾아내 표로 브리핑하십시오. (리스크가 없으면 '특이사항 없음'으로 출력)

| 적발된 리스크 (Risk) | 발견 위치 및 문구 | 관련 법령 및 판정 근거 (상세 사유) | 방어 및 수정 제안 |
|---|---|---|---|
"""
                st.session_state["result_tab5"] = run_qc_model(free_style_prompt)
        display_result(st.session_state["result_tab5"], "AI법률스캔")

    with tab6:
        if st.button("종합 결과 요약 리포트 생성", key="btn_summary"):
            with st.spinner("전체 검토 결과 집계 및 경영진 보고서 작성 중..."):
                summary_prompt = """## 6. [식품 표시사항 종합 검토 리포트]
지금까지 분석한 1~5번 탭의 모든 결과를 종합하여, 실무자 및 경영진이 한눈에 파악할 수 있도록 핵심만 요약한 마크다운 리포트를 작성하십시오.
1. **[총평]**: 전체적인 시안의 법적 안정성 평가 (매우 우수 / 양호 / 주의 / 위험)
2. **[즉시 수정 필요 (부적합)]**: 과태료나 리콜 대상이 될 수 있는 치명적 위반 사항 요약
3. **[실무 확인 요망]**: 규정 위반은 아니나, 폰트 크기, 마크 색상, 보수적 표기 안전율 등 인간의 눈으로 최종 확인해야 할 사항
4. **[모범 준수 사항]**: 디자이너나 실무자가 규정을 아주 훌륭하게 방어해 낸 점 (칭찬 포인트)
"""
                st.session_state["result_summary"] = run_qc_model(summary_prompt)
        display_result(st.session_state["result_summary"], "종합보고서")

if __name__ == "__main__":
    if check_password():
        main()
