import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os
import re
import tempfile
import socket

# 👇 [네트워크 방어] 파이썬 전체 대기 시간을 10분(600초)으로 연장
socket.setdefaulttimeout(600)

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
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항(예: 당알코올 10% 컷오프, 향료 통합, 간략명/동의어 허용, 내부 코드 생략, 2% 미만 순서 유연성 등)은 이 1:1 기계적 대조 원칙보다 무조건 최우선으로 적용하여 합법(✅) 처리하십시오.**
🔥 [오탈자 무관용 원칙]: 단어의 의미가 통하더라도 글자(자음/모음)가 단 하나라도 다르면 무조건 부적합 처리하십시오. 단, 화학식 기호(α vs ALPHA), 아래첨자(₁ vs 1), 대소문자(DL vs dl), 단순 띄어쓰기 차이는 동의어 표기이므로 일치(✅) 처리하십시오. Rule 35에 해당하는 합법적 간략화/치환인 경우는 🌟 [표5/6 치환 알림] 플래그를 띄우십시오.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 "왜 이것이 법적으로 잘못되었는지, 어떻게 수정해야 하는지" 명확하고 구체적인 사유를 반드시 설명하십시오.
문서에 없는 데이터를 배경지식으로 알아서 채워 넣거나 임의로 해석하는 환각(Hallucination)을 엄격히 통제합니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 69대 룰북 원문 (V170.0 최신법 완결판)
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

## ⚠️ 검토 대원칙: 69대 품질관리 지침

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽 적합입니다.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 및 총열량/식이섬유 열량 계산 강제 룰]**
   - 주표시면(앞면)에 열량(kcal)이나 특정 영양소 함량(예: 칼슘 200mg)이 강조되어 있다면, 반드시 뒷면 영양성분표의 수치와 단 1의 오차도 없이 100% 일치하는지 교차 대조하십시오.
   - **[⭐ 세트포장(박스) 총내용량 및 총열량 누락 스나이퍼]**: 박스/세트 포장의 주표시면에는 반드시 '총 내용량(또는 단품용량 x 수량)'과 그에 상응하는 '총 열량(kcal)'이 모두 기재되어야 합니다. 누락 시 즉시 🚨부적합 처리하십시오.
   - **[⭐ 열량 계산 시 식이섬유 및 당알콜 분리 필수 적용]**: 영양성분표에 **식이섬유**나 **당알콜**이 표기되어 있다면 반드시 총 탄수화물에서 그 양을 분리하여 계산하십시오. *(적용 공식 ➔ 식이섬유: 2kcal/g, 에리스리톨: 0kcal/g, 자일리톨 등: 2.4kcal/g, 나머지 당질(탄수화물): 4kcal/g)*

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 합법(적합)으로 인정하십시오.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g으로 표기되었다면, 실제 함량이 0.5g 미만인지 검증하십시오.

🔥 **Rule 7. [당알코올 주의문구 개정 (10% 컷오프 룰)]**
   - 2026년 시행 개정법 완벽 반영: 자일리톨, 에리스리톨 등 당알코올류가 최종 제품에 **10% 미만**으로 사용된 경우, "과량 섭취 시 설사를 일으킬 수 있습니다" 등의 주의문구 생략은 100% 합법(✅)입니다. 억지 부적합 지적을 절대 금지합니다.
   - 단, 당알코올 함량이 10% 이상일 때만 해당 문구 누락 시 🚨부적합 처리하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 특정 국가명 대신 '외국산' 또는 '수입산'으로 표기해도 적합합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되었는지 확인하십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 영양 강조 심사를 하십시오.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 및 과다검출 이상치 경고 룰]**
   - **[⭐ 역산 금지]**: 무조건 '시안 표시량'을 기준으로 법적 기준선을 도출하십시오.
   - **[하한선만 검사하는 80% 이상 합법 그룹]**: 탄수화물, 단백질, 비타민, 미네랄 등. ➔ (실측값) >= (표시량 * 0.8) 이면 **제조사의 의도된 보수적(안전빵) 표기이므로 무조건 적합(✅)**입니다.
   - **[⭐ 과다 검출 이상치 경고]**: 실측값이 표시량의 3배(300%)를 초과할 경우 `✅ 적합` + `⚠️ [실무 검토 권장]` 경고 추가.
   - **[상한선만 검사하는 120% 미만 합법 그룹]**: 열량, 나트륨, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤 등. ➔ (실측값) <= (표시량 * 1.2) 이면 무조건 적합(✅).

✅ **Rule 12. [원재료명 3단 교차 검증 및 임의 추론 금지]**
   - 배합비 데이터 서류 없이 레시피를 상상하거나 임의로 지적하지 마십시오.

🔥 **Rule 13. [알레르기 정밀 추적 및 파생 원료 예외 허용]**
   - 시안의 "~함유" 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 실존해야 합니다.
   - **[⭐ 알레르기 위치 표기 절대 규칙]**: 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 한 번만 기재되어 있으면 100% 합법입니다.
   - **[⭐ 기계적 대조 예외]**: 파생 원료가 존재한다면 절대 불일치로 오판하지 말고 무조건 적합(✅) 처리하십시오.

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 완벽 스나이퍼]**
   - **[⭐ 표 4 (명칭+용도명 병기 의무)]**: 감미료, 보존료, 산화방지제 등 표 4에 속하는 첨가물은 반드시 "명칭+용도명"으로 기재.
   - **[⭐ 표 5 (간략명 표기 허용 및 용도명 대체 금지)]**: 표 5에 속하는 첨가물은 용도명으로 뭉뚱그려 쓸 수 없으며 반드시 정해진 명칭이나 허용된 간략명으로 기재.
   - **[⭐ 표 6 (용도명 대체 100% 합법)]**: 유화제, 산도조절제, 증점제, 팽창제, 영양강화제 등 표 6에 해당하는 첨가물은 용도명만 표기해도 완벽한 합법(✅).

✅ **Rule 15. [기능성 오인 문구 스캔]**
   - 건강기능식품으로 오인할 수 있는 마케팅 문구를 스캔하여 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가에서 100% 수입된 원료인 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지된 첨가물을 배제했다고 강조한 경우 기만광고로 부적합(🚨) 처리하십시오.

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 일반 식품에 영유아를 타겟으로 하는 명칭 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 분리 검증]**
   - '무당'은 당류 0.5g 미만일 때, '무가당'은 인위적 당류 첨가가 없을 때 적합합니다.

✅ **Rule 20. [포장재질 직접 접촉 원칙]**
   - 외부 박스가 아닌 '식품과 직접 접촉하는 내면 재질'만 기재하는 것이 원칙입니다.

