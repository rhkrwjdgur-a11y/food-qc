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
MODEL_NAME = "gemini-2.5-pro"

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
# 🧬 [첨가물 표 4, 5, 6 하드코딩 DB (환각 방지용)]
# ==========================================
ADDITIVE_TABLE_4 = [
    "사카린나트륨", "수크랄로스", "아스파탐", "아세설팜칼륨", "식용색소적색제2호", "식용색소적색제3호", 
    "식용색소적색제40호", "식용색소황색제4호", "식용색소황색제5호", "식용색소청색제1호", "식용색소청색제2호",
    "아질산나트륨", "소브산", "소브산칼륨", "안식향산", "안식향산나트륨", "에리토브산", "아황산나트륨", "효소처리스테비아"
]
ADDITIVE_TABLE_5 = [
    "카라멜색소", "카라멜색소I", "카라멜색소II", "카라멜색소III", "카라멜색소IV", "치자청색소", "치자황색소", 
    "홍화황색소", "적양배추색소", "파프리카추출색소", "안나토추출물", "차아염소산나트륨", "구아검", "잔탄검", 
    "펙틴", "카라기난", "로커스트콩검", "알긴산나트륨", "결명자추출물"
]
ADDITIVE_TABLE_6 = [
    "L-글루탐산나트륨", "구연산", "구연산나트륨", "빙초산", "탄산나트륨", "탄산수소나트륨", "제이인산칼륨", 
    "제삼인산칼슘", "수산화나트륨", "젖산", "젖산나트륨", "말토덱스트린", "글리세린"
]

