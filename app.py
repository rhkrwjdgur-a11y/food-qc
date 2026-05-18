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
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항(예: 향료 통합, 공전 명칭 치환, 내부 코드 생략, 2% 미만 순서 유연성 등)은 이 1:1 기계적 대조 원칙보다 무조건 최우선으로 적용하여 합법 처리하십시오.**
🔥 [오탈자 무관용 원칙]: 의미가 통하더라도 단순 오타(예: 토코페일 vs 토코페릴)는 무조건 부적합 처리하십시오. 단, Rule 35에 해당하는 합법적 간략화/치환(예: 분말비타민A아세테이트 ➔ 분말비타민A)인 경우는 오타로 잡지 말고 🌟 [표5/6 치환 알림] 플래그를 띄우십시오.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 "왜 잘못되었는지, 어떻게 수정해야 하는지" 명확히 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 🌟(표5/6 치환 알림) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 65대 룰북 원문 (V156.9 QA 실무 고도화 패치)
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

## ⚠️ 검토 대원칙: 65대 품질관리 지침

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽 적합입니다.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 및 총열량/식이섬유 열량 계산 강제 룰]**
   - 주표시면(앞면)에 열량(kcal)이나 특정 영양소 함량(예: 칼슘 200mg)이 강조되어 있다면, 반드시 뒷면 영양성분표의 수치와 단 1의 오차도 없이 100% 일치하는지 교차 대조하십시오.
   - **[⭐ 세트포장(박스) 총내용량 및 총열량 누락 스나이퍼]**: 박스/세트 포장의 주표시면에는 반드시 '총 내용량(또는 단품용량 x 수량)'과 그에 상응하는 '총 열량(kcal)'이 모두 기재되어야 합니다. 누락 시 즉시 🚨부적합 처리하십시오.
   - **[⭐ 열량 계산 시 식이섬유 및 당알콜 분리 필수 적용]**: 영양성분표에 식이섬유나 당알콜이 표기되어 있다면 반드시 총 탄수화물에서 그 양을 분리하여 각 계수(식이섬유 2kcal, 에리스리톨 0kcal 등)를 적용해 계산하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 합법(적합)으로 인정하십시오.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g으로 표기되었다면, 실제 함량이 0.5g 미만인지 검증하십시오.

✅ **Rule 7. 감미료 주의문구 (조건부 발동)**
   - 당알콜류 사용 시 과량 섭취 시 설사를 일으킬 수 있다는 주의 문구 누락 여부를 확인 및 지적하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 특정 국가명 대신 '외국산' 또는 '수입산'으로 표기해도 적합합니다.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 영양 강조 심사를 하십시오.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 및 과다검출 이상치 경고 룰]**
   - **[⭐ 역산 금지]**: 무조건 '시안 표시량'을 기준으로 법적 기준선을 도출하십시오.
   - **[하한선만 검사하는 80% 이상 합법 그룹]**: 탄수화물, 단백질, 비타민, 식이섬유 등. ➔ (실측값) >= (표시량 * 0.8) 이면 무조건 적합(✅).
   - **[상한선만 검사하는 120% 미만 합법 그룹]**: 열량, 나트륨, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤 등. ➔ (실측값) <= (표시량 * 1.2) 이면 무조건 적합(✅).

🔥 **Rule 13. [알레르기 정밀 추적 및 파생 원료 예외 허용]**
   - 시안의 "~함유" 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 실존해야 합니다.
   - **[⭐ 알레르기 위치 표기 절대 규칙]**: 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 한 번만 기재되어 있으면 100% 합법입니다.

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 완벽 스나이퍼]**
   - **[⭐ 표 4 (명칭+용도명 병기 의무)]**: 감미료, 보존료, 산화방지제 등 표 4에 속하는 첨가물은 반드시 "명칭+용도명"으로 기재.
   - **[⭐ 표 5 (간략명 표기 허용 및 용도명 대체 금지)]**: 표 5에 속하는 첨가물은 용도명으로 뭉뚱그려 쓸 수 없으며 반드시 정해진 명칭이나 허용된 간략명으로 기재.
   - **[⭐ 표 6 (용도명 대체 100% 합법)]**: 유화제, 산도조절제, 증점제, 팽창제, 영양강화제 등 표 6에 해당하는 첨가물은 용도명만 표기해도 완벽한 합법(✅).

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지된 첨가물을 배제했다고 강조한 경우 기만광고로 부적합(🚨) 처리하십시오.