🔥 **Rule 21. [영양강조표시 4대 조건 교차 연산 및 절대 수치 강제]**
   - [고단백]: 100g당 11g 이상 / 100mL당 5.5g 이상 / 100kcal당 5.5g 이상 / 1회섭취량당 11g 이상 (이 중 하나 충족)
   - [고식이섬유]: 100g당 6g 이상 / 100mL당 3g 이상 / 100kcal당 3g 이상 / 1회섭취량당 5g 이상 (이 중 하나 충족)
   - [고칼슘]: 100g당 210mg 이상 / 100mL당 105mg 이상 / 100kcal당 70mg 이상 / 1회섭취량당 210mg 이상 (이 중 하나 충족)
   - [저당]: 100g당 5g 미만 / 100mL당 2.5g 미만 (이 중 하나 충족)

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. 단, 상표 로고는 예외입니다.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 예외 규정 (법적 사유 지적 강제)]**
   - **트랜스지방:** 0.2~0.5g 미만은 "0.5g 미만" 표시. 0.2g 미만은 무조건 "0g" 표시.
   - **콜레스테롤:** 2~5mg 미만은 "5mg 미만" 표시.
   - **포화지방 등:** 0.5g 미만은 "0g" 표시 시 적합.

🔥 **Rule 24. [무당/무가당/설탕무첨가 2대 의무 표기 (감미료 & 열량 물리적 위치 강제)]**
   - '무당(Zero)', '무가당', '설탕 무첨가'를 강조했을 때만 발동합니다.
   - 1) **[감미료 위치 검증]**: 감미료가 들어갔다면 "감미료 함유" 문구가 강조표시 '바로 옆이나 아래'에 붙어있어야 합니다.
   - 2) **[열량 병기 위치 강제]**: 저열량 미충족 시 총 열량을 병기해야 하는데, 이 열량 텍스트가 패키지 맨 밑바닥이나 엉뚱한 곳에 떨어져 있다면 ⚠️**[실무 검토 권장]**을 띄우고 지적하십시오.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 수치를 명확히 분리하여 영양성분을 대조 검증하십시오.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 중량(g), 액체는 용량(mL)으로 적절히 표기되었는지 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등 제한 성분은 100kcal 당 조건을 적용하지 마십시오.

🔥 **Rule 28. [원산지 3순위 완벽 필터링 및 과잉 표기 경고 룰]**
   - 1) **[3순위 강제 도출]**: 정제수, 주정, 당류, 식품첨가물을 원산지 산정 순위에서 강제로 제외하십시오. 남은 진짜 원료 중 상위 1위, 2위, 3위 원료를 정확히 도출하고, 누락되었다면 🚨부적합 처리하십시오.
   - 2) **[과잉 도출 경고]**: 의무 대상이 아닌 하위 부원료에 원산지가 적혀 있다면 무조건 🚨**[확인 요망]**을 띄워 경고하십시오.

🔥 **Rule 29. [복합원재료 원산지 표시 한계]**
   - 복합원재료 자체의 원산지만 확인하십시오. 하위 성분 각각의 원산지까지 강제하지 마십시오.

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.**

✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 여러 시험성적서가 제공된 경우 모든 영양성분을 누락 없이 병합하여 종합 대조하십시오.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 영양성분표 수치 반올림 오차에 의한 단순 계산 차이는 적합(✅)으로 인정.

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치를 명확히 구분하여 리포트를 작성하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 배합비 기준 투입량 2% 미만 원료는 기재 순서가 달라도 적합으로 판정하십시오.

🔥 **Rule 35. [🌟 범용 간략명/동의어 허용 및 고도 정제/부형제 생략 보장 (강력 예외 룰)]**
   - **[🌟 고도 정제 원료 기원 생략]**: 포도당, 물엿, 과당 등 단일 당류는 서류에 옥수수전분 등 기원이 적혀있어도, 시안에서 이를 생략하고 '포도당'이라 적는 것이 100% 합법입니다.
   - **[🌟 첨가물 부형제 생략]**: 펙틴 등 혼합제제 서류에 포함된 부형제/희석제(자당, 덱스트린, 포도당 등)가 시안에서 생략되고 '펙틴'처럼 주원료만 적힌 것은 완벽한 합법입니다. 절대 누락으로 오판하지 마십시오.
   - **[🌟 수치 그대로 표시 허용]**: 영양표시 시 5.6g 등 소수점이 포함된 실측값을 그대로 적는 것은 합법(✅)입니다. 억지로 반올림을 강요하지 마십시오.
   - **[🌟 간략화 치환]**: 서류의 복잡한 명칭을 시안에서 통용명(예: `비타민 B1 염산염` -> `비타민B1`)으로 간략화한 경우 합법입니다. 🌟 [표5/6 치환 알림]을 띄우십시오.
   - **[🌟 화학식/기호/띄어쓰기 범용 예외]**: CMC-Na = CMC Na, α = ALPHA 등 모두 일치 처리.
   - **[🚨 첨가물 명칭 임의 조작 절대 금지]**: 명칭 앞뒤에 '분말', 'N종' 임의 추가 금지 (예: 향료2종 -> 🚨부적합).

✅ **Rule 36. [주의사항 오탈자 스캔]**
   - 필수 주의사항 문구의 오탈자를 정밀 검수하십시오.

✅ **Rule 37. [법적 서류 우선 원칙]**
   - 증빙 서류 데이터를 최우선으로 하되, Rule 35(간략명) 예외를 항상 먼저 고려하십시오.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 룰 (수학적 차집합 연산)]**
   - **[⭐ 수학적 차집합 검증 로직]**: [교차오염 정답지] = [공장 취급 마스터 목록] - [직접 투입 알레르기 물질]. 중복이나 누락 시 부적합(🚨).

✅ **Rule 39. [동명 원료 종속성 원칙]**
   - 동명의 복합원재료가 있더라도 각각을 별도로 독립 대조 검증하십시오.

🔥 **Rule 40. [열량 표기 및 반올림 원칙]**
   - 단품 열량이 '0 kcal'로 적법하게 표기되었더라도, 세트(박스) 총 열량은 실측 소수점을 합산하여 5kcal 단위로 반올림하므로 모순 지적을 금지합니다.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 및 수식 노출 강제]**
   - 열량(kcal)과 트랜스지방은 비율(%)을 표기하는 항목이 아닙니다. `(시안 표시량 ÷ 1일 기준치) × 100` 수식을 명시하십시오.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 완제품 기준의 최종 시험성적서 데이터만 사용하십시오.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독이 어려우면 임의 판정 금지.

🔥 **Rule 44. [혼합제제 전개 및 해체 병합(Merge) 완벽 허용 룰]**
   - 혼합제제는 2가지 합법적인 표기 방식이 있으며, 둘 중 하나만 만족하면 무조건 ✅적합 처리하십시오.
   - [방식 A (괄호 전개)]: `비타민혼합제제(비타민C, 포도당, 전분)` 처럼 괄호 안에 내림차순으로 전개한 경우 (합법)
   - [방식 B (완전 해체 병합)]: 혼합제제의 괄호를 완전히 없애고, 하위 성분들을 다른 원료들과 섞어 내림차순으로 뿔뿔이 흩어지게 기재하는 것도 완벽한 합법입니다. "괄호가 없다"며 부적합(🚨)을 지적하는 것을 절대 금지합니다.