# ==========================================
# 📚 2. 시스템 지시어
# ==========================================
SYSTEM_PROMPT = f"""당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
당신에게는 창의성, 추론 능력, 융통성이 전혀 없습니다. 오직 화면에 보이는 픽셀 단위의 글자(Text)만 있는 그대로 읽고 기계적으로 1:1 대조하는 봇(Bot)입니다.

🔥 [식품첨가물 표기 특별 통제 족쇄]: 
원재료명 란의 첨가물을 판정할 때, 반드시 아래 하드코딩된 DB를 먼저 대조하여 판정하십시오.
* [표 4 소속 (명칭+용도 병기 강제, 누락시 🚨부적합)]: {ADDITIVE_TABLE_4}
* [표 5 소속 (명칭 또는 간략명만 표시, 용도 생략해도 ✅합법)]: {ADDITIVE_TABLE_5}
* [표 6 소속 (명칭, 간략명, 주용도 중 선택 표시 ✅합법)]: {ADDITIVE_TABLE_6}

🔥 [오탈자 무관용 및 환각 차단 원칙]: 의미가 통하더라도 룰북에 명시된 관용명/동의어 허용 규칙에 해당하지 않으면서 글자나 기호가 다르면 무조건 부적합 처리하십시오.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 사유를 반드시 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 87대 마스터 룰북 원문 (V310.80 완결본)
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

🔥 **Rule 1. [원산지 3순위 산정 제외 및 임의 분류 금지]**
   - 정제수(물), 주정, 당류, 첨가물은 배합비율이 높아도 원산지 산정에서 100% 제외됩니다.
   - 나한과추출분말 등을 이름만 보고 임의로 식품첨가물로 오판하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 개별 향료명이 명시되어 있어도, 시안 원재료명에 단순히 '향료'로 묶어 표기 가능. (단, Rule 85 참고)

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 강제 룰]**
   - 주표시면(앞면)에 특정 영양소 함량이 강조되어 있다면, 뒷면 영양성분표 수치와 단 1의 오차도 없이 100% 일치해야 합니다.
   - 세트 포장의 주표시면에는 '총 내용량'과 '총 열량(kcal)'이 모두 기재되어야 합니다.

✅ **Rule 4. 영양성분 실측값 허용**
   - 허용 오차 범위 내 성적서 실측값 반영 합법.

🔥 **Rule 5. [복합원재료 5가지 컷오프 및 첨가물 생략 합법성 룰 (유권해석 기반)]**
   - **[조건 A: 5% 미만]**: 배합비 5% 미만인 복합원재료는 괄호를 열고 하위 성분을 전개할 의무가 아예 없으므로 생략 합법(✅).
   - **[조건 B: 5가지 컷오프]**: 배합비가 5% 이상인 복합원재료의 경우, 하위 성분 중 **'물을 제외하고 많이 사용한 순서대로 5가지'**만 명시되어 있다면 나머지 일반 원료 생략은 합법(✅).
   - 🌟 **[조건 C: 5순위 밖 첨가물 생략 면제]**: 식약처 유권해석(2025.07)에 의거, 복합원재료 내 하위 순위(6순위 이하)에 해당하는 식품첨가물(착색료, 감미료 등)은 **완제품에 기능적 영향을 발휘하더라도 표기를 완전히 생략하는 것이 합법(✅)**입니다. (기존 Carry-over 강제 부활 표기 예외 인정)

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

🔥 **Rule 13. [알레르기 정밀 추적 및 위치 표기 절대 규칙]**
   - 바탕색과 구분되는 '별도 란(박스)'에 기재 필수.

🔥 **Rule 14. [첨가물 교차 검증]**
   - 식품첨가물은 원재료명 표시란에 반드시 법적 기준(표4, 5, 6)에 맞게 표기해야 함.

✅ **Rule 15. [기능성 오인 문구 및 신체 조직 작용 전면 통제]**
   - '소화불편감 완화' 등 인체의 기능·작용·효과를 직접 암시하거나 기만하는 표현 전면 금지(🚨부적합).

✅ **Rule 16. [원산지 100% 표기 룰]**
   - 단일 국가 100% 수입 원료만 100% 강조 가능.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지 첨가물 배제 강조 시 부적합(🚨).

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 영유아 타겟 명칭 사용 적발.

✅ **Rule 19. ['무당' vs '무가당' 분리 검증]**
   - 무당: 0.5g 미만 / 무가당: 인위적 첨가 없을 때.

🔥 **Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무 없음.

🔥 **Rule 21. ['고/풍부', '저', '무' 영양강조표시 엄격 컷오프 및 비중세탁 금지 룰]**
   - **['고', '풍부' 표시 기준]**: 
      1) **단백질, 식이섬유**: 기준치의 20%(100g당) / 10%(100mL당) / 10%(100kcal당) / 20%(1회섭취량당) 이상.
      2) **비타민 및 무기질**: 기준치의 30%(100g당) / 15%(100mL당) / 10%(100kcal당) / 30%(1회섭취량당) 이상.
   - **['저' 표시 기준]**: 열량(100g당 40kcal 미만 또는 100mL당 20kcal 미만), 나트륨(100g당 120mg 미만) 등.
   - **['무(Zero)' 표시 기준]**: 열량(100mL당 4kcal 미만), 나트륨/지방/당류(5mg/0.5g/0.5g 미만).
   ⭐ **[부적합 시 수학적 증명 족쇄]**: 반드시 4가지 조건의 수식을 모조리 나열하여 4가지 모두 기준치 미달임을 증명해야 부적합.
   - 🚨 **[액체 비중 세탁 영구 봉쇄]**: 내용량을 'mL' 단위로 유통하는 액체 식품은 무조건 **'100mL당'** 기준선만 적용.

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 함.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 및 반올림 예외 절대 규정]**
   - 트랜스지방 0.2g 미만은 "0g" 표시. 냉장 흰우유 유통기한 예외 인정(✅).

🔥 **Rule 24. [당류 강조표시 연계 의무 표기 룰]**
   - 무당/저당 강조 시 열량 병기 의무, 감미료 함유 문구 기재 확인.

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

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 투입량 2% 미만 원료는 순서가 달라도 합법.

🔥 **Rule 35. [🌟 범용 간략명/관용명/동의어 허용 및 N종 묶음 절대 금지]**
   - **[관용명/동의어 합법 처리]**: 식약처 공전 및 식품유형상 허용되는 동의어나 관용명 표기는 100% 합법(✅) 처리함. (예: 옥배유 = 옥수수기름, 황백당/원당 = 갈색설탕, 채종유 = 대두유 등)
   - **[내부 식별 코드/띄어쓰기 생략]**: 서류상의 납품업체 전용 식별코드(예: E(30), -2 등)나 단순 띄어쓰기 생략은 완벽한 합법(✅)으로 간주함.
   - 혼합제제 괄호 내부를 '산도조절제 2종' 등으로 숫자로 묶어 은폐하는 것은 명백한 위법(🚨부적합). 단, 향료의 '합성향료 2종' 등 숫자는 합법(✅).

🔥 **Rule 36. [주의사항 오탈자 스캔]**
   - 오탈자 정밀 검수.

✅ **Rule 37. [법적 서류 우선 고려]**
   - Rule 35 예외 우선 고려.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증]**
   - ⭐ **[강제 수식]**: `[교차오염 정답지] = [공장 취급 마스터] - [직접 투입 알레르기]` 도출 증명.

🔥 **Rule 39. [동명 원료 및 식품유형 종속성 분리 룰]**
   - 명칭이 같아도 [식품유형]이 다르면 분리 표기.

🔥 **Rule 40. [열량 표기 및 반올림 원칙]**
   - 세트 총 열량은 실측 소수점을 합산하여 5kcal 단위로 반올림.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - 열량(kcal)과 트랜스지방은 %를 표기하지 않습니다.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 최종 완제품 기준 데이터만 사용.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독 어려우면 임의 판정 금지.

🔥 **Rule 44. [혼합제제 전개 및 해체 병합 완벽 허용 룰]**
   - 혼합제제는 괄호를 깨고 흩어지게 적어도 완벽 합법(✅).

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
   - **['함유', '급원', 단순 명칭 강조 표시 기준]**:
      1) **단백질, 식이섬유**: 기준치의 10%(100g당) / 5%(100mL당) / 5%(100kcal당) / 10%(1회섭취량당) 이상.
      2) **비타민 및 무기질**: 기준치의 15%(100g당) / 7.5%(100mL당) / 5%(100kcal당) / 15%(1회섭취량당) 이상.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 제품명에 농수산물이 쓰이면 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성]**
   - 단일 원료 2개국 병기 시 비율 생략 확인 요망.

🔥 **Rule 55. [영양성분 소수점 및 반올림 강제 규정]**
   - 포화지방 5g 이상은 소수점 없이 정수 표시.

🔥 **Rule 56. [HACCP 인증 마크 공식 텍스트 검증]**
   - "안전관리인증", "식품안전관리인증" 확인.

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

🔥 **Rule 62. [축산물 보관상태 의무 표시]**
   - 냉장/냉동 상태 명시.

🔥 **Rule 63. [미드팩 질소충전 확인]**
   - 190mL 팩 질소충전 문구 확인.

🔥 **Rule 64. [원물 기만표시 스나이퍼]**
   - 강조 비율이 추출액 비율이면 기만(🚨).

🔥 **Rule 65. [내부 식별 코드 생략 합법성]**
   - `-2` 등 내부 코드는 생략 합법.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 복붙 스나이퍼]**
   - 박스 시안 영양표시가 낱팩 용량 그대로면 복붙 에러(🚨).

🔥 **Rule 70. [내/외포장 원재료명 100% 일치 강제 범용 스나이퍼]**
   - 내/외포장 텍스트 픽셀 단위 대조 다르면 부적합(🚨).

🔥 **Rule 71. [강조 폰트 크기 규정]**
   - 원료 함량 14pt 육안 확인 알림.

🔥 **Rule 72. ['조리예/이미지 사진' 점검]**
   - 연출 사진 텍스트 스캔.

🔥 **Rule 73. [세부 재질 스나이퍼]**
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
   - 박스 영양정보표 상단에 `총 내용량 OOO mL (OOO mL X O개입)` 및 `1개당` 포맷 확인.

🔥 **Rule 81. [영양표시 하단 면책 문구 토시 대조]**
   - 면책 문구 기호 100% 일치 확인.

🔥 **Rule 82. [영양소 법정 단위 엄격 검증]**
   - 비타민 단위 등 특수기호 100% 대조.

🔥 **Rule 83. [영양성분 % 병기 강제 범용 스나이퍼]**
   - 기준치 존재 성분 옆에 비율(%) 병기 필수.

🔥 **Rule 84. [유기농/친환경 단어 원천 봉쇄 스나이퍼 룰]**
   - '유기농', '유기' 단어가 있으면 반드시 인증 마크 + 95% 이상 함량 조건 충족.

🔥 **Rule 85. [식품첨가물 공전 명칭 사수 및 기호 창조 절대 금지]**
   - 명칭 축약 엄격 금지, 괄호 외 임의 기호 창조 전면 금지(🚨).

🔥 **Rule 86. [국가 공인 인증 도안 기만 및 텍스트 편법 규제 룰]**
   - 도안 미사용 텍스트 편법 적발 시 부적합(🚨).

🔥 **Rule 87. [특정균 강조 표시 및 균수 분리 기재 합법성 룰]**
   - 특정균 사용 시 주표시면 배합함량(%), 정보표시면 균수(CFU) 분리 기재 합법(✅).
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

ALL_RULES_NUMBERS = list(range(1, 88))
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
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V310.80 - 측면/기타면 영양스캔 고도화 패치)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        with st.expander("⚙️ 고급 설정 (수동 텍스트 입력)", expanded=False):
            st.info("💡 텍스트가 너무 빽빽해서 AI가 글자를 빼먹는다면, 디자이너 원본 텍스트 복붙해 주세요.")
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
                        extracted_results.append(pass1_response.text)
                        break
                    except Exception as e:
                        if "504" in str(e) or "Deadline" in str(e) or "503" in str(e):
                            if attempt < max_retries - 1:
                                time.sleep(10)
                                continue
                        return f"🚨 Pass 1 오류 발생: {e}"
            
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
                    verified_text = pass15_response.text
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

🔥 [최종 출력 양식 및 절대 강제 족쇄] 🔥
아래 제시된 [출력 양식]을 단 한 줄도 삭제하거나 변형하지 말고, 100% 그대로 복사한 뒤 내용만 표의 빈칸에 채워 넣어 출력하십시오. 지정된 탭의 검토 항목 외에 다른 영역을 침범하는 월권행위를 절대 금지합니다.

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
                final_clean_text = pass2_response.text
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
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        full_prompt = f"""
        [제품유형]: {product_type}\n[검토모드]: {inspection_mode}\n[우리 공장 알레르기 마스터 목록]: {factory_allergens}
        {RULE_BOOK_FULL}\n========================================\n{prompt_text}
        """
        try:
            response = model.generate_content(st.session_state["uploaded_content"] + [full_prompt], generation_config=generation_config)
            return fix_markdown_table(response.text)
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
                    "주표시면(앞면) 이미지에서 '제품명, 내용량, 칼로리, 마케팅 강조문구'만 리스트로 정확히 추출하십시오.",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 앞면에 강조된 특정 영양소의 '% 기준치' 추출.",
                    "업로드된 서류에서 주표시면에 강조된 성분의 투입량(%)과 실측값(mg/g) 추출.",
                    "시안 전체에서 원재료명 리스트를 찾아 추출하십시오."
                ]
                judgment_prompt = """## 1️⃣ [주표시면 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 검토 결과 및 사유 (오탈자 무관용) | 판정 |