🔥 **Rule 21. [영양강조표시 4대 조건 교차 연산 및 절대 수치 강제]**
   - [고단백]: 100g당 11g 이상 / 100mL당 5.5g 이상 / 100kcal당 5.5g 이상 / 1회섭취량당 11g 이상 (이 중 하나 충족)

🔥 **Rule 24. [무당/무가당/설탕무첨가 2대 의무 표기 (감미료 & 열량 물리적 위치 강제)]**
   - '무당(Zero)', '무가당', '설탕 무첨가'를 강조했을 때만 발동합니다.
   - 1) **[감미료 위치 검증]**: 감미료가 들어갔다면 "감미료 함유" 문구가 강조표시 '바로 옆이나 아래'에 붙어있어야 합니다.
   - 2) **[열량 병기 위치 강제]**: 저열량 미충족 시 총 열량을 병기해야 하는데, 이 열량 텍스트가 패키지 맨 밑바닥이나 엉뚱한 곳에 떨어져 있다면 ⚠️**[실무 검토 권장]**을 띄워 수정 지시를 내리십시오.

🔥 **Rule 28. [원산지 3순위 완벽 필터링 및 과잉 표기 경고 룰]**
   - 정제수, 주정, 당류, 식품첨가물을 원산지 산정 순위에서 강제로 제외하십시오. 남은 진짜 원료 중 상위 1~3위 원료를 정확히 도출하고, 이 3개 중 하나라도 라벨에 원산지가 누락되었다면 🚨부적합 처리하십시오. 의무 대상이 아닌 부원료에 과잉 표기된 경우 🚨**[확인 요망]**을 띄우십시오.

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.**

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 배합비 기준 투입량 2% 미만 원료는 기재 순서가 달라도 적합으로 판정하십시오.

🔥 **Rule 35. [🌟 첨가물 공전 명칭 치환 및 간략화 실무 허용 룰 (QA 고도화)]**
   - 기계적인 1:1 오타 대조를 멈추고 다음의 경우 합법적인 치환으로 인정하십시오.
   - 원료 서류상의 복잡한 명칭(예: `분말비타민A아세테이트`, `비타민 B1 염산염`)을 시안에서 업계 통용 간략명(예: `분말비타민A`, `비타민A`, `비타민B1`)으로 간략화하는 것은 합법입니다.
   - 🌟 **[중요 작동 지침]**: 이렇게 합법적으로 치환된 것을 발견하면 `🚨 부적합(오타)`으로 잡지 말고, 또한 단순 `✅ 적합`으로 넘기지도 마십시오. 반드시 **`🌟 [표5/6 치환 알림]`** 이라는 플래그를 띄우고 "서류의 [원래명칭]이 시안에서 [치환명칭]으로 합법적 간략화/치환되었습니다. (실무자 최종 확인 요망)"이라고 명시하여 AI의 필터링 역할과 QA의 최종 결정 역할을 분담하십시오.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 룰 (수학적 차집합 연산)]**
   - **[⭐ 수학적 차집합 검증 로직]**: [교차오염 정답지] = [공장 취급 마스터 목록] - [직접 투입 알레르기 물질]. 중복이나 누락 시 부적합(🚨).