✅ **Rule 45. [선택적 누락 허용]**
   - 마케팅적 선택 누락은 지적하지 마십시오.

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자가 포함된 경우 하위 전개 내역 스캔.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 및 뼈대 정보 교차 검증]**
   - **[🌟 영문 제품명 예외 허용]**: 앞면의 영문 브랜드명(예: MH Milk House)과 뒷면의 법적 한글 제품명이 불일치해도 디자인 요소로 완벽히 합법(✅)입니다.

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(투입 순서)와 한글라벨(최종 명칭) 역할 분리.

🔥 **Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 주표시면에 '원액', '추출물', '농축액' 함량(%)을 강조한 경우, 반드시 그 주변에 '고형분 함량(%)' 또는 '배합함량(%)' 기재 강제.

🔥 **Rule 51. [고형분(Brix) 보수적 표기 예외]**
   - 고형분 함량 시안 수치가 서류 스펙보다 낮게 표기된 경우 보수 표기이므로 무조건 적합(✅).

🔥 **Rule 52. [영양성분 강조표시(명칭 단독 기재 및 N종) 컷오프 엄격 검증 룰]**
   - 앞면에 단독으로 기재되거나 강조된 영양성분은 1일 기준치의 **15% 이상 (액체의 경우 7.5% 이상)** 함유되어야 합니다. 미달 시 🚨부적합 처리.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 농수산물 원물인 경우 가공품으로 투입되었더라도 정보표시면에 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성 검증 룰]**
   - 단일 원료에 대해 2개 이상 국가 병기 시 비율(%) 누락 여부 확인 요망 플래그.

🔥 **Rule 55. [영양성분 소수점 및 반올림 강제 규정]**
   - 포화지방 5g 이상은 소수점 없이 정수로, 트랜스지방 0.2g 미만은 소수점 없이 0g 표시.

🔥 **Rule 56. [HACCP 인증 마크 공식 텍스트 검증]**
   - "안전관리인증", "식품안전관리인증", "축산물안전관리인증" 합법. "위해요소중점관리우수식품" 등은 부적합.

🔥 **Rule 57. [세트포장 식품이력추적관리번호 수량 강제 룰]**
   - 박스 번호에 "수량(예: X 16입)"이 기재되어야 완벽한 합법(✅). 삭제 지적 절대 금지.

🔥 **Rule 58. [주표시면 함량 기재 시 원재료명 함량 생략 합법성]**
   - 앞면에 함량(%)이 적혀있다면 뒷면 원재료명에는 %를 생략해도 100% 합법(✅).

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 1) 소비자 상담 번호 2) 반품/교환 장소(구입처 등) 3) "부정·불량식품 신고는 국번없이 1399" 문구. 
   - 4장(전 구역) 중 단 한 곳에라도 적혀 있다면 합법(✅) 처리하십시오. 

🔥 **Rule 60. [복합원재료 원물 함량 강제 환산 및 타겟 원물 스나이퍼 룰]**
   - 제품명에 강조된 원물이 '페이스트, 농축액' 등 복합원재료 형태면 반드시 괄호로 진짜 원물 배합함량(%)을 기재해야 합법.

🔥 **Rule 61. [가공국 vs 원물국 분리 및 국산 예외 실무 룰 (QA 고도화)]**
   - 명칭이 '페이스트, 농축액, 분말' 등으로 끝나는 복합원재료의 경우, 원물이 국산이고 국내에서 가공했다면 괄호 안에 원물명을 쓰지 않고 곧바로 (국산)이라고 써도 완벽한 합법(✅)입니다.

🔥 **Rule 62. [축산물 주표시면 냉동/냉장 의무 표시 및 자체 추론 룰]**
   - 축산물 가공품이 냉장/냉동 제품인 경우 주표시면(앞면)에 상태를 명시해야 함.

🔥 **Rule 63. [미드팩 190mL 질소충전 표기 확인 룰]**
   - 내용량 190mL인 제품은 반드시 "질소충전" 단어가 기재되어야 함.

🔥 **Rule 64. [원물 기만표시(99.9% 등) 스나이퍼 룰]**
   - 패키지 앞면에 강조된 비율(예: 100%)이 실제 순수 '원물' 투입량이 아니라 '추출액'의 비율이라면 🚨**무조건 부적합(기만표시)** 처리.

🔥 **Rule 65. [원료명 내부 식별 코드(버전) 생략 합법성]**
   - 서류상 원료명 뒤에 붙은 내부 식별용 숫자/기호(예: `-2`, `(A)`)는 시안에서 생략해도 100% 합법(✅)입니다.

🔥 **Rule 66. [영양성분 법정 단위 하드코딩 매칭 룰 (단위 스나이퍼)]**
   - 영양정보표의 각 영양소 단위는 반드시 아래의 **[법정 단위 정답지]**와 일치해야 합니다. (g vs mg 오타 적발 시 🚨부적합)
   - **[kcal]**: 열량
   - **[g]**: 탄수화물, 당류, 식이섬유, 단백질, 지방, 포화지방, 트랜스지방
   - **[mg]**: 나트륨, 콜레스테롤, 비타민B1, 비타민B2, 비타민B6, 비타민C, 판토텐산, 칼슘, 인, 칼륨, 철(철분), 마그네슘, 아연, 구리, 망간
   - **[µg]**: 비타민D, 비타민B12, 비타민K, 비오틴, 요오드, 셀레늄, 몰리브덴, 크롬
   - **[특수 복합]**: 비타민A (`µg RE` 또는 `µg RAE`), 비타민E (`mg α-TE`), 나이아신 (`mg NE`), 엽산 (`µg DFE`)

🔥 **Rule 67. [영양정보표 하단 법정 안내문구 토시 검증 룰]**
   - 영양정보표 하단에는 반드시 **"1일 영양성분 기준치에 대한 비율(%)은 2,000kcal 기준이므로 개인의 필요 열량에 따라 다를 수 있습니다."** 가 적혀 있어야 합니다. "1일 영양소 기준"처럼 법적 용어를 임의로 축약하면 무조건 🚨부적합.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 복붙(Copy&Paste) 스나이퍼 룰 (V169 업그레이드)]**
   - 검토 모드가 '선물세트 박스(외포장)'일 경우, 디자이너가 낱팩 영양성분표를 그대로 복붙했는지 아래 3단계를 강제 스캔하여 하나라도 어긋나면 🚨부적합 처리하십시오.
   - 1) **[맨 윗줄]**: 반드시 `총 내용량 [전체용량] (낱개용량 x 개수)` 형태여야 합니다. (낱개 용량인 125mL만 적혀있으면 낱팩 복붙 에러)
   - 2) **[칼로리 줄]**: 총 내용량 바로 아래 칼로리 표기는 단순히 `15 kcal`가 아니라, 반드시 `1개(또는 1팩)당 15 kcal` 형태로 기재되어야 합니다.
   - 3) **[표 안쪽 열 제목]**: 표 내부의 영양성분 기준 수치 열 제목은 `총 내용량당`이 아니라, 반드시 `1개당` 또는 `1개(OO mL)당` 이어야 합니다.

