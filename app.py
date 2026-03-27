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
# 🛡️ AI 표 깨짐 강제 복구 함수
# ==========================================
def fix_markdown_table(text):
    text = re.sub(r'([^\n])\s*(\|\s*No\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*영양성분명\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'\|\s+\|', '|\n|', text)
    return text

# ==========================================
# 📚 2. 통합 전문가 프롬프트 (시스템 지시어)
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 이모지를 붙이십시오.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 문서에 없는 데이터를 임의로 지어내는 환각(Hallucination)을 엄격히 통제합니다."""

# ==========================================
# 📚 3. 55대 룰북 원문 
# ==========================================
RULE_BOOK = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## 🚨 [⚖️ 1일 영양성분 기준치 (외부 데이터 개입 차단 및 비율 규칙)] 🚨
주의: 사전 학습된 글로벌 데이터(예: 칼슘 1000mg 등) 적용을 금지합니다. 오직 아래 명시된 **한국 식약처 기준치**만 대입하여 %를 산출해야 합니다.
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

**[🚨 비율(%) 표기 절대 규칙]:** 산출된 비율 값은 무조건 소수점 첫째 자리에서 반올림하여 정수(1% 단위)로 표시합니다. 
**[🚨 1% 미만 예외 규칙]:** 단, 비율이 1% 미만으로 나온 경우 임의로 0%로 적지 말고, 반드시 **"1% 미만"**이라고 텍스트 그대로 표기하십시오. (단, 함량 자체가 '0g' 예외 규정에 해당하여 0g으로 적힌 경우에 한해서만 0%로 표기합니다.)

## ⚠️ 검토 대원칙: 55대 품질관리 지침 (단 한 글자도 생략 없이 엄수할 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽한 적합입니다.

✅ **Rule 3. 영양정보 vs 강조표시 (이원화 대조)**
   - 영양성분표의 수치와 주표시면의 마케팅 강조 문구가 서로 충돌하지 않는지 대조하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 적합으로 인정하십시오. 

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다. 감미료나 향료가 생략되었더라도 지적하지 마십시오.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g이면, 실제 0.5g 미만인지 검증하십시오.

✅ **Rule 7. 감미료 주의문구 (조건부 발동)**
   - 당알콜류 사용 시 설사 관련 주의 문구 누락 여부를 확인 및 지적하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 국가명 대신 '외국산' 또는 '수입산'으로 표기해도 적합합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되었는지 확인하십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 심사하십시오.

🔥 **Rule 11. [영양정보 허용오차 산술 연산 법칙 (역산 오류 방지)]**
   - **[🚨역산 금지]**: 무조건 **'시안 표시량'에 0.8 또는 1.2를 곱하여** 법적 기준선을 도출하십시오.
   - **[80% 이상 합법 그룹 (비타민, 무기질, 단백질 등)]**: (성적서 환산 실측값) >= (시안 표시량 * 0.8) 이면 적합(✅).
   - **[120% 미만 합법 그룹 (열량, 당류, 지방 등)]**: (성적서 환산 실측값) <= (시안 표시량 * 1.2) 이면 적합(✅). 

✅ **Rule 12. [원재료명 3단 교차 검증 및 임의 추론 금지]**
   - 배합비 데이터 없이 레시피를 상상하거나 임의로 지적하지 마십시오. 

🔥 **Rule 13. [알레르기 정밀 추적 및 위치 오판 방지]**
   - 시안의 **"~함유"** 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 존재해야 합니다. (원재료에 없는데 적혀있으면 🚨부적합)
   - **[🚨알레르기 위치 표기 절대 규칙]: 식약처 규정상 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 한 번만 기재되어 있으면 100% 합법입니다. '영양성분표 하단'이나 다른 곳에 중복 표기를 요구하는 환각(Hallucination)을 엄격히 금지합니다.**

🔥 **Rule 14. [표 4 및 표 6 의무/예외 표기 마스터 룰 (묶음 표기 허용)]**
   - **[🚨향료 괄호 관련 임의 지적 금지]**: '향료' 뒤에 '(착향료)' 용도명을 병기하라고 지적하는 것을 엄격히 금지합니다.
   - **[표 6 묶음 표기 적합성]**: 구연산나트륨 등을 묶어서 시안에 **"영양강화제 2종"**처럼 표기하는 것은 완벽 적합(✅)입니다.

✅ **Rule 15. [기능성 오인 문구 스캔]**
   - 건강기능식품으로 오인할 수 있는 효능 문구를 스캔하여 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가에서 100% 수입된 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 사용이 원천 금지된 첨가물을 배제했다고 강조한 경우 기만광고로 부적합(🚨) 처리하십시오.

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 일반 식품에 영유아를 타겟으로 하는 명칭(예: 베이비, 아기) 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 분리 검증]**
   - '무당'은 당류 0.5g 미만, '무가당'은 인위적 당류 첨가가 없을 때 적합합니다.

✅ **Rule 20. [포장재질 직접 접촉 원칙]**
   - 포장재질 텍스트 란에는 **'식품과 직접 접촉하는 내면 재질'**만 기재하는 것이 원칙입니다.

🔥 **Rule 21. [비타민/무기질 영양강조 다중 조건 연산]**
   - 칼슘 등 강조 시 4가지 기준(100g, 100mL, 100kcal, 1회 섭취참고량) 중 **단 하나라도 충족하면 적합(✅)**합니다. 

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. 단, 상표 로고는 예외입니다.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 예외 규정]**
   - **트랜스지방:** 0.2~0.5g 미만은 **"0.5g 미만"** 표시.
   - **콜레스테롤:** 2~5mg 미만은 **"5mg 미만"** 표시.
   - **포화지방 등:** 0.5g 미만은 "0g" 표시 시 적합.

🔥 **Rule 24. [감미료 14pt 의무 표기 및 다중 강조표시 규칙]**
   - 무당/제로 강조 시 14포인트 이상 크기로 "감미료 함유"를 표시해야 합니다. 
   - **[🚨다중 강조 시 위치 강제]: 단, 당류 강조표시(ZERO, 무당 등)가 시안에 2회 이상 반복되어 있는 경우에는, 반드시 "가장 큰 강조표시 주위"에 감미료 함유 문구를 기재해야 합니다.** 만약 1회만 표시되었거나, 뱃지가 가장 큰 강조표시 주위에 배치되어 있다면 뱃지 형태라도 적합(✅)합니다. 무조건 뱃지라고 부적합 처리하지 마십시오.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위와 총 내용량 수치를 명확히 분리하여 대조 검증하십시오.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 중량(g), 액체는 용량(mL)으로 적절히 표기되었는지 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등 제한 성분은 100kcal 당 조건을 적용하지 마십시오.

🔥 **Rule 28. [원산지 과잉 지적 금지]**
   - 배합비 하위 성분까지 과도하게 전개하여 원산지를 추가 요구하지 마십시오. 단, Rule 53에 해당하는 제품명 연동 원료는 예외입니다.

🔥 **Rule 29. [복합원재료 원산지 표시 한계]**
   - 복합원재료 자체의 원산지만 확인하십시오.

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.** ✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 여러 성적서가 제공된 경우 모든 영양성분을 누락 없이 병합하여 대조하십시오.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 균형 열량 구성비의 단순 역산 결과만으로 부적합 처리하지 마십시오.

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치를 명확히 구분하여 리포트를 작성하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 배합비 기준 2% 미만 원료는 기재 순서가 달라도 적합으로 판정하십시오.

✅ **Rule 35. [서류 명칭 일치(간략명) 허용]**
   - 의미상 동일한 간략 명칭은 적합 처리하십시오.

✅ **Rule 36. [주의사항 오탈자 스캔]**
   - 필수 주의사항 문구의 오탈자를 정밀 검수하십시오.

✅ **Rule 37. [법적 서류 우선 원칙]**
   - 증빙 서류(배합비, 성적서) 데이터를 최우선 기준으로 판별하십시오.

🔥 **Rule 38. [교차오염 경고 상호 배타성 원칙]**
   - 원재료로 이미 투입된 성분을 '제조시설 공유(교차오염)' 주의사항에 중복 기재하면 부적합. 반대로 원재료에 없는 물질을 알레르기 '~함유' 칸에 기재해도 부적합입니다.

✅ **Rule 39. [동명 원료 종속성 원칙]**
   - 복합원재료 각각을 별도로 독립 대조 검증하십시오.

✅ **Rule 40. [열량 표기 및 반올림 원칙]**
   - 열량은 그 값을 그대로 표시하거나 가장 가까운 5kcal 단위로 반올림하여 표시하십시오.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 및 외부 데이터 차단]**
   - 비율(%) 계산 시 외부 데이터(해외 기준)를 절대 사용하지 마십시오. 프롬프트 상단의 [1일 영양성분 기준치]에 명시된 한국 식약처 수치만 대입하십시오.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 완제품 기준의 최종 시험성적서 데이터만 사용하십시오.

✅ **Rule 43. [시각적 한계 명시]**
   - 이미지 픽셀 저하로 글자 판독이 도저히 어려우면 임의 판정하지 말고 "육안 재확인 요망"으로 처리하십시오.

✅ **Rule 44. [혼합제제 하위성분 전개 적합성]**
   - 혼합제제 구성 성분이 올바르게 하위 전개되었는지 확인하십시오.

✅ **Rule 45. [선택적 누락 허용]**
   - 필수 법정 표시사항이 아닌 마케팅적 선택 누락은 굳이 지적하지 마십시오.

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자가 포함된 경우 관련된 하위 전개 내역을 대조 스캔하십시오.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 룰]**
   - 내포장(팩)과 외포장(박스)의 **'원재료명'과 '영양성분' 텍스트는 100% 일치**해야 합니다.
   - **[🚨물리적 차이 예외 인정]**: 단, 소비기한 표기 위치(상단 vs 측면) 등 용기 특성에 따른 물리적 문구 차이는 적합(✅)으로 인정합니다.

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(투입량 순서 기준)와 한글라벨(최종 명칭 기준)의 역할을 명확히 분리하여 검증하십시오.

🔥 **Rule 49. [균형영양식 강제 전개 적합성]**
   - 혼합제제를 해체하여 원료별로 병합 전개하는 것은 합법적입니다.

🔥 **Rule 50. ['원액/100%' 명칭 표시 적합성 판별]**
   - **[✅적합 조건]**: 납품받은 특정 원료 자체가 100% 순수 원액이라면, 최종 제품 공정에서 타 첨가물과 배합되더라도 원료명에 'OO원액' 명칭 사용이 가능합니다.
   - **[🚨부적합 조건]**: 원료 자체 스펙에 이미 정제수나 부형제가 혼합되어 있음에도 마케팅 면에 묶어서 '100% 원액'으로 과장한 경우 엄격히 부적합 처리하십시오.

🔥 **Rule 51. [데이터 1:1 매칭 및 고형분(Brix) 보수적 표기 예외]**
   - 제공된 문서의 시안 텍스트와 서류 데이터를 1:1로 매칭하십시오. 
   - **[🚨고형분 함량 예외 인정]**: 단, 과일 농축액 등의 **'고형분 함량(%)' 표기 시, 시안 수치가 서류 실제 스펙보다 같거나 낮게 표기된 경우(예: 서류 72.74% ➔ 시안 70%)는 안전역 확보 보수 표기이므로 무조건 적합(✅)** 판정하십시오. 서류보다 수치를 높게 뻥튀기한 경우에만 부적합(🚨) 처리하십시오.

🔥 **Rule 52. [논리적 모순 탐지 및 정합성 검증]**
   - 제품명이나 마케팅 문구에 특정 숫자(예: '23곡', '15종', '5無')가 명시되어 있다면, 괄호 안 원재료명에 나열된 실제 항목의 개수(쉼표 개수 기반)와 **논리적/수학적으로 정확히 일치하는지 반드시 대조 카운트하십시오.**

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰 (🚨농산물 원물 한정)]**
   - 주표시면(앞면)의 **'제품명'에 특정 원재료의 명칭**이 포함되어 있는지 스캔하십시오.
   - 포함되어 있다면 다음 2가지를 강제 대조 검증하십시오.
     1) **함량 검증 (모든 원료 공통):** 주표시면에 해당 원료의 함량(%)이 명확히 명시되어 있는지 확인하십시오. (누락 시 🚨 부적합)
     2) **원산지 검증 (🚨진짜 농수산물 원물만 해당):** 해당 원료가 **'진짜 농수산물(예: 딸기, 고구마, 밤, 우유, 돼지고기, 쌀 등 자연 원물)'**인 경우에만 정보표시면에 원산지가 기재되어 있는지 검증하십시오. (누락 시 🚨 부적합)
     - **[✅가공품 원산지 면제]:** 만약 제품명에 쓰인 원료가 진짜 원물이 아니라 **'가공품(예: 코코아분말, 페이스트, 농축액, 추출액 등)'**이거나 첨가물이라면, 원산지 의무 표기 대상이 아니므로 정보표시면에 원산지가 누락되어 있어도 적합(✅)으로 판정하십시오.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성 검증 룰]**
   - 정보표시면 원재료명에 단일 원료에 대해 2개 이상의 국가가 쉼표(,)로 병기되어 있고(예: 가나산, 에콰도르산), **각 국가별 혼합 비율(%)이 기재되어 있지 않은 경우** 덮어놓고 적합(✅)으로 판정하지 마십시오. 반드시 🚨(확인 요망) 플래그를 띄우고 부서 확인을 지시하십시오.

🔥 **Rule 55. [영양성분 소수점 및 반올림 강제 규정]**
   - 포화지방 5g 이상은 소수점 없이 정수로, 트랜스지방 0.2g 미만은 소수점 없이 0g으로 표시해야 합니다. 시안에 소수점이 기재되어 있다면(예: 8.0g ➔ 8g 수정 필요 / 0.0g ➔ 0g 수정 필요) 부적합(🚨) 처리하십시오.
"""

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    # 🔒 세션 스테이트(메모리) 초기화
    if "result_tab1" not in st.session_state: st.session_state["result_tab1"] = None
    if "result_tab2" not in st.session_state: st.session_state["result_tab2"] = None
    if "result_tab3" not in st.session_state: st.session_state["result_tab3"] = None
    if "result_tab4" not in st.session_state: st.session_state["result_tab4"] = None
    if "result_summary" not in st.session_state: st.session_state["result_summary"] = None

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

    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V54.0 - 구조화된 딥-띵킹 패치)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        product_type = st.radio("📌 1. 식품유형", ("일반식품", "특수의료용도식품 / 환자식"))
        inspection_mode = st.radio("📌 2. 검토 모드", ("단품(개별 팩) 검토", "선물세트 교차 검토"))
        
        st.markdown("---")
        img_main = st.file_uploader("1️⃣ 주표시면(앞면)", type=["jpg", "png", "jpeg"])
        img_info = st.file_uploader("2️⃣ 정보표시면(뒷면)", type=["jpg", "png", "jpeg"])
        img_nutri = st.file_uploader("3️⃣ 영양성분표", type=["jpg", "png", "jpeg"])
        img_extra = st.file_uploader("4️⃣ 기타면/측면 (선택)", type=["jpg", "png", "jpeg"])
        
        st.markdown("---")
        report_docs = st.file_uploader("📑 시험성적서", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("📑 배합비(또는 한글라벨)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        legal_docs = st.file_uploader("📑 한글라벨(기타)", type=["pdf", "jpg", "png"], accept_multiple_files=True)

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
        if img_extra: process(img_extra, "시안_기타면_측면")
        if report_docs: 
            for f in report_docs: process(f, "근거_시험성적서")
        if recipe_docs: 
            for f in recipe_docs: process(f, "근거_서류(배합비/한글라벨)")
        if legal_docs: 
            for f in legal_docs: process(f, "근거_추가서류")
            
        for f in glob.glob("temp_*"): os.remove(f)
        return user_content

    def run_qc_model(prompt_text):
        content = get_uploaded_content()
        if not content:
            st.warning("🚨 업로드된 파일이 없습니다. 파일을 먼저 업로드해 주십시오.")
            return None
            
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
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
        
        아래의 55대 상세 룰북을 철저히 숙지하여 판단하되, **가장 마지막에 지시된 [절대 수행 임무]의 양식만을 반드시 출력**해야 합니다.
        
        {RULE_BOOK}
        
        ========================================
        🚨 [절대 수행 임무 및 출력 템플릿 강제] 🚨
        당신은 지금 선택된 탭의 임무만 수행해야 합니다. 지시되지 않은 다른 번호의 양식을 출력하면 시스템이 파괴됩니다.
        
        {prompt_text}
        """
        
        try:
            response = model.generate_content(content + [full_prompt], generation_config=generation_config, safety_settings=safety_settings)
            fixed_text = fix_markdown_table(response.text)
            return fixed_text
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1️⃣ 주표시면", 
        "2️⃣ 정보표시면", 
        "3️⃣ 영양성분표", 
        "4️⃣ 기타면/측면",
        "📊 5️⃣ 종합 보고서"
    ])

    with tab1:
        st.info("주표시면 이미지와 배합비를 대조하여 마케팅 문구, 함량 표기, 제로 강조 및 감미료 표기 위치 등을 검토합니다.")
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("주표시면 텍스트 및 뱃지 정밀 대조 중..."):
                prompt = """
                [지시]: 오직 '주표시면'에 대한 리뷰만 출력하십시오. 
                🚨 [1단계: 사전 판단(Thinking) 강제] 🚨
                리뷰를 출력하기 전에 반드시 `<thinking>` 태그를 열어 분석하십시오.
                <thinking>
                (마케팅 문구, 뱃지 위치 등 사전 분석 내용 기록)
                </thinking>
                🚨 [2단계: 정식 리포트 출력] 🚨
                ## 1️⃣ [주표시면 및 마케팅 뱃지]
                - 결론: (✅ 적합 또는 🚨 부적합/확인요망)
                - 🚨 [Rule 24] 감미료 함유 문구 위치 적합성: 
                - 100% 원액 및 고형분 강조 적합성: 
                - 마케팅 숫자(N종, N곡 등) 정합성: 
                - 제품명 연동 함량(%) 표기 여부: 
                - 기타 특이사항 (과장광고 등): 
                """
                st.session_state["result_tab1"] = run_qc_model(prompt)

        if st.session_state["result_tab1"]:
            result = st.session_state["result_tab1"]
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
            if thinking_match:
                thinking_log = thinking_match.group(1).strip()
                report_content = result.replace(thinking_match.group(0), "").strip()
                with st.expander("🧠 주표시면 마케팅 뱃지 및 위치 추론 로그 보기"):
                    st.markdown(f"*{thinking_log}*")
                st.markdown(report_content)
            else:
                st.markdown(result)

    # ==========================================================
    # 탭 2: 정보표시면 검토 (V54 구조화된 딥-띵킹 적용)
    # ==========================================================
    with tab2:
        st.info("정보표시면 이미지와 한글라벨, 배합비를 대조하여 원재료명, 원산지, 알레르기를 전수 검토합니다.")
        if st.button("▶️ 정보표시면 원재료 100% 대조 시작", key="btn_info"):
            with st.spinner("서류 분석 및 원재료 1:1 정밀 대조 중... (최대 40초 소요)"):
                prompt = """
                [지시]: 오직 아래의 원재료명 표와 알레르기 교차검증 양식만 출력하십시오.
                
                🚨 [1단계: 서류 분석 및 구조화된 1:1 매칭 (Structured Thinking 강제)] 🚨
                `<thinking>` 태그를 열고 원재료를 꼼꼼하게 대조하되, 시스템 멈춤을 방지하기 위해 **서술형 문장을 절대 쓰지 말고 '키워드 단답형'과 '화살표(->)' 방식**으로만 기록하십시오. 충분히 길게 생각해도 좋으나 포맷은 반드시 지키십시오.
                
                <thinking>
                - [배합비 % 유무 파악]: (O/X 기록)
                - [원재료 1:1 매칭 작업 시작]:
                  * 시안(코코아분말) -> 서류(코코아 100% / 네덜란드)
                  * 시안(마카다미아) -> 서류(마카다미아페이스트 / 호주)
                  (이런 식으로 모든 원료를 서술형 없이 짧게 1:1 맵핑만 수행)
                </thinking>
                
                🚨 [2단계: 정식 리포트 및 표 렌더링] 🚨
                ## 2️⃣ [원재료명 및 원산지 대조]
                - 결론: (✅ 적합 또는 🚨 부적합)
                (🚨 절대 경고: 아래 표를 작성할 때 무조건 파이프(|) 기호를 사용하십시오.)
                [🟢 올바른 표 작성 예시]
                | No | 시안 원재료명 | 서류 매칭 원료 (품번, 스펙 등) | 배합비 검증 (모르면 생략) | 판정 및 사유 |
                |---|---|---|---|---|
                | 1 | 코코아분말 | 코코아 100% (네덜란드) | 서류 내 % 미상 | ✅ 적합 (Rule 53 적용: 가공품이므로 원산지 표기 의무 없음) |
                
                (여기에 위 예시를 참고하여 시안에 적힌 모든 원료를 대조하는 표를 그리십시오.)
                
                - [Rule 53, 54 검토 사항]: (제품명 연동 원료 함량/원산지 등 별도 서술)
                
                ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
                - 결론: (✅ 적합 또는 🚨 부적합)
                - '~함유' 물질 원재료명 실존 여부:
                - 교차오염 경고 중복/모순 여부:
                """
                st.session_state["result_tab2"] = run_qc_model(prompt)

        if st.session_state["result_tab2"]:
            result = st.session_state["result_tab2"]
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
            if thinking_match:
                thinking_log = thinking_match.group(1).strip()
                report_content = result.replace(thinking_match.group(0), "").strip()
                with st.expander("🧠 서류 1:1 구조화 매칭 로그 보기"):
                    st.markdown(f"*{thinking_log}*")
                st.markdown(report_content)
            else:
                st.markdown(result)

    with tab3:
        st.info("영양성분표 이미지와 시험성적서를 대조하여 9대 영양소의 허용오차율 및 식약처 1일 기준치를 계산합니다.")
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("영양성분 오차 수식 계산 및 표 렌더링 중..."):
                prompt = """
                🚨 [최고 수준 경고]: 당신은 지금 [3번 탭: 영양성분표 검토] 전용 모드입니다. 
                🚨 [1단계: 사전 판단(Thinking) 강제] 🚨
                표를 그리기 전에 반드시 `<thinking>` 태그를 열어 오차율을 계산하십시오. 서술형 문장 없이 공식만 짧게 적으십시오.
                <thinking>
                (9개 성분의 허용오차 기준선 및 1일 기준치 비율 계산식 기록)
                </thinking>
                🚨 [2단계: 정식 표 렌더링] 🚨
                ## 4️⃣ [영양표시 및 % 기준치 검증]
                - 결론: (✅ 적합 또는 🚨 부적합)
                (🚨 절대 경고: 파이프(|) 기호를 사용하여 마크다운 표 형태를 완벽하게 유지하십시오.)
                [🟢 올바른 표 작성 예시]
                | 영양성분명 | 성적서 실측값 | 시안 표시량 | 법적 허용오차 기준선 | 1일 기준치 | 시안 % | % 검증 | 판정 |
                |---|---|---|---|---|---|---|---|
                | 나트륨 | 15mg | 20mg | 18mg 미만 | 2000mg | 1% | 적합 | ✅ 적합 |
                
                (여기에 표를 작성하십시오.)
                """
                st.session_state["result_tab3"] = run_qc_model(prompt)

        if st.session_state["result_tab3"]:
            result = st.session_state["result_tab3"]
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
            if thinking_match:
                thinking_log = thinking_match.group(1).strip()
                report_content = result.replace(thinking_match.group(0), "").strip()
                with st.expander("🧠 영양소 산술 연산 로그 보기"):
                    st.markdown(f"*{thinking_log}*")
                st.markdown(report_content)
            else:
                st.markdown(result)

    with tab4:
        st.info("선물용 박스, 트레이, 파우치 등의 기타면/측면 이미지에 표기된 마케팅 문구 및 함량 표기를 추가 검증합니다.")
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("기타면/측면 텍스트 및 마케팅 적합성 검토 중..."):
                prompt = """
                [지시]: 오직 아래의 기타면/측면 양식 5번 목차만 출력하십시오. 
                🚨 [1단계: 사전 판단(Thinking) 강제] 🚨
                <thinking>
                (기타면에 적힌 문구 추출 및 허위/과장광고 여부 판단 기록. 짧게 작성)
                </thinking>
                🚨 [2단계: 정식 리포트 출력] 🚨
                ## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지]
                - 결론: (✅ 적합 또는 🚨 부적합/확인요망)
                - 추가 마케팅 문구 및 숫자(N종, 소수점 등) 정합성: 
                - 건강기능식품 오인, 무첨가 강조 등 규정 위반 여부:
                - 제품명/원료 함량 강조 적합성:
                - 기타 특이사항: 
                """
                st.session_state["result_tab4"] = run_qc_model(prompt)

        if st.session_state["result_tab4"]:
            result = st.session_state["result_tab4"]
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
            if thinking_match:
                thinking_log = thinking_match.group(1).strip()
                report_content = result.replace(thinking_match.group(0), "").strip()
                with st.expander("🧠 기타면 마케팅 문구 추출 및 추론 로그 보기"):
                    st.markdown(f"*{thinking_log}*")
                st.markdown(report_content)
            else:
                st.markdown(result)

    with tab5:
        st.info("지금까지 1~4번 탭에서 분석한 모든 결과를 끌어모아 '최종 요약 및 수정 권고사항'을 작성합니다.")
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"], st.session_state["result_tab3"], st.session_state["result_tab4"]]):
                st.warning("🚨 앞의 1~4번 탭 중에서 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("모든 분석 데이터를 병합하여 최종 수정 지시서를 작성 중입니다..."):
                    combined_results = f"""
                    [1번 탭 결과]: {st.session_state.get('result_tab1', '분석 안 함')}
                    [2번 탭 결과]: {st.session_state.get('result_tab2', '분석 안 함')}
                    [3번 탭 결과]: {st.session_state.get('result_tab3', '분석 안 함')}
                    [4번 탭 결과]: {st.session_state.get('result_tab4', '분석 안 함')}
                    """
                    
                    summary_prompt = f"""
                    [지시]: 지금까지 사용자가 각 탭에서 검토한 내용들을 모았습니다. 아래의 기존 결과들을 철저히 분석하여, 실무자가 한눈에 보고 패키지를 수정할 수 있도록 종합 결론을 내려주십시오.

                    [기존 분석 데이터]
                    {combined_results}
                    
                    🚨 [출력 템플릿 강제]
                    당신은 반드시 아래의 마크다운 템플릿 양식만 출력해야 합니다.
                    
                    ## 📋 [최종 종합 검토 리포트]
                    - **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)
                    
                    ### 📌 [핵심 지적 사항 및 수정 지시]
                    (위 기존 분석 데이터에서 '부적합(🚨)' 또는 '확인요망'이 나온 내용들만 뽑아서, 디자인팀/연구소에서 즉각적으로 알아볼 수 있도록 수정 방안을 1, 2, 3번 불릿 포인트로 강력하게 요약하여 나열하십시오. 적합(✅)으로 나온 칭찬 내용은 적을 필요 없습니다.)
                    
                    ### 🔍 [기타 주의사항]
                    (수정 사항 외에 실무자가 참고해야 할 55대 룰북 관련 코멘트가 있다면 간략히 덧붙이십시오.)
                    """
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])
            
            st.markdown("---")
            st.markdown("#### 📂 (참고) 각 탭별 상세 분석 데이터")
            with st.expander("1️⃣ 주표시면 원본 결과"):
                st.markdown(st.session_state["result_tab1"] if st.session_state["result_tab1"] else "분석 안 함")
            with st.expander("2️⃣ 정보표시면 원본 결과"):
                st.markdown(st.session_state["result_tab2"] if st.session_state["result_tab2"] else "분석 안 함")
            with st.expander("3️⃣ 영양성분표 원본 결과"):
                st.markdown(st.session_state["result_tab3"] if st.session_state["result_tab3"] else "분석 안 함")
            with st.expander("4️⃣ 기타면/측면 원본 결과"):
                st.markdown(st.session_state["result_tab4"] if st.session_state["result_tab4"] else "분석 안 함")

if __name__ == "__main__":
    if check_password(): main()