| :--- | :--- | :--- | :--- |
| **제품명 및 특정 원료(특정균) 강조 기준** | [Rule 9, 53, 87] | | |
| **강조 폰트 크기** | [Rule 71] | | |
| **조리예/이미지 사진 표기** | [Rule 72] | | |
| **보관상태(냉동/냉장) 명시** | [Rule 62] | | |
| **세트포장 앞면 총내용량/열량** | [Rule 3] | | |
| **다포장 낱팩 복붙 여부** | [Rule 68] | | |
| **원액/추출물 고형분 병기** | [Rule 50] | | |
| **영양강조 컷오프(4대 조건)** | [Rule 21, 52] | | |
| **국가 공인 인증 도안 마케팅** | [Rule 86] | | |
| **극단적 픽셀 대조 (오탈자/공백)** | 전수 검사 | | |
| **유기농/친환경 마크 검증** | [Rule 84] | | |
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【원재료 1:1 매칭 매트릭스 연산 중...】"):
                missions = [
                    "오직 '타겟(박스) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "오직 '비교용(팩) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "시안에 기재된 원재료명 중 '식품첨가물'을 추출한 뒤, 하드코딩된 DB나 문서에서 해당 첨가물 명칭을 대조하십시오. 그리고 [표 4], [표 5], [표 6] 중 정확히 어느 표에 속해 있는지 소속을 명확히 지정하여 추출하십시오.",
                    "정보표시면의 '알레르기 유발물질', '교차오염 주의문구', 'CS 주의문구' 추출.",
                    "정보표시면의 행정 정보(제조원, 유통전문판매원, 포장재질 등) 추출.",
                    "증빙 서류의 모든 원료명, 하위 성분, 원산지, 배합비(%)를 추출하십시오."
                ]
                
                base_tab2_warning = """⭐ [1:1 대조 예외 절대 원칙 (Rule 35. 관용명/동의어, 내부 식별코드 생략, 유기농 생략 완벽 합법 우선 적용)] ⭐\n🔥 [시스템 절대 족쇄: 월권행위 금지] 🔥\n이 탭은 오직 '원재료명, 첨가물, 알레르기, 행정정보'만 검토하는 탭입니다. 영양정보, 내용량, 소비기한, 바코드 등은 다른 탭의 소관이므로 여기서 절대 판정 항목으로 나열하지 마십시오.\n"""
                common_tab2_prompts = """## 2️⃣-1. [서류 기반 마스터 원재료 DB]
| 서류상 원료명 | 하위 전개 성분 | 원산지 | 배합비(%) / 비고 |
|---|---|---|---|

## 2️⃣-2. [마스터 서류 vs 시안 법적 대조 매트릭스]
| 시안 표기 원재료명 (100% 나열) | 매칭된 서류 원료명 (없으면 '제출 안 됨') | 대조 검증 결과 (Rule 5 적용 및 Rule 35 관용명 허용 포함) | 최종 판정 |
|---|---|---|---|

### 🚨 [식품첨가물 범용 형식주의 스나이퍼 (Rule 85 강력 적용)]
- **[명칭 축약 및 용도 표시 검사 결과]**: (※ 반드시 표 4, 5, 6 DB 소속을 확인한 뒤 판정할 것)
- **[임의 기호 창조 검사 결과]**: 

### 🚨 [서류 기준 최종 누락 스나이퍼 검증 (Anti-Join)]
- 적발 양식: "🚨 [누락]: 서류의 'OOO' 원료가 시안에서 완전히 누락되었습니다."
- 이상 없을 시: "✅ 서류상 누락된 원료 없음."

## ⚖️ 3️⃣ [배합비 기반 2% 룰 및 전개 순서 정밀 검증 (Rule 34)]
(전개 순서 및 2% 룰 적용 결과 요약 기재)

## 4️⃣ [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38 적용)]
- [공장 마스터 목록]: 
- [직접 투입된 알레르기]: 
- [도출된 교차오염 정답지]: 
- [시안 표기 문구]: 
- [최종 판정 및 사유]: 

## 🏛️ 5️⃣ [행정 정보 교차 검증]
- ⭐ [Rule 76] 유통전문판매원/판매원 타이틀 강제 확인:
"""
                judgment_prompt = base_tab2_warning + common_tab2_prompts
                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【허용오차 검증 매트릭스 가동 중...】"):
                missions = [
                    "타겟(박스) 시안의 영양정보표 내부 수치와 표 바깥의 총 내용량, 칼로리, '1일 영양성분 기준치' 문구 전부 추출.",
                    "비교용(팩) 시안이 있다면 영양정보표 내부 수치와 바깥 문구 전부 추출.",
                    "시험성적서 서류에서 각 영양성분의 실측값 데이터 추출."
                ]
                
                judgment_prompt = """## 3️⃣ [영양표시 오차 검증 및 % 기준치 확인]
| 영양성분 | 성적서 환산값(A) | 시안 표시량(B) | 법적 기준선 (B의 80% 또는 120%) | 🎯 % 계산 검증 | 판정 및 상세 사유 (수식 증명 필수) |
|---|---|---|---|---|---|

## 🔍 [영양성분표 치명적 레이아웃 및 뼈대 스나이퍼]
- ⭐ [Rule 80] 박스 포장 상단 레이아웃 확인: 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
- ⭐ [Rule 83] 기준치 존재 성분 % 병기 룰 대조:
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【의무표시 및 인증마크 해독 중...】"):
                missions = [
                    "전 구역 이미지를 스캔하여 필수 의무표시 3종(상담번호, 교환처, 1399 문구)과 HACCP 인증 마크 추출.",
                    "알레르기 직접 함유 표시(바탕색 별도 박스) 및 분리배출 마크 추출.",
                    "포장재질 표기(세부 재질 포함) 및 CS 방어/기타 주의문구 추출.",
                    "특정균(비피더스 등)의 균수 표기 문구가 기타면에 별도로 적혀있는지 추출.",
                    "기타면/측면 이미지에서 '단백질', '비타민', '칼슘' 등 특정 영양소를 강조하는 마케팅 뱃지나 텍스트가 있는지 스캔하여 추출하십시오."
                ]
                judgment_prompt = """## 4️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 정밀 검증]