🔥 **Rule 69. [비타민 아래첨자(Subscript) 타이포그래피 스나이퍼 룰]**
   - 원재료명, 영양성분표, 주표시면 등 패키지 전 구역에서 비타민(B1, B2, B6, B12, D3 등) 표기 시, 일반 숫자(예: B6)가 사용되었다면 반드시 ⚠️**[타이포 교정 권장]** 플래그를 띄우십시오.
   - 법적인 위반(부적합)은 아니지만, 브랜드의 전문성과 품질(QC) 관리를 위해 반드시 **아래첨자(예: B₁, B₂, B₆, B₁₂, D₃)** 폰트로 통일하여 수정할 것을 지적해야 합니다.
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
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 9, 10, 15, 16, 17, 18, 19, 21, 24, 28, 40, 46, 47, 50, 51, 52, 53, 57, 58, 59, 60, 62, 64, 68, 69] + COMMON_RULES)
# 💡 [V170.0 패치] 7번 룰(당알코올 주의문구)을 탭 2(정보표시면)에도 반영
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 6, 7, 8, 12, 13, 14, 25, 28, 29, 30, 34, 35, 38, 39, 44, 48, 52, 54, 57, 58, 59, 60, 61, 65, 69] + COMMON_RULES)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 6, 10, 11, 21, 23, 25, 26, 27, 31, 32, 33, 40, 41, 55, 59, 66, 67, 68, 69] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([7, 15, 17, 18, 20, 22, 24, 38, 56, 57, 59, 63, 64, 69] + COMMON_RULES)

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
        /* 1. 불필요한 UI 완벽하게 날려버리기 */
        [data-testid="stSidebar"], header, footer, [data-testid="stHeader"], [data-testid="stToolbar"],
        .stFileUploader, .stButton, .stRadio, .stTextInput, button { 
            display: none !important; 
        }
        
        /* 2. 탭 버튼만 정확히 타겟팅해서 숨기기 (내용물 증발 방지) */
        [role="tablist"], [data-baseweb="tab-list"] {
            display: none !important;
        }

        /* 3. 스크롤 락 파괴: 모든 컨테이너의 높이 제한을 무한대로 풀기 */
        html, body, .stApp, main, .block-container, 
        [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"] {
            height: auto !important;
            min-height: 100% !important;
            max-height: none !important;
            overflow: visible !important;
            position: static !important;
            width: 100% !important;
            max-width: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            display: block !important;
        }
        
        /* 4. 표(Table) 테두리 선명하게 살리기 및 페이지 잘림 방지 */
        table { page-break-inside: auto !important; width: 100% !important; border-collapse: collapse !important; }
        tr { page-break-inside: avoid !important; page-break-after: auto !important; }
        th, td { page-break-inside: avoid !important; border: 1px solid black !important; padding: 8px !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V170.0 - 최신 당알코올 개정법 반영)")
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
        st.info("💡 팁: 실행 파일 옆에 `default_docs` 정규 폴더를 만들고 PDF를 넣어두면 🚀버튼 클릭 시 자동으로 읽어옵니다. 가급적 표가 깨지지 않게 엑셀 원본이나 고화질 캡처 이미지를 올려주세요.")
        report_docs = st.file_uploader("📑 추가 시험성적서 및 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("📑 추가 배합비/원료 서류", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            DEFAULT_DOCS_DIR = "./default_docs"

            def robust_upload(file_path):
                max_retries = 5 
                for attempt in range(max_retries):
                    try:
                        up = genai.upload_file(file_path)
                        while up.state.name == "PROCESSING":
                            time.sleep(3)
                            up = genai.get_file(up.name) 
                        if up.state.name == "FAILED":
                            raise Exception("구글 서버에서 파일 처리 FAILED 반환")
                        return up
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise e
                        time.sleep(3 * (attempt + 1)) 

            if os.path.exists(DEFAULT_DOCS_DIR):
                auto_files = glob.glob(os.path.join(DEFAULT_DOCS_DIR, "*.pdf"))
                for file_path in auto_files:
                    user_content.append(f"### [자동로드_기본서류: {os.path.basename(file_path)}] ###")
                    user_content.append(robust_upload(file_path))

            def process(f, label):
                user_content.append(f"### [{label}] ###")
                if f.type.startswith("image"):
                    user_content.append(Image.open(f))
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(f.getbuffer())
                        safe_temp_path = tmp.name
                    user_content.append(robust_upload(safe_temp_path))
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
            with st.spinner("파일을 AI 시스템에 연동 중입니다... (구글 서버 상황에 따라 1~2분 소요될 수 있습니다)"):
                st.session_state["uploaded_content"] = get_uploaded_content()
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    # ==========================================
    # 🔥 3-Pass 파이프라인
    # ==========================================
    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_mission: str = None):
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

        if extract_mission:
            # ── PASS 1: 순수 텍스트 추출 ──
            pass1_prompt = f"""
[PASS 1 - 텍스트 추출 및 서류 파싱 전용 명령]
⭐ 이 단계에서는 판정이나 평가를 절대 금지합니다. 오직 아래 미션만 텍스트로 추출하여 반환하십시오.

{extract_mission}

출력 형식:
=== [미션 A] 추출 텍스트 ===
(추출 내용)
=== [미션 B] 서류 마스터 데이터 (표 형식/해당 시) ===
(추출 내용)
"""
            try:
                pass1_response = model.generate_content(content + [pass1_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                extracted_text = pass1_response.text
            except Exception as e:
                return f"🚨 Pass 1 (텍스트 추출) 오류 발생: {e}"

            # ── PASS 1.5: 자체 검증 ──
            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 자체검증 명령]
⭐ 당신은 방금 작성한 데이터를 비판적으로 검열하는 '매의 눈 검수관'입니다.

[Pass 1 추출 텍스트]
{extracted_text}

검증 규칙:
1. ⭐ [미션 A 검증]: Pass 1에서 추출한 텍스트에, 원본 이미지에 명백히 존재하는 오타가 임의로 정상 단어로 교정(환각)되었다면 즉시 원본 오타 그대로 훼손시켜 복구하십시오. 배열 순서가 시안의 실제 흐름과 일치하는지 강제 정렬하십시오.
2. ⭐ [미션 B 표 검증]: 미션 B의 결과물이 존재한다면 반드시 표(Table) 형태인지 확인하십시오. "등", "외 다수" 라는 표현이 표 안에 있다면 원래 성분명으로 복구하십시오.

오직 검증 및 수정이 완료된 최종 텍스트만 위와 동일한 구조(=== 미션 A ===, === 미션 B ===)로 화면에 출력하십시오.
"""
            try:
                pass15_response = model.generate_content(content + [pass15_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                verified_text = pass15_response.text
            except Exception as e:
                verified_text = extracted_text

        # ── PASS 2: 판정 ──
        docs_only = []
        for i, item in enumerate(content):
            if not isinstance(item, Image.Image) and not isinstance(item, str):
                if i > 0 and isinstance(content[i-1], str):
                    docs_only.append(content[i-1]) 
                docs_only.append(item) 

        pass2_context = ""
        if extract_mission:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================
⭐ [최종 자기검증 명령]
판정을 시작하기 전, 위 텍스트에서 실제로 확인된 내용만을 근거로 삼으십시오.
텍스트에 없는 내용을 있다고 판정하는 것을 엄격히 금지합니다.
"""

        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
이 텍스트 데이터만을 사실(FACT)로 사용하여 룰북과 대조 판정하십시오.
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
            pass2_response = model.generate_content(docs_only + [pass2_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
            if extract_mission:
                final_output = (
                    f"<pass1_log>{extracted_text}</pass1_log>\n"
                    f"<pass15_log>{verified_text}</pass15_log>\n"
                    f"{pass2_response.text}"
                )
            else:
                final_output = pass2_response.text
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
            response = model.generate_content(content + [full_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
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
                extract_mission = """
🎯 [미션 A: 주표시면 텍스트 추출 및 교차검증 스파이 스캔]
1. [전면 스캔]: '주표시면(앞면)' 시안 사진을 집중적으로 보고 제품명, 내용량, 칼로리, 마케팅 강조문구(설탕 무첨가, 비타민 함유 등)만 빠짐없이 리스트로 작성하십시오. 원재료명 전체는 절대로 추출하지 마십시오.
2. 🕵️‍♂️ [뒷면 핀셋 스캔 (교차 검증용)]: 전면 스캔이 끝났으면, 첨부된 다른 시안(영양성분표, 정보표시면)들을 빠르게 살펴보고 아래 2가지만 딱 뽑아오십시오.
   - 영양성분표 사진에 적힌 '총 내용량'과 '총 열량(kcal)' 수치
   - 앞면에 "OOO 함유" 혹은 "비타민" 등 영양소가 강조되어 있다면, 영양성분표 사진에서 해당 영양소의 '% 기준치' 및 '표시 함량' 수치
"""
                judgment_prompt = """
⭐ [영양성분 전면 분석 절대 금지] 1번 탭에서는 성적서 실측값을 환산하여 오차율(%)을 계산하는 작업을 절대 하지 마십시오. 그것은 3번 탭의 고유 권한입니다. 1번 탭에서는 오직 앞면과 뒷면의 '숫자 1:1 일치'만 확인하십시오!

## 1️⃣ [주표시면 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망) (Rulebook에 입각하여 법적 사유를 명확히 설명할 것)
- ⭐ [Rule 62] 축산물 보관상태(냉동/냉장) 주표시면 명시 강제 점검: (증빙 서류가 없더라도 다른 시안 텍스트에서 '냉장보관' 단어가 스캔되면 제품유형을 '냉장'으로 간주하고 주표시면을 스캔할 것)
- ⭐ [Rule 63] 미드팩 190mL 질소충전 표기 강제 점검: 내용량이 190mL인지 파악하고, 맞다면 '질소충전' 문구가 있는지 점검할 것.
- ⭐ [Rule 3] 세트포장(박스) 앞면 총내용량 및 총열량 강제 스캔: 세트포장 검토 모드일 경우, 박스 앞면(주표시면)에 반드시 '총 내용량(예: 125mL x 24팩)'과 그에 상응하는 '총 열량(예: 0 kcal)'이 모두 적혀 있어야 합니다. 글자가 아예 없거나, 수량만 있고 총 열량이 없거나, 단품 열량만 덜렁 적혀있다면 즉시 🚨부적합 처리하고 총 열량을 수학적으로 계산하여 팩트 폭격을 날리십시오.
- ⭐ [Rule 68] 다포장 낱팩 복붙 스나이퍼: 
- ⭐ [Rule 60 범용 적용] 제품명에 강조된 '타겟 원료'가 '페이스트, 농축액...' 형태일 때 괄호 안에 타겟 원물의 함량(%)이 있는지 강제 검증. (주의: 강조되지 않은 조연 원물의 함량 생략은 합법이므로 역산/지적 절대 금지):
- ⭐ [Rule 64] 원물 기만표시(99.9% 등) 스나이퍼 스캔:
- ⭐ [Rule 47] 박스 vs 팩 앞면 뼈대 정보 교차 검증 (제품명, 총내용량, 강조원료 함량 모순 여부):
- ⭐ [Rule 50] 원액/추출물 고형분 병기 및 명칭 적합성:
- 추가 마케팅 문구(추출분말 등) 적합성:
- ⭐ [Rule 24] 무당/무가당/설탕무첨가 2대 의무 표기 적합성 검증:
   (※ 주의: 통과 여부와 상관없이 반드시 아래 1번과 2번 항목을 각각 분리하여 보고할 것)
   1) 감미료 문구 위치: (알룰로스 등 식품원료는 제외하고 판단할 것. 적합/부적합 사유 명시)
   2) 열량 병기 물리적 위치: (저열량 기준 충족 여부를 확인하고, 미충족 시 열량 텍스트가 뱃지 주변에 있는지 판정 사유 명시)
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
1) 앞면에 특정 비타민/미네랄 명칭(예: 아연, 비타민B6 등)이 단독으로 적혀있다면, 'N종'이라는 글자가 없더라도 무조건 🚨확인 요망을 띄우고 "해당 성분들이 정보표시면 영양성분표에서 1일 기준치의 15%(액체는 7.5%) 이상을 충족하는지 반드시 성적서를 대조 확인하십시오"라고 경고할 것.
2) 만약 'N종'이라는 숫자가 적혀있다면, 영양정보표에서 7.5%(고체 15%) 미달 항목을 ❌탈락 처리하고 살아남은 개수만 합산하여 패키지의 숫자와 대조 판정할 것.
- 기타 특이사항:

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증 (단품/세트 열량 반올림 오차 허용):
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조. 의미가 같아도 자음/모음 하나라도 다르면 무조건 🚨부적합 처리할 것. 단, 단순 띄어쓰기 차이로 억지 부적합을 남발하지 말 것)
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                extract_mission = """
🎯 [미션 A: 정보표시면 배열 강제 추출]
- 시안의 '원재료명' 텍스트를 줄글로 뭉뚱그리지 말고, 쉼표(,)를 기준으로 완벽하게 쪼개서 [1. 원액두유, 2. 정제수 ...] 처럼 번호가 매겨진 세로 리스트 형태로 추출하십시오.
- 물리적 배열 순서를 반드시 유지하십시오.

🎯 [미션 B: 증빙 서류 파싱 (마스터 정답지 선행 구축)]
- 사용자가 업로드한 '증빙 서류'를 샅샅이 분석하여, 시안 검토의 기준이 될 [절대 정답지 체크리스트]를 구축하십시오.
- ⭐ [필수 표 출력]: 서류 분석 결과는 반드시 아래의 컬럼을 가진 마크다운 표(Table) 형태로 정리하여 출력해야 합니다. 줄글로 요약하지 마십시오!
  | 증빙 서류명 | 원료 제품명 | 식품유형 | 하위 전개 성분 (100% 나열) | 원산지 |
- 혼합제제의 하위 성분이 몇 개든 귀찮아하지 말고 100% 전부 타이핑하십시오 ("외", "등" 금지).
"""
                base_tab2_warning = """
⭐ [영양성분표 분석 절대 금지 명령] ⭐
이 탭(정보표시면)의 유일한 목적은 '원재료명'과 '알레르기/주의사항' 검증입니다. 시안에 '영양정보' 박스가 보이더라도 절대 그 안의 칼로리, 수치, % 기준치를 분석하거나 표로 출력하지 마십시오. 영양성분 분석은 3번 탭의 고유 권한입니다.

⭐ [1:1 대조 예외 절대 원칙 (Rule 2, 34, 35, 65 우선 적용)] ⭐
기계적인 글자 대조보다 아래 4가지 룰이 무조건 우선합니다. 이 경우 절대 부적합 지적을 금지하고 무조건 ✅적합 처리하십시오.
1. (Rule 2) 서류에 '천연땅콩향' 등 구체적 향료명이 있어도 시안에 '향료'로 묶어 표기한 경우.
2. (Rule 34) 배합비 2% 미만인 원료들끼리의 기재 순서가 서류와 다른 경우.
3. (Rule 35) '중조 ➔ 탄산수소나트륨' 처럼 공전 공식 명칭이나 널리 쓰이는 통용명, 또는 식약처 간략명(표 5, 표 6)으로 치환된 경우.
4. (Rule 65) 서류의 원료명 뒤에 붙은 내부 코드(예: '-2', '(A)')가 시안에서 생략된 경우.

🔥 [마스터 표 절대 독립 및 양방향 크로스체크 (가장 중요)] 🔥
1. [마스터 표 선행 작성 원칙]: 1번 마스터표를 작성할 때 '시안 텍스트'는 절대 컨닝하지 말고 오직 서류만 분석하여 하위성분 100% 전개 표를 만드십시오.
2. ⭐ [표 구조: 1열(Column 1) 절대 Lock]: 2번 대조 표를 그릴 때, 가장 맨 왼쪽 열(Column 1)은 반드시 **"[미션 A]에서 추출한 번호가 매겨진 시안 원재료명 리스트"**를 1번부터 끝번까지 토시 하나 바꾸지 말고 순서대로 복붙해야 합니다. 서류(마스터표)에만 있는 묶음 단어(예: 영양강화제, 비타민D3혼합제제 등 시안에 없는 글자)를 1열에 창조해 내는 순간 이 시스템은 즉시 파괴됩니다. 시안에 적힌 낱개 원료들을 그대로 1열에 고정시키십시오!
3. 🚨 [최종 누락 스나이퍼 검증]: 시안 기준의 대조 표 작성이 끝나면, 반드시 **마스터 정답지(서류)에는 존재하지만 시안에서 통째로 누락된 원료/하위성분이 있는지 수학적 차집합으로 계산**하여 표 아래에 별도 섹션으로 가차 없이 적발하십시오.

⭐ [공식 보고서용 100% 극강제 분해 및 표기 명령 (전략/중략/후략 절대 금지)] ⭐
이 문서는 타 부서에 제출할 공식적인 법적 근거 자료(QC 레포트)입니다. 단 하나의 원료라도 생략되면 이 문서의 신뢰도는 완전히 파괴됩니다.
당신이 출력하는 모든 표에서 "전략", "중략", "후략", "...", "등" 이라는 요약/생략 단어를 사용하는 순간 이 보고서는 법적 효력을 상실합니다. 무식할 정도로 100% 전부 나열하여 1:1 대조하십시오.

각 원료 행마다 다음 7가지를 끈질기게 추적하여 판정 사유에 기재하십시오:
1. ⭐ [원산지 도출 로직 명시 (가장 중요)]: 표의 '원산지 산정 순위' 열에 이 원료가 왜 원산지가 적혔는지(또는 안 적혔는지) 명확히 기재하십시오. (출력 예시: `1순위(의무)`, `제외대상(당류)`)
2. [순서 검증]: 해당 원료가 규격서 배합비 투입량에 맞게 내림차순으로 나열되었는가? (단, 2% 미만 소량 원료는 순서 유연성 인정)
3. [원산지 검증]: 해당 원료가 농수산물인 경우, 원산지가 원재료명 '바로 뒤 괄호' 안에 합법적으로 표기되었는가?
4. 🔥 [혼합제제 강제 합법 판정]: 시안에 비타민이나 부형제가 괄호 없이 뿔뿔이 흩어져 적혀 있다면, 그것은 Rule 44의 [방식 B]를 따른 완벽한 합법(✅적합)입니다. 은폐라고 오판하지 마십시오.
5. 🔥 [표 작성 절대 규칙]: 귀찮다고 여러 원료를 한 줄(Row)에 쉼표로 묶어서 표기하지 마십시오. 
6. ⭐ [가공국 vs 원물국 범용 검증 (Rule 61)]: 명칭이 '페이스트, 농축액, 분말' 등으로 끝나는 복합원재료에 대해 '원물명-국가명' 형태로 정확히 타겟팅되어 적혀있는가?
7. 🔥 [글자 단위 완전 일치 강제 명령 (오탈자 무관용)]: "토코페일"과 "토코페릴"처럼 단 한 글자의 자음/모음이라도 다르면 🚨부적합(오탈자 적발) 처리하십시오. AI의 자의적인 문맥 파악 및 자동 교정을 엄격히 금지합니다.
"""
                if doc_type == "통합 엑셀/PDF 자료 (마스터표 생략)":
                    if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🚨 확인 요망)

| 타겟(박스) 시안 표기 원재료명 (순서대로) | 매칭된 마스터 서류 원료명 | 비교용(팩) 시안 일치 여부 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유) |
|---|---|---|---|---|---|
| (시안 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 타겟(박스) 시안에서 통째로 누락된 원료/하위성분: (없으면 '누락 없음 ✅', 누락이 있다면 성분명 명시 후 🚨부적합 판정)

## 2️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
- 서류 기준, 박스와 팩의 '~함유' 알레르기 표시 완벽 일치 여부:
- ⭐ [Rule 63] 미드팩 190mL 주의사항 내 '질소충전' 표기 누락 점검:
- ⭐ [Rule 7] 당알코올 주의문구 적합성 검증 (10% 이상일 때만 표시):

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조. 자음/모음 하나라도 다르면 무조건 🚨부적합 처리)
"""
                    else:
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🚨 확인 요망)

| 시안 표기 원재료명 (패키지 나열 순서) | 매칭된 마스터 서류 원료명 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유 필수 포함) |
|---|---|---|---|---|
| (시안 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 시안에서 통째로 누락된 원료/하위성분: (없으면 '누락 없음 ✅', 누락이 있다면 성분명 명시 후 🚨부적합 판정)

## 2️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
- ⭐ [Rule 63] 미드팩 190mL 주의사항 내 '질소충전' 표기 누락 점검:
- ⭐ [Rule 7] 당알코올 주의문구 적합성 검증 (10% 이상일 때만 표시):

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조. 자음/모음 하나라도 다르면 무조건 🚨부적합 처리)
"""
                else:
                    if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원료 스펙 마스터 취합표 (개별 라벨 기반 자동 생성)]

| 시안 원재료명 | 매칭된 증빙 서류 | 식품유형 | 원료 제품명 | 한글표시사항 (하위 전개 성분) | 원산지 |
|---|---|---|---|---|---|
| (미션 B 서류 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 2️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🚨 확인 요망)

| 타겟(박스) 시안 표기 원재료명 (순서대로) | 매칭된 위 마스터 표 원료명 | 비교용(팩) 시안 일치 여부 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유) |
|---|---|---|---|---|---|
| (시안 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 타겟(박스) 시안에서 통째로 누락된 원료/하위성분: (없으면 '누락 없음 ✅', 누락이 있다면 성분명 명시 후 🚨부적합 판정)

## 3️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
- ⭐ [Rule 63] 미드팩 190mL 주의사항 내 '질소충전' 표기 누락 점검:
- ⭐ [Rule 7] 당알코올 주의문구 적합성 검증 (10% 이상일 때만 표시):

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조. 자음/모음 하나라도 다르면 무조건 🚨부적합 처리)
"""
                    else:
                        judgment_prompt = base_tab2_warning + """
## 1️⃣ [원료 스펙 마스터 취합표 (개별 라벨 기반 자동 생성)]

| 매칭된 증빙 서류명 | 원료 제품명 | 식품유형 | 한글표시사항 (하위 전개 성분) | 원산지 |
|---|---|---|---|---|
| (미션 B 서류 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 2️⃣ [원재료명 2-Way 정밀 교차 검증 (시안 기준 대조 + 누락 적발)]
- 결론: (✅ 적합 또는 🚨 부적합 또는 🚨 확인 요망)

| 시안 표기 원재료명 (패키지 나열 순서대로) | 매칭된 위 마스터 표 원료명 | 원산지 산정 순위 | 오탈자 및 대조 검증 | 판정 (Rule 기반 상세 사유 필수 포함) |
|---|---|---|---|---|
| (시안 기준 100% 나열) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

### 🚨 [서류 기준 최종 누락 스나이퍼 검증]
- 마스터 정답지에는 존재하지만 시안에서 통째로 누락된 원료/하위성분: (없으면 '누락 없음 ✅', 누락이 있다면 성분명 명시 후 🚨부적합 판정)

## 3️⃣ [알레르기, 주의사항 교차 검증]
- 결론: (✅ 적합 또는 🚨 부적합)
- ⭐ [Rule 63] 미드팩 190mL 주의사항 내 '질소충전' 표기 누락 점검:
- ⭐ [Rule 7] 당알코올 주의문구 적합성 검증 (10% 이상일 때만 표시):

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조. 자음/모음 하나라도 다르면 무조건 🚨부적합 처리)
"""
                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                extract_mission = """
🎯 [미션 A: 영양성분표 데이터 표 추출]
- 시안 이미지 중 '영양정보' 표를 찾아 단 하나도 빠짐없이 100% 똑같이 마크다운 표(성분명, 함량, %)로 추출하십시오.
- 영양정보표 바깥 하단에 적힌 "1일 영양성분 기준치에 대한..." 문구도 텍스트로 꼭 추출하십시오.

🎯 [미션 B: 시험성적서(실측값) 파싱]
- 업로드된 서류 중 '시험성적서' 실측값 데이터를 찾아 표로 정리하십시오.
"""
                base_tab3_warning = """
⭐ [오차 검증 절대 규칙 (Rule 11 강제 적용)]:
비타민, 무기질 등은 (실측값 >= 표시량의 80%) 이면 무조건 합법(✅). 열량, 당류 등은 (실측값 <= 표시량의 120%) 이면 합법. 
제조사의 의도된 보수적(안전빵) 표기를 성적서 단순 환산값과 다르다는 이유로 절대 지적하지 마십시오!

⭐ [액체 비중(Specific Gravity) 고려 원칙]: 
실험실 배합비(%)를 바탕으로 계산된 성분(예: 자일리톨)은 단순 부피(mL) 환산값과 시안 표시값이 미세하게 달라도 비중 밀도가 고려된 것이므로 무조건 ✅합법 처리하십시오.

⭐ [단위 환산 및 연산 강제 지시]: 
성적서가 100mL(g) 기준이고 시안이 총 내용량(예: 125mL) 기준이라면, 반드시 100mL 실측값에 배수를 곱하여 '환산 실측값'을 구하십시오.
기계적인 표 출력에 그치지 말고, '% 연산 검증' 컬럼에는 반드시 '시안 표시량 ÷ 1일기준치 × 100'을 직접 계산하여 그 결과값을 적어 넣으십시오!
"""
                if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                    judgment_prompt = base_tab3_warning + """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
- 결론: (✅ 적합 또는 🚨 부적합) (법적 사유 상세 설명 포함)

| 영양성분 | 성적서 환산값 | 비교용(팩) 시안 | 타겟(박스) 시안 | 팩 vs 박스 일치 여부 | 🎯 % 계산 검증 (표시량÷기준치×100) | 최종 판정 (상세 사유 필수) |
|---|---|---|---|---|---|---|---|
| (모든 영양성분을 축약 없이 100% 기재) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 🔍 [영양성분표 치명적 오탈자 및 단위 스나이퍼 스캔]
- ⭐ [Rule 66] 단위 오기재 스나이퍼: (반드시 Rule 66 정답지와 대조하여 g, mg, µg 등 단위 오타 정밀 스캔)
- ⭐ [Rule 67] 하단 법정 문구 스나이퍼: (영양정보 하단의 "1일 영양소 기준" 등 불법 축약/오타 여부 스캔)
- ⭐ [Rule 68] 다포장 낱팩 복붙 스나이퍼: (박스 시안일 경우 총내용량, 칼로리 문구, 표 안쪽 열 제목이 '낱팩 복붙'인지 3단계 강제 스캔)
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- 🔍 [전 구역 공통] 오탈자 및 띄어쓰기 정밀 스캔: (표 내 오타 여부)
"""
                else:
                    judgment_prompt = base_tab3_warning + """
## 4️⃣ [영양표시 및 % 기준치 검증]
- 결론: (✅ 적합 또는 🚨 부적합) (법적 사유 상세 설명 포함)

| 영양성분 | 성적서 환산값 | 시안 표시량 | 오차 검증(실측vs표시) | 시안 표시 % | 🎯 % 계산 검증 (표시량÷기준치×100) | 판정 (상세 사유 필수) |
|---|---|---|---|---|---|---|
| (모든 영양성분을 축약 없이 100% 기재) | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] | [내용 작성] |

## 🔍 [영양성분표 치명적 오탈자 및 단위 스나이퍼 스캔]
- ⭐ [Rule 66] 단위 오기재 스나이퍼: (반드시 Rule 66 정답지와 대조하여 g, mg, µg 등 단위 오타 정밀 스캔)
- ⭐ [Rule 67] 하단 법정 문구 스나이퍼: (영양정보 하단의 "1일 영양소 기준" 등 불법 축약/오타 여부 스캔)
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- 🔍 [전 구역 공통] 오탈자 및 띄어쓰기 정밀 스캔: (표 내 오타 여부)
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, extract_mission)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【3-Pass】 분석 진행 중..."):
                extract_mission = """
🎯 [미션 A: 전 구역(4장 전체) 공통 의무표시 통합 스캔]
- 당신은 지금부터 패키지의 특정 면에 얽매이지 않는 '통합 스캐너'입니다.
- 업로드된 앞면, 뒷면, 영양정보, 기타면 시안 '전체'를 이 잡듯이 뒤져서 아래 항목들을 정확하게 추출하십시오. (어느 면에 적혀 있든 상관없습니다.)
  1) 소비자 상담 번호 
  2) 반품 및 교환 장소 (구입처 등)
  3) "부정·불량식품 신고는 국번없이 1399" 문구
  4) HACCP 인증 마크 및 텍스트
  5) 분리배출 마크 텍스트 (해당 시)
  6) 알레르기 유발물질 교차오염 주의문구