🔥 **Rule 44. [혼합제제 분산 전개(해체) 합법성 보장 룰 (QA 고도화)]**
   - 혼합제제 내 하위 성분들을 괄호로 묶지 않고 전체 성분표에 개별 원료처럼 분산(해체)하여 내림차순으로 섞어 기재하는 것(방식 B)은 성분 은폐가 아닌 **완벽히 합법적인 전개 방식**입니다.
   - AI는 괄호가 없거나 성분이 흩어져 있다는 이유로 "은폐", "구분이 안 됨", "소비자 오인" 등의 이유를 달아 부적합을 때리는 오판을 절대 해서는 안 됩니다. 서류에 있는 부형제가 시안 리스트에 100% 빠짐없이 흩어져 존재하기만 한다면 무조건 ✅ 적합 처리하십시오.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 및 뼈대 정보 교차 검증]**
   - 팩과 박스 앞면 뼈대 정보(제품명, 총내용량, 강조원료 함량) 모순 여부 강제 스캔.

🔥 **Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 주표시면에 '원액', '추출물', '농축액' 함량(%)을 강조한 경우, 반드시 그 주변에 '고형분 함량(%)' 또는 '배합함량(%)' 기재 강제.

🔥 **Rule 52. [영양성분 강조표시(명칭 단독 기재 및 N종) 컷오프 엄격 검증 룰]**
   - 패키지 주표시면이나 측면 등에 "비타민/미네랄 N종" 또는 "비타민C, 아연" 등 개별 영양소 명칭을 단독으로 기재/강조하는 것은 '영양성분 강조표시'입니다.
   - 앞면에 이름이 적힌 영양성분은 1일 기준치의 **15% 이상 (액체의 경우 7.5% 이상)** 함유되어야 합니다. 미달 시 🚨부적합 처리하십시오.

🔥 **Rule 57. [세트포장 식품이력추적관리번호 수량 강제 룰]**
   - 박스 번호에 "수량(예: X 16입)"이 기재되어야 완벽한 합법(✅). 삭제 지적 절대 금지.

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 1) 소비자 상담 번호 2) 반품/교환처 3) 1399 신고 문구. 누락 시 🚨부적합.

🔥 **Rule 61. [가공국 vs 원물국 분리 및 국산 예외 실무 룰 (QA 고도화)]**
   - 명칭이 '페이스트, 농축액, 추출액, 분말' 등으로 끝나는 복합원재료의 원산지 표기 시, 원물명을 괄호 안에 병기하는 것이 원칙입니다. (예: `검은콩농축액(검은콩: 중국산)`)
   - 🌟 **[국산 원물 + 국내 가공 예외 허용]**: 단, 원물이 국산이고 국내에서 가공하여 **수입산을 국산으로 둔갑시킬 우려가 없는 경우(예: `검은콩농축액(국산)`)에는 원물명을 별도로 병기하지 않아도 실무상 허용되는 합법(✅ 적합)** 표기입니다. 이를 부적합으로 오판하지 마십시오.

🔥 **Rule 64. [원물 기만표시(100% 등) 스나이퍼 룰]**
   - 패키지 주표시면에 특정 원물명과 함께 높은 비율(예: 100%)이 강조되어 있을 때, 그 비율이 실제 순수 '원물'의 투입량이 아니라 '추출액, 원액'의 비율이라면 🚨**무조건 부적합(기만표시/오인혼동)** 처리하십시오. (예: "국내산 서리태 100%" ➔ 부적합 / "국내산 서리태 사용" 또는 "서리태 원액두유 100%" ➔ 적합)