| 검토 항목 | 검토 룰(Rule) | 검토 결과 및 사유 (오탈자 무관용) | 판정 |
| :--- | :--- | :--- | :--- |
| **의무표시 3종 Global Scan** | [Rule 59] | | |
| **기타면 영양강조표시 스나이퍼** | [Rule 21, 52] | | |
| **알레르기 교차오염 검증** | [Rule 38] | | |
| **HACCP 마크 공식 명칭** | [Rule 56] | | |
| **특정균 균수 분리 표시 의무** | [Rule 87] | | |
| **용기 세부 재질 스나이퍼** | [Rule 73] | | |
| **액상 음료 개봉 후 주의문구** | [Rule 74] | | |
| **CS 클레임 방어용 문구** | [Rule 75] | | |
| **범용 식품유형 필수 주의문구** | [Rule 77] | | |
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    with tab5:
        st.info("💡 [AI 자율 스캔 모드] 기계적 검증(1~4번 탭)이 잡아내지 못하는 문맥상의 위법성, 과대광고, 소비자 기만 행위를 법령 PDF를 기반으로 심층 스캔합니다.")
        if st.button("▶️ AI 법률 자문 자율 스캔 시작", key="btn_law"):
            with st.spinner("【법률 스캔 중: 마케팅 리스크 및 맹점 추적...】"):
                missions = [
                    "업로드된 시안에서 '12년 연속 1등', '특허', '효능 표방', '미래 시점(날짜) 포함 문구' 등 마케팅 카피, 제품명, 강조 문구, 뱃지 디자인만을 정밀 스캔하여 추출하십시오. (원재료명, 영양성분 숫자, 띄어쓰기는 추출 금지)",
                    "추출된 마케팅/광고 요소들이 「식품등의 표시·광고에 관한 법률」 및 고시상 부당광고(소비자기만, 허위과대광고, 객관적 근거 결여 등)에 해당하는지 업로드된 법령 PDF에서 관련 조항을 검색하여 추출하십시오."
                ]
                
                judgment_prompt = """## 5️⃣ [AI 법률 자문 자율 스캔 리포트]
⭐ [월권행위 절대 금지 및 맹점 추적 명령] ⭐
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
"""
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])

if __name__ == "__main__":
    if check_password():
        main()