"""
                if inspection_mode == "선물세트 박스(외포장) 교차 검토":
                    judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 팩 vs 박스 교차 대조 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망) (법적 사유 명시)
- ⭐ [Rule 59] 필수 의무표시 3종 누락 검증 (박스/팩 양쪽 확인):
   1) 고객상담실 번호: (확인 여부 기재)
   2) 반품 및 교환처: (확인 여부 기재)
   3) 1399 부정/불량식품 신고 문구: (확인 여부 기재)
   4) 판정: (하나라도 누락 시 🚨부적합 처리)
- ⭐ [Rule 38] 알레르기 교차오염 문구 적합성 (수학적 차집합 검증):
   1) [공장 마스터]: [내용 작성]
   2) [제품 함유 알레르기]: [내용 작성]
   3) [정답지 (1 - 2 차집합)]: [내용 작성]
   4) [시안 실제 교차오염 표기 (박스/팩 양쪽 확인)]: [내용 작성]
   5) [검증 결과]: (정답지와 실제 표기가 일치하는지 판단하여 누락이나 과다 기재 지적)
- ⭐ [Rule 56] HACCP 마크 텍스트 공식 명칭 적합성 (박스/팩 양쪽 확인):
- ⭐ [Rule 63] 미드팩 190mL 기타면 내 '질소충전' 표기 누락 점검:
- 팩(내포장) 기타면 vs 박스(외포장) 기타면 교차 대조 특이사항: (주의사항, 마크 등 누락이나 모순 여부)
- ⭐ [Rule 64] 원물 기만표시(99.9% 등) 스나이퍼 스캔:
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
- ⭐ [Rule 24] 무당/무가당/설탕무첨가 2대 의무 표기 적합성 검증:
   1) 감미료 문구 위치: (알룰로스 등 식품원료는 제외하고 판단할 것. 적합/부적합 사유 명시)
   2) 열량 병기 물리적 위치: (저열량 기준 충족 여부를 확인하고, 미충족 시 열량 텍스트가 뱃지 주변에 있는지 판정 사유 명시)
- 기타 특이사항:

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조)
"""
                else:
                    judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 (HACCP 포함)]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망) (법적 사유 명시)