🔥 **Rule 65. [원료명 내부 식별 코드(버전) 생략 합법성]**
   - 서류상 원료명 뒤에 붙은 내부 식별용 숫자/기호(예: `메이플시럽-2`, `비타민D3 1.0`, `YP103`)는 시안에서 생략해도 100% 합법(✅)입니다.
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
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 6, 10, 11, 21, 23, 25, 26, 27, 31, 32, 33, 40, 41] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([7, 24, 38, 57, 59, 64] + COMMON_RULES)

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
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V156.9 - QA 실무 고도화 패치)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        st.markdown("#### 🏭 공장 알레르기 마스터 설정")
        factory_allergens = st.text_area(
            "우리 공장 취급 알레르기 물질 (쉼표로 구분)",
            "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류",
            help="여기에 입력된 목록을 기준으로 제품 함유 물질을 제외한 차집합 연산을 수행하여 교차오염 멘트의 누락/중복을 검증합니다."
        )
        st.markdown("---")
        product_type = st.radio("📌 1. 식품유형 (냉장표시 검사 스위치)", (
            "일반식품 (두유류 등 - 냉장표시 의무 없음)", 
            "특수의료용도식품 / 환자식", 
            "냉장 축산물 (우유/가공유 등 - 주표시면 냉장표시 강제 스캔)"
        ))
        inspection_mode = st.radio("📌 2. 검토 모드", ("단품(팩/단일포장) 기본 검토", "선물세트 박스(외포장) 교차 검토"))
        doc_type = st.radio("📌 3. 증빙 서류 형태", ("통합 엑셀/PDF 자료 (마스터표 생략)", "개별 원료 한글라벨 무더기 (마스터표 생성)"))

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
            box_main = None
            box_info = None
            box_nutri = None
            box_extra = None

        st.markdown("---")
        st.markdown("#### 📑 추가 증빙 서류 업로드 (선택사항)")
        st.info("💡 가급적 표가 깨지지 않게 엑셀 원본이나 고화질 캡처 이미지를 올려주세요.")
        report_docs = st.file_uploader("📑 추가 시험성적서 및 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("📑 추가 배합비/원료 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            DEFAULT_DOCS_DIR = "./default_docs"
            if os.path.exists(DEFAULT_DOCS_DIR):
                auto_files = glob.glob(os.path.join(DEFAULT_DOCS_DIR, "*.pdf"))
                for file_path in auto_files:
                    user_content.append(f"### [자동로드_기본서류: {os.path.basename(file_path)}] ###")
                    up = genai.upload_file(file_path)
                    while up.state.name == "PROCESSING":
                        time.sleep(1)
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
                    while up.state.name == "PROCESSING":
                        time.sleep(1)
                    user_content.append(up)
                    os.remove(safe_temp_path)

            if img_main: process(img_main, "타겟_시안_주표시면")
            if img_info: process(img_info, "타겟_시안_정보표시면")
            if img_nutri: process(img_nutri, "타겟_시안_영양성분표")
            if img_extra: process(img_extra, "타겟_시안_기타면_측면")
            if box_main: process(box_main, "비교용_정답지_시안_주표시면")
            if box_info: process(box_info, "비교용_정답지_시안_정보표시면")
            if box_nutri: process(box_nutri, "비교용_정답지_시안_영양성분표")
            if box_extra: process(box_extra, "비교용_정답지_시안_기타면_측면")
            
            if report_docs:
                for f in report_docs: process(f, "수동추가_근거_시험성적서_및_서류")
            if recipe_docs:
                for f in recipe_docs: process(f, "수동추가_근거_서류(비교용 기준)")
            return user_content

        st.markdown("---")
        if st.button("🚀 전체 시스템 파일 연동 (기본 폴더 자동 로드 포함)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다..."):
                st.session_state["uploaded_content"] = get_uploaded_content()
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    # ==========================================
    # 🔥 3-Pass 파이프라인
    # ==========================================
    def run_qc_3pass(tab_rules: str, judgment_prompt: str):
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

        pass1_prompt = """
[PASS 1 - 텍스트 추출 및 서류 파싱 전용 명령]
⭐ 이 단계에서는 판정이나 평가를 절대 금지합니다. 오직 아래 두 가지 미션만 수행하십시오.

🎯 [미션 A: 라벨 시안 이미지 추출 (배열 강제 추출 및 오타 교정 절대 차단)]
- 당신은 인간의 맥락 이해 능력이 없는 '바보 광학 스캐너(OCR)'입니다. 시안 이미지(JPG, PNG)에 오타(예: 토코페일아세티이트, 비타민B₁염산염 등)가 있더라도 절대 올바른 단어로 교정하지 말고 기괴한 글자 그대로 100% 필사하십시오.
- ⭐ [배열(List) 강제 추출]: 시안의 원재료명 텍스트를 줄글로 뭉뚱그리지 말고, 쉼표(,)를 기준으로 완벽하게 쪼개서 [1. 원액두유, 2. 정제수 ... 17. dl-α-토코페일아세티이트] 처럼 번호가 매겨진 세로 리스트 형태로 추출하십시오.

🎯 [미션 B: 증빙 서류 파싱 (마스터 정답지 선행 구축)]
- 사용자가 업로드한 '증빙 서류'를 샅샅이 분석하여 [절대 정답지 체크리스트]를 구축하십시오.
- ⭐ [필수 표 출력]: 서류 분석 결과는 반드시 아래의 컬럼을 가진 마크다운 표(Table) 형태로 정리하여 출력해야 합니다.
  | 증빙 서류명 | 원료 제품명 | 식품유형 | 하위 전개 성분 (100% 나열) | 원산지 |
- 혼합제제의 하위 성분을 단 하나도 빠짐없이 표 안에 100% 추출하십시오. 
- 🔥 [가장 중요한 명령]: 하위 성분이 몇 개든 귀찮아하지 말고 100% 전부 타이핑하십시오. "외", "등" 같은 축약어를 사용하는 순간 이 시스템은 폐기됩니다. 서류에 적힌 글자 그대로를 모두 추출하십시오. 또한 여러 비타민 제제를 묶어서 '영양강화제'라는 단어로 임의 창조하여 짬처리하지 마십시오.

출력 형식:
=== [미션 A] 라벨 시안 추출 텍스트 (번호 매긴 리스트) ===
1. [원료명]
...

=== [미션 B] 증빙 서류 마스터 데이터 (표 형식) ===
(표 출력)
"""
        try:
            pass1_response = model.generate_content(content + [pass1_prompt], generation_config=generation_config, safety_settings=safety_settings)
            extracted_text = pass1_response.text
        except Exception as e:
            return f"🚨 Pass 1 (텍스트 추출) 오류 발생: {e}"

        pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 자체검증 명령]
⭐ 당신은 방금 작성한 데이터를 비판적으로 검열하는 '매의 눈 검수관'입니다.

[Pass 1 추출 텍스트]
{extracted_text}

검증 규칙:
1. ⭐ [미션 A (시안) 검증]: Pass 1 텍스트가 번호가 매겨진 리스트 형태인지 확인하십시오. 시안 이미지에 명백한 오타가 있는데 AI가 마음대로 정답으로 교정했다면 원본 이미지의 오타 그대로 다시 훼손시켜 복구하십시오.
2. ⭐ [미션 B (서류) 표 검증]: 미션 B의 결과물이 반드시 표(Table) 형태인지 확인하십시오. 서류 내용 중 실수로 빼먹은 하위 성분, 원산지가 없는지 샅샅이 뒤져서 표의 내용을 100% 꽉 채우십시오. "등", "외 다수" 라는 표현이 표 안에 있다면 원래 성분명으로 복구하십시오.

오직 검증 및 수정이 완료된 최종 텍스트만 위와 동일한 구조(=== 미션 A ===, === 미션 B 표 ===)로 화면에 출력하십시오.
"""
        try:
            pass15_response = model.generate_content(content + [pass15_prompt], generation_config=generation_config, safety_settings=safety_settings)
            verified_text = pass15_response.text
        except Exception as e:
            verified_text = extracted_text

        docs_only = []
        for i, item in enumerate(content):
            if not isinstance(item, Image.Image) and not isinstance(item, str):
                if i > 0 and isinstance(content[i-1], str):
                    docs_only.append(content[i-1]) 
                docs_only.append(item) 

        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
아래 [검증된 텍스트 데이터]는 Pass 1 추출 후 Pass 1.5 자체검증까지 완료된 최종 확정본입니다.
이 텍스트 데이터만을 사실(FACT)로 사용하여 룰북과 대조 판정하십시오.
⭐ 이미지를 직접 다시 참조하는 것을 엄격히 금지합니다. 오직 아래 텍스트와 함께 제공된 PDF/엑셀 증빙 서류만 참조하십시오.

[제품유형]: {product_type}
[검토모드]: {inspection_mode}
[우리 공장 알레르기 마스터 목록]: {factory_allergens}

[이 탭에 적용되는 핵심 룰]
{tab_rules}

========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================

⭐ [최종 자기검증 명령]
판정을 시작하기 전, 위 텍스트에서 실제로 확인된 내용만을 근거로 삼으십시오.
텍스트에 없는 내용을 있다고 판정하는 것을 엄격히 금지합니다.

{judgment_prompt}
"""
        try:
            pass2_response = model.generate_content(docs_only + [pass2_prompt], generation_config=generation_config, safety_settings=safety_settings)
            final_output = (
                f"<pass1_log>{extracted_text}</pass1_log>\n"
                f"<pass15_log>{verified_text}</pass15_log>\n"
                f"{pass2_response.text}"
            )
            return fix_markdown_table(final_output)
        except Exception as e:
            return f"🚨 Pass 2 (룰 판정) 오류 발생: {e}"

    # ==========================================
    # 종합 보고서 
    # ==========================================
    def run_qc_model(prompt_text):
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
        full_prompt = f"""
        [제품유형]: {product_type}
        [검토모드]: {inspection_mode}
        [우리 공장 알레르기 마스터 목록]: {factory_allergens}
        {RULE_BOOK_FULL}
        ========================================
        당신은 지금 선택된 탭의 임무만 완벽하게 수행해야 합니다.
        {prompt_text}
        """
        try:
            response = model.generate_content(content + [full_prompt], generation_config=generation_config, safety_settings=safety_settings)
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

        if pass1_match:
            pass1_log = pass1_match.group(1).strip()
            result = result.replace(pass1_match.group(0), "").strip()
            with st.expander(f"📋 Pass 1 원본 추출 로그 보기 ({tab_name})"): st.markdown(f"*{pass1_log}*")

        if pass15_match:
            pass15_log = pass15_match.group(1).strip()
            result = result.replace(pass15_match.group(0), "").strip()
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 보기 ({tab_name}) ← 실제 판정에 사용된 텍스트"):
                st.info("💡 Pass 1.5는 Pass 1 추출본을 이미지와 재대조하여 오독/환각을 제거한 최종 확정 텍스트입니다.")
                st.markdown(f"*{pass15_log}*")

        thinking_match = re.search(r'<thinking>(.*?)</thinking>', result, re.DOTALL)
        if thinking_match:
            thinking_log = thinking_match.group(1).strip()
            result = result.replace(thinking_match.group(0), "").strip()
            with st.expander(f"🧠 Pass 2 판정 사전 분석 로그 보기 ({tab_name})"): st.markdown(f"*{thinking_log}*")

        st.markdown(result)

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "📊 5️⃣ 종합 보고서"
    ])

    # ── TAB 1: 주표시면 ──
    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                judgment_prompt = """
## 1️⃣ [주표시면 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망) (Rulebook에 입각하여 법적 사유를 명확히 설명할 것)
- ⭐ [Rule 62] 축산물 보관상태(냉동/냉장) 주표시면 명시 강제 점검: 
- ⭐ [Rule 63] 미드팩 190mL 질소충전 표기 강제 점검: 
- ⭐ [Rule 3] 세트포장(박스) 앞면 총내용량 및 총열량 강제 스캔: 
- ⭐ [Rule 60 범용 적용] 제품명에 강조된 타겟 원료 배합함량 강제 검증:
- ⭐ [Rule 64] 원물 기만표시(100% 등) 스나이퍼 스캔:
- ⭐ [Rule 47] 박스 vs 팩 앞면 뼈대 정보 교차 검증:
- ⭐ [Rule 50] 원액/추출물 고형분 병기 및 명칭 적합성:
- ⭐ [Rule 24] 무당/무가당/설탕무첨가 2대 의무 표기 적합성 검증:
   1) 감미료 문구 위치:
   2) 열량 병기 물리적 위치:
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
- 기타 특이사항:

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                base_tab2_warning = """
🔥 [마스터 표 절대 독립 및 양방향 크로스체크 (가장 중요)] 🔥
1. [마스터 표 선행 작성 원칙]: 1번 마스터표를 작성할 때 '시안 텍스트'는 절대 컨닝하지 말고 오직 서류만 분석하여 하위성분 100% 전개 표를 만드십시오.
2. ⭐ [표 구조: 1열(Column 1) 절대 Lock]: 2번 대조 표를 그릴 때, 가장 맨 왼쪽 열(Column 1)은 반드시 **"[미션 A]에서 추출한 번호가 매겨진 시안 원재료명 리스트"**를 그대로 복사해서 순서대로 붙여넣으십시오. 서류에 존재하는 '영양강화제' 같은 묶음 단어가 시안 리스트에 없다면 절대 1열에 임의로 적어넣지 마십시오.
3. 🚨 [최종 누락 스나이퍼 검증]: 시안 기준의 대조 표 작성이 끝나면, 반드시 **마스터 정답지(서류)에는 존재하지만 시안에서 통째로 누락된 원료/하위성분이 있는지 차집합으로 계산**하여 적발하십시오.