- ⭐ [Rule 59] 필수 의무표시 3종 누락 검증:
   1) 고객상담실 번호: (확인 여부 기재)
   2) 반품 및 교환처: (확인 여부 기재)
   3) 1399 부정/불량식품 신고 문구: (확인 여부 기재)
   4) 판정: (하나라도 누락 시 🚨부적합 처리)
- ⭐ [Rule 38] 알레르기 교차오염 문구 적합성 (수학적 차집합 검증):
   1) [공장 마스터]: [내용 작성]
   2) [제품 함유 알레르기]: [내용 작성]
   3) [정답지 (1 - 2 차집합)]: [내용 작성]
   4) [시안 실제 교차오염 표기]: [내용 작성]
   5) [검증 결과]: (정답지와 실제 표기가 일치하는지 판단하여 누락이나 과다 기재 지적)
- ⭐ [Rule 56] HACCP 마크 텍스트 공식 명칭 적합성:
- ⭐ [Rule 63] 미드팩 190mL 기타면 내 '질소충전' 표기 누락 점검:
- ⭐ [Rule 64] 원물 기만표시(99.9% 등) 스나이퍼 스캔:
- ⭐ [Rule 52] 영양강조 컷오프(7.5%/15%) 및 N종 카운트 정밀 타겟팅:
- ⭐ [Rule 24] 무당/무가당/설탕무첨가 2대 의무 표기 적합성 검증:
   1) 감미료 문구 위치: (알룰로스 등 식품원료는 제외하고 판단할 것. 적합/부적합 사유 명시)
   2) 열량 병기 물리적 위치: (저열량 기준 충족 여부를 확인하고, 미충족 시 열량 텍스트가 뱃지 주변에 있는지 판정 사유 명시)
- 제품명/원료 함량 강조 적합성:
- 기타 특이사항:

## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 포장 단위(수량) 2-Track 검증:
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발: (글자 단위 1:1 대조)
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, extract_mission)
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