⭐ [공식 보고서용 100% 극강제 분해 및 표기 명령] ⭐
각 원료 행마다 다음을 끈질기게 추적하여 판정 사유에 기재하십시오:
1. ⭐ [원산지 도출 로직 명시]: 표의 '원산지 산정 순위' 열 기재.
2. [원산지 검증]: 합법 표기 여부 (Rule 61의 국산 예외 포함 확인).
3. 🔥 [혼합제제 분산 전개(해체) 합법성 보장 (Rule 44)]: 시안에 부형제가 괄호 없이 뿔뿔이 흩어져 적혀 있다면 완벽한 합법(✅적합)입니다. 은폐라고 오판하지 마십시오.
4. 🌟 [표5/6 치환 알림 (Rule 35)]: 분말비타민A아세테이트를 분말비타민A로 적은 것과 같은 실무적 통용명칭 간략화는 합법이므로 오타(부적합)로 잡지 말고 **🌟 [표5/6 치환 알림]** 플래그를 띄워 실무자에게 보고하십시오.
5. 🔥 [글자 단위 완전 일치 강제 명령 (오탈자 무관용)]: Rule 35의 합법적 치환이 아닌 단순 오타(예: 토코페일 vs 토코페릴)는 🚨부적합(오탈자 적발) 처리하십시오.
"""
                if doc_type == "통합 엑셀/PDF 자료 (마스터표 생략)":
                    if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🌟 확인 요망)

| 타겟(박스) 시안 표기 원재료명 (순서대로) | 매칭된 마스터 서류 원료명 | 비교용(팩) 시안 일치 여부 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유) |
|---|---|---|---|---|---|
| (시안(미션 A) 기준 100% 복붙 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 타겟(박스) 시안에서 통째로 누락된 원료/하위성분: 

## 2️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
"""
                    else:
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🌟 확인 요망)

| 시안 표기 원재료명 (패키지 나열 순서) | 매칭된 마스터 서류 원료명 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유 필수 포함) |
|---|---|---|---|---|
| (시안(미션 A) 기준 100% 복붙 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 시안에서 통째로 누락된 원료/하위성분: 

## 2️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
"""
                else:
                    if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원료 스펙 마스터 취합표 (개별 라벨 기반 자동 생성)]

| 시안 원재료명 | 매칭된 증빙 서류 | 식품유형 | 원료 제품명 | 한글표시사항 (하위 전개 성분) | 원산지 |
|---|---|---|---|---|---|
| (미션 B 서류 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 2️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🌟 확인 요망)

| 타겟(박스) 시안 표기 원재료명 (순서대로) | 매칭된 위 마스터 표 원료명 | 비교용(팩) 시안 일치 여부 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유) |
|---|---|---|---|---|---|
| (시안(미션 A) 기준 100% 복붙 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 타겟(박스) 시안에서 통째로 누락된 원료/하위성분: 

## 3️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
"""
                    else:
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원료 스펙 마스터 취합표 (개별 라벨 기반 자동 생성)]

| 매칭된 증빙 서류명 | 원료 제품명 | 식품유형 | 한글표시사항 (하위 전개 성분) | 원산지 |
|---|---|---|---|---|
| (미션 B 서류 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 2️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🌟 확인 요망)

| 시안 표기 원재료명 (패키지 나열 순서대로) | 매칭된 위 마스터 표 원료명 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유 필수 포함) |
|---|---|---|---|---|
| (시안(미션 A) 기준 100% 복붙 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 시안에서 통째로 누락된 원료/하위성분: 

## 3️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
"""
                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                    judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
| 영양성분 | 성적서 실측값 | 비교용(팩) 시안 | 타겟(박스) 시안 | 팩 vs 박스 일치 여부 | % 계산 검증 (표시량÷기준치) | 최종 판정 (상세 사유 필수) |
|---|---|---|---|---|---|---|
| (모든 영양성분을 축약 없이 100% 기재) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |
"""
                else:
                    judgment_prompt = """
## 4️⃣ [영양표시 및 % 기준치 검증]
| 영양성분 | 성적서 실측값 | 시안 표시량 | 오차 검증(실측vs표시) | 시안 표시 % | % 계산 검증 (표시량÷기준치) | 판정 (상세 사유 필수) |
|---|---|---|---|---|---|---|
| (모든 영양성분을 축약 없이 100% 기재) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                    judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 팩 vs 박스 교차 대조 및 마케팅 뱃지]
- ⭐ [Rule 59] 필수 의무표시 3종 누락 검증 (박스/팩 양쪽 확인):
- ⭐ [Rule 38] 알레르기 교차오염 문구 적합성 (수학적 차집합 검증):
- ⭐ [Rule 56] HACCP 마크 텍스트 공식 명칭 적합성 (박스/팩 양쪽 확인):
- ⭐ [Rule 64] 원물 기만표시(100% 등) 스나이퍼 스캔:
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
"""
                else:
                    judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 (HACCP 포함)]
- ⭐ [Rule 59] 필수 의무표시 3종 누락 검증:
- ⭐ [Rule 38] 알레르기 교차오염 문구 적합성 (수학적 차집합 검증):
- ⭐ [Rule 56] HACCP 마크 텍스트 공식 명칭 적합성:
- ⭐ [Rule 64] 원물 기만표시(100% 등) 스나이퍼 스캔:
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    # ── TAB 5: 종합 보고서 ──
    with tab5:
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"],
                        st.session_state["result_tab3"], st.session_state["result_tab4"]]):
                st.warning("🚨 앞의 1~4번 탭 중에서 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("모든 분석 데이터를 병합하여 최종 수정 지시서를 작성 중입니다..."):
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
(위 분석 데이터에서 '부적합(🚨)' 또는 '확인요망'이 나온 내용들만 뽑아서 번호 순 불릿 포인트로 요약하십시오. 법적 사유가 적혀있다면 그 사유도 반드시 요약하여 포함하십시오.)

### 🔍 [기타 주의사항]
(실무자가 참고해야 할 관련 룰북 코멘트를 덧붙이십시오.)
"""
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])
            st.markdown("""
                <hr class='hide-on-print'>
                <div class='hide-on-print' style='text-align: right; margin-top: 20px; margin-bottom: 20px;'>
                    <button onclick='setTimeout(function(){ window.print(); }, 100);' style='background-color: #FF4B4B; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; font-size: 16px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                        🖨️ 종합 보고서 전용 인쇄
                    </button>
                    <p style='font-size: 12px; color: gray; margin-top: 8px;'>※ 단축키(Ctrl+P 또는 Cmd+P)를 누르셔도 스크롤 잘림 없이 전체 페이지가 인쇄됩니다.</p>
                </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    if check_password():
        main()
