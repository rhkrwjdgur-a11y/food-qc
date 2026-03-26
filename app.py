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
# 📚 2. 통합 전문가 프롬프트 (비즈니스 용어 최적화)
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 이모지를 붙이십시오.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 당신의 판단은 100% 논리적으로 일관되어야 하며, 문서에 없는 데이터를 임의로 생성(Hallucination)하거나 연산 과정을 누락하는 것을 엄격히 통제합니다.

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## 🚨 [⚖️ 1일 영양성분 기준치 (외부 데이터 개입 차단)] 🚨
주의: 사전 학습된 글로벌 데이터(예: 칼슘 1000mg 등) 적용을 금지합니다. 오직 아래 명시된 **한국 식약처 기준치**만 대입하여 %를 산출해야 합니다.
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

## ⚠️ 검토 대원칙: 52대 품질관리 지침 (단 한 글자도 생략 없이 엄수할 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 높아도 원산지 표시 대상 3순위 산정에서 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 적합합니다.

✅ **Rule 3. 영양정보 vs 강조표시 (이원화 대조)**
   - 영양성분표의 수치와 주표시면의 마케팅 강조 문구가 서로 충돌하지 않는지 대조하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 적합으로 인정하십시오. 

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다. 감미료나 향료가 생략되었더라도 지적하지 마십시오.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g이면, 0.5g 미만인지 검증하십시오.

✅ **Rule 7. 감미료 주의문구 (조건부 발동)**
   - 당알콜류 사용 시 설사 관련 주의 문구 누락 시 지적하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 '외국산' 또는 '수입산'으로 표기해도 적합합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되었는지 확인하십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 심사하십시오.

🔥 **Rule 11. [영양정보 허용오차 산술 연산 법칙 (역산 오류 방지)]**
   - **[🚨역산 금지]**: 무조건 **'시안 표시량'에 0.8 또는 1.2를 곱하여** 법적 기준선을 도출하십시오.
   - **[80% 이상 합법 그룹 (비타민, 무기질, 단백질 등)]**: (성적서 환산 실측값) $\ge$ (시안 표시량 $\times$ 0.8) 이면 적합(✅).
   - **[120% 미만 합법 그룹 (열량, 당류, 지방 등)]**: (성적서 환산 실측값) $\le$ (시안 표시량 $\times$ 1.2) 이면 적합(✅). 

✅ **Rule 12. [원재료명 3단 교차 검증 및 임의 추론 금지]**
   - 배합비 데이터 없이 레시피를 상상하여 지적하지 마십시오. 

🔥 **Rule 13. [알레르기 '~함유' 키워드 정밀 추적 및 역방향 검증]**
   - 시안의 **"~함유"** 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 존재해야 합니다.
   - **[🚨임의 판단 금지]**: 원재료명에 없는 물질이 '~함유'에 기재되어 있다면, 교차오염 등의 사유로 임의 해석하지 마시고 무조건 부적합(🚨) 처리하십시오.

🔥 **Rule 14. [표 4 및 표 6 의무/예외 표기 마스터 룰 (묶음 표기 허용)]**
   - **[🚨향료 괄호 관련 임의 지적 금지]**: '향료' 뒤에 '(착향료)' 용도명을 병기하라고 지적하는 것을 금지합니다.
   - **[표 6 묶음 표기 적합성]**: 구연산나트륨 등을 묶어서 시안에 **"영양강화제 2종"**처럼 표기하는 것은 적합(✅)합니다.

✅ **Rule 15. [기능성 오인 문구 스캔]**
   - 건강기능식품으로 오인할 수 있는 효능 문구를 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가에서 100% 수입된 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 사용이 원천 금지된 첨가물을 배제했다고 강조한 경우 부적합(🚨) 처리하십시오.

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 일반 식품에 영유아를 타겟으로 하는 명칭(예: 베이비) 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 분리 검증]**
   - '무당'은 당류 0.5g 미만, '무가당'은 인위적 당류 첨가가 없을 때 적합합니다.

✅ **Rule 20. [포장재질 직접 접촉 원칙]**
   - 포장재질 텍스트 란에는 **'식품과 직접 접촉하는 내면 재질'**만 기재하는 것이 원칙입니다.

🔥 **Rule 21. [비타민/무기질 영양강조 다중 조건 연산]**
   - 칼슘 등 강조 시 4가지 기준(100g, 100mL, 100kcal, 1회 섭취참고량) 중 **단 하나라도 충족하면 적합(✅)**합니다. 

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. 단, 상표 로고는 예외입니다.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 예외 규정]**
   - **트랜스지방:** 0.2~0.5g 미만 **"0.5g 미만"** 표시.
   - **콜레스테롤:** 2~5mg 미만 **"5mg 미만"** 표시.
   - **포화지방 등:** 0.5g 미만 "0g" 표시 적합.

✅ **Rule 24. [감미료 14pt 의무 표기]**
   - 무당 강조 시 14포인트 이상 크기로 "감미료 함유"를 표시하십시오.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위와 총 내용량 수치를 명확히 분리하여 대조하십시오.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 중량(g), 액체는 용량(mL)으로 표기되었는지 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등 제한 성분은 100kcal 당 조건을 적용하지 마십시오.

🔥 **Rule 28. [원산지 과잉 지적 금지]**
   - 하위 성분까지 과도하게 전개하여 원산지를 추가 요구하지 마십시오.

🔥 **Rule 29. [복합원재료 원산지 표시 한계]**
   - 복합원재료 자체의 원산지만 확인하십시오.

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 아닙니다.** ✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 여러 성적서의 영양성분을 누락 없이 대조하십시오.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 균형 열량 구성비 역산만으로 부적합 처리하지 마십시오.

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치를 명확히 구분하여 작성하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 배합비 2% 미만 원료는 기재 순서가 달라도 적합합니다.

✅ **Rule 35. [서류 명칭 일치(간략명) 허용]**
   - 의미상 동일한 간략 명칭은 적합 처리하십시오.

✅ **Rule 36. [주의사항 오탈자 스캔]**
   - 필수 주의사항 문구의 오탈자를 검수하십시오.

✅ **Rule 37. [법적 서류 우선 원칙]**
   - 증빙 서류 데이터를 최우선 기준으로 판별하십시오.

🔥 **Rule 38. [교차오염 경고 상호 배타성 원칙]**
   - 원재료로 투입된 성분을 '제조시설 공유(교차오염)' 주의사항에 중복 기재하면 부적합. 반대로 원재료에 없는 물질을 알레르기 '~함유' 칸에 기재해도 부적합입니다.

✅ **Rule 39. [동명 원료 종속성 원칙]**
   - 복합원재료 각각을 독립적으로 대조 검증하십시오.

✅ **Rule 40. [열량 5kcal 단위 반올림 원칙]**
   - 오차율 계산 전 가장 가까운 5kcal 단위로 반올림 적용하십시오.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 및 외부 데이터 차단]**
   - 비율(%) 계산 시 외부 데이터(해외 기준)를 사용하지 마십시오. 프롬프트 상단의 [1일 영양성분 기준치]에 명시된 한국 식약처 수치만 대입하십시오.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 완제품 기준의 시험성적서 데이터만 사용하십시오.

✅ **Rule 43. [시각적 한계 명시]**
   - 이미지 픽셀 저하로 글자 판독이 어려우면 "육안 재확인 요망"으로 처리하십시오.

✅ **Rule 44. [혼합제제 하위성분 전개 적합성]**
   - 혼합제제 구성 성분이 올바르게 전개되었는지 확인하십시오.

✅ **Rule 45. [선택적 누락 허용]**
   - 필수 표시사항이 아닌 마케팅적 선택 누락은 지적하지 마십시오.

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자가 포함된 경우 하위 전개 내역을 대조 스캔하십시오.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 룰]**
   - 내포장(팩)과 외포장(박스)의 **'원재료명'과 '영양성분'은 100% 일치**해야 합니다.
   - **[🚨물리적 차이 예외 인정]**: 단, 소비기한 표기 위치(상단 vs 측면) 등 용기 특성에 따른 물리적 문구 차이는 적합(✅)합니다.

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(투입량 순서)와 한글라벨(최종 명칭)의 역할을 분리하여 검증하십시오.

🔥 **Rule 49. [균형영양식 강제 전개 적합성]**
   - 혼합제제를 해체하여 원료별로 전개하는 것은 합법입니다.

🔥 **Rule 50. ['원액/100%' 명칭 표시 적합성 판별]**
   - **[✅적합 조건]**: 특정 원료 자체가 100% 순수 원액이라면, 최종 제품 공정에서 타 첨가물과 배합되더라도 원료명에 'OO원액' 명칭 사용이 가능합니다.
   - **[🚨부적합 조건]**: 원료 자체 스펙에 정제수나 부형제가 혼합되어 있음에도 마케팅 면에 '100% 원액'으로 과장한 경우 부적합 처리.

🔥 **Rule 51. [사용자 커스텀 PDF 폼 해독]**
   - 제공된 문서의 시안 열과 합법 데이터 열을 1:1로 정확히 매칭하십시오.

🔥 **Rule 52. [논리적 모순 탐지 및 정합성 검증]**
   - 제품명이나 마케팅 문구에 숫자(예: '23곡', '15종', '5無')가 포함된 경우, 괄호 안 원재료명에 나열된 실제 항목의 개수(쉼표 개수 기반)와 **논리적/수학적으로 일치하는지 반드시 대조 카운트**하십시오.
   - 개수가 불일치하거나 데이터 간 충돌이 발생할 경우 임의로 적합 처리하지 말고, 🚨(확인 요망) 플래그와 함께 불일치 사유를 상세히 리포트하십시오.
---
"""

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    print_css = """
    <style>
    @media print {
        header, footer, .stDeployButton { display: none !important; }
        .stFileUploader, .stButton, .stRadio, .stTextInput { display: none !important; }
        .hide-on-print { display: none !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)

    # 👔 임원진 보고용 제목으로 변경
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V16.1 - 로직 검증 및 일관성 강화판)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    c_type, c_mode = st.columns(2)
    with c_type:
        product_type = st.radio("📌 1. 식품유형 선택", ("일반식품", "특수의료용도식품 / 환자식"))
    with c_mode:
        inspection_mode = st.radio("📌 2. 검토 모드 선택", ("단품(개별 팩) 검토", "선물세트(외포장/번들) 100% 일치 교차 검토"))
    
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    st.markdown("<h3 class='hide-on-print'>🎨 3. 본 시안 이미지 (외포장 또는 단품)</h3>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    img_inner_main = img_inner_info = img_inner_nutri = img_inner_extra = None

    if "선물세트" in inspection_mode:
        st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)
        st.markdown("<h3 class='hide-on-print'>🎁 4. 내포장(개별 팩) 시안 (선물세트 대조 시 필수)</h3>", unsafe_allow_html=True)
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1: img_inner_main = st.file_uploader("내포장 주표시면", type=["jpg", "png", "jpeg"], key="inner_main")
        with ic2: img_inner_info = st.file_uploader("내포장 정보표시면", type=["jpg", "png", "jpeg"], key="inner_info")
        with ic3: img_inner_nutri = st.file_uploader("내포장 영양성분표", type=["jpg", "png", "jpeg"], key="inner_nutri")
        with ic4: img_inner_extra = st.file_uploader("내포장 기타면", type=["jpg", "png", "jpeg"], key="inner_extra")

    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)
    st.markdown("<h3 class='hide-on-print'>📄 증빙 서류 (성적서/배합비/한글라벨)</h3>", unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    with d1: report_docs = st.file_uploader("시험성적서", type=["pdf", "jpg", "png"], accept_multiple_files=True)
    with d2: recipe_docs = st.file_uploader("배합비 / 레시피", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True)
    with d3: legal_docs = st.file_uploader("한글라벨 / 품목보고서", type=["pdf", "jpg", "png"], accept_multiple_files=True)

    def process_qc(ptype, imode, content_hashes):
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        final_prompt = f"""
        [제품유형]: {ptype}
        [검토모드]: {imode}
        
        🚨 [출력 형식 강제 명령] 🚨
        당신의 응답은 반드시 첫 글자를 `<thinking>` 으로 시작하여야 하며, 빈칸으로 제출하는 것을 절대 금지합니다.
        모든 판단 결과 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망)을 붙이십시오.
        
        🚨 [긴급 차단 명령12 (마크다운 표 강제 유지)]: 아래 2번(원재료명)과 4번(영양성분표) 목차의 표는 반드시 줄바꿈(Enter)을 엄수하여 정상적인 마크다운 표(Table) 포맷으로 렌더링되게 하십시오.
        
        🧠 [긴급 차단 명령0 (Chain of Thought - 사전 추론 과정 강제)]:
        최종 7단계 리포트를 작성하기 전에, 반드시 `<thinking>` 태그를 열고 업로드된 시안과 서류를 52대 룰에 맞춰 어떻게 교차 검증했는지 당신의 '의사결정 논리'를 먼저 상세히 서술하십시오.
        (예시: "제품명 23곡과 원재료 24종이 불일치하므로 Rule 52에 의거하여 모순 탐지 보고를 수행한다"와 같이 객관적으로 서술할 것)
        
        <thinking>
        (이곳에 52대 룰과 긴급 차단 명령을 적용하여 시안과 서류를 대조하는 당신의 산술 연산 및 논리적 판단 과정을 먼저 출력할 것)
        </thinking>

        위의 사고 과정이 끝난 후, 아래의 7단계 마크다운 리포트를 본격적으로 출력하십시오.

        ## 1️⃣ [주표시면 및 마케팅 뱃지 (Rule 50, 52 적용)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령1]: 비타민/무기질의 '고/풍부' 강조 판별 시 4가지 기준의 % 허용치를 모두 대조한 후, 단 하나라도 충족한다면 적합(✅) 처리하십시오.
        - 🚨 [긴급 차단 명령13 (데이터 정합성 보고)]: Rule 52에 따라 N곡, N종 등 숫자가 포함된 경우, 하위 데이터와의 정합성 카운트 결과를 반드시 보고하십시오.
        
        ## 2️⃣ [원재료명 및 원산지 대조 (Rule 48, 49, 50, 51, 52 적용)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령2]: 배합비 상위 3순위가 아닌 미량 원료의 원산지 누락 지적을 통제합니다.
        - 🚨 [긴급 차단 명령3]: "영양강화제 2종" 등 그룹 묶음 표기는 적합(✅)으로 처리합니다.
        - 🚨 [긴급 차단 명령4]: '향료' 표기 뒤에 '(착향료)' 용도명 병기를 임의로 요구하지 마십시오.
        - 🚨 [긴급 차단 명령15 (추출 데이터와 판정 결과의 논리적 일관성 강제)]: 시안에서 원재료명 텍스트를 추출하여 표에 명시한 후, 정작 판정 칸에서는 "해당 원료가 누락되었다"며 본인이 추출한 데이터와 모순되는 결론을 내리는 논리적 오류를 엄격히 금지합니다. 데이터의 존재 유무를 판정하기 전에, 본인이 렌더링한 추출 텍스트에 해당 키워드가 존재하는지 반드시 교차 스캔하십시오.
        
        | No | 시안 원재료명 (개별 전개) | 한글라벨 매칭 원료 | 배합비 순서 검증 | 판정 및 수정안 |
        |---|---|---|---|---|
        (반드시 여기에 표 내용을 줄바꿈하여 정상적인 표 형태로 작성할 것)
        
        ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령5]: 원재료에 '호밀'이나 '호밀농축액'이 존재한다고 하여 알레르기 유발물질 '밀' 누락으로 오판하지 마십시오.
        - 🚨 [긴급 차단 명령14 (알레르기 교차오염 임의 판단 금지)]: 알레르기 주의 문구에 'OO 함유'로 표기되었다면, 반드시 시안의 '원재료명' 리스트 내에 'OO' 원료가 실존해야 합니다. 원재료명에 없는 물질이 '~함유'에 기재된 경우, "제조시설 공유 목적일 것"이라고 임의 추론하여 적합(✅) 처리하는 것을 금지합니다. 예외 없이 부적합(🚨) 처리하십시오.
        
        ## 4️⃣ [영양표시 및 % 기준치 검증]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령6 (성적서 부재 시 데이터 일치 검증)]: 시험성적서가 업로드되지 않은 '선물세트' 검토 모드 시, [내포장(개별 팩)]의 영양정보를 마스터 데이터로 삼아 [외포장(박스)] 영양성분이 내포장과 동일하거나 배수 비례에 맞게 기재되었는지 검증하십시오.
        - 🚨 [긴급 차단 명령7 (전략적 데이터 생략 인정)]: 시험성적서에 '식이섬유' 등의 검사 결과가 존재하더라도, 패키지 시안에 표기 의사가 없는 경우 임의로 표 항목에 추가하여 지적하지 마십시오.
        - 🚨 [긴급 차단 명령8 (산술 연산 검증 강제)]: 산술 연산 과정을 생략하지 마십시오. '법적 허용오차 기준선' 칸에 반드시 "[시안 표시량] * 0.8 = [결과값] 이상" 포맷으로 수식을 노출하십시오.
        - 🚨 [긴급 차단 명령9 (0표시 예외 구간 적용)]: 실측값이 0이 아니더라도, Rule 23 예외 기준 미만(예: 트랜스지방 0.2 미만)일 경우 '0' 표시를 적합으로 인정하십시오.
        - 🚨 [긴급 차단 명령11 (기준치 임의 적용 차단)]: 칼슘의 1일 기준치로 1000mg 등 외부 데이터를 적용하지 마십시오. 모든 % 연산은 프롬프트 최상단 [⚖️ 1일 영양성분 기준치]에 명시된 식약처 수치만 대입하십시오.
        
        | 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식 필수) | 1일 기준치 | 시안 % | % 검증 (계산식) | 판정 및 수정안 |
        |---|---|---|---|---|---|---|---|---|
        (반드시 여기에 표 내용을 줄바꿈하여 정상적인 표 형태로 작성할 것)
        
        ## 5️⃣ [기타 법적 의무사항]
        - 결론: (✅ 또는 🚨)
        
        ## 6️⃣ [외포장(선물세트) vs 내포장(팩) 1:1 전수 대조 결과]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령10 (식품 접촉면 및 정보 무결성 검증)]: 
          1) 식품 접촉면 검증: 내/외포장 텍스트 란에 '식품과 직접 닿는 면의 재질'이 명확히 표시되었는지 대조하십시오.
          2) 무결성 검증: 물리적 디자인 차이(표기 위치 등)를 제외한 모든 규격 텍스트 데이터가 내/외포장 간 100% 일치하는지 전수 대조하십시오.
        
        ## 7️⃣ [종합의견 및 조치 필요사항]
        """
        
        response = model.generate_content(
            user_content + [final_prompt], 
            generation_config=genai.types.GenerationConfig(temperature=0.0),
            safety_settings=safety_settings
        )
        
        # 🚨 무응답(Empty Response) 예외 처리 로직
        try:
            if not response.candidates:
                return f"🚨 [시스템 알림] 서버 응답이 없습니다. 일시적인 트래픽 지연일 수 있습니다.\n\n(시스템 로그: {response})"
            
            candidate = response.candidates[0]
            if not candidate.content.parts:
                error_msg = f"🚨 [시스템 알림] AI 분석이 내부 정책에 의해 일시 중단되었습니다.\n"
                error_msg += f"- Finish Reason: {candidate.finish_reason}\n"
                error_msg += f"- Safety Ratings: {candidate.safety_ratings}\n\n"
                error_msg += "👉 조치 안내: 브라우저 새로고침(F5) 후, 파일과 텍스트를 다시 업로드하여 '새 채팅'으로 재시도해 주십시오."
                return error_msg
                
            return response.text
        except Exception as e:
            return f"🚨 [시스템 알림] 데이터 추출 중 예상치 못한 오류가 발생했습니다: {str(e)}\n\n(시스템 로그 확인 필요)"

    if st.button("🔍 정밀 QC 검수 시작", type="primary"):
        has_files = any([
            img_main, img_info, img_nutri, img_extra,
            img_inner_main, img_inner_info, img_inner_nutri, img_inner_extra,
            report_docs, recipe_docs, legal_docs
        ])
        if not has_files:
            st.warning("🚨 검토할 시안이나 서류 파일을 최소 1개 이상 업로드해 주십시오.")
            st.stop()

        user_content = []
        def process_single_file(f, label):
            user_content.append(f"### [분류: {label}] ###")
            if f.type.startswith("image"): 
                user_content.append(Image.open(f))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                uploaded = genai.upload_file(temp)
                while uploaded.state.name == "PROCESSING": 
                    time.sleep(1)
                user_content.append(uploaded)

        with st.spinner(f"52대 품질관리 룰셋 및 데이터 정합성 검증 중... [{inspection_mode}]"):
            if img_main: process_single_file(img_main, "시안_외포장_주표시면")
            if img_info: process_single_file(img_info, "시안_외포장_정보표시면")
            if img_nutri: process_single_file(img_nutri, "시안_외포장_영양성분표")
            if img_extra: process_single_file(img_extra, "시안_외포장_기타면")
            
            if img_inner_main: process_single_file(img_inner_main, "시안_내포장_주표시면")
            if img_inner_info: process_single_file(img_inner_info, "시안_내포장_정보표시면")
            if img_inner_nutri: process_single_file(img_inner_nutri, "시안_내포장_영양성분표")
            if img_inner_extra: process_single_file(img_inner_extra, "시안_내포장_기타면")
            
            if report_docs: 
                for f in report_docs: process_single_file(f, "근거_성적서")
            if recipe_docs:
                for f in recipe_docs: process_single_file(f, "근거_배합비")
            if legal_docs:
                for f in legal_docs: process_single_file(f, "근거_한글라벨")

            try:
                result_text = process_qc(product_type, inspection_mode, None)
                
                # 시스템 오류 메시지 출력
                if "🚨 [시스템 알림]" in result_text:
                    st.error(result_text)
                else:
                    # <thinking> 태그 분리 및 UI 최적화
                    thinking_match = re.search(r'<thinking>(.*?)</thinking>', result_text, re.DOTALL)
                    
                    if thinking_match:
                        thinking_content = thinking_match.group(1).strip()
                        report_content = result_text.replace(thinking_match.group(0), "").strip()
                        
                        # 👔 보고용으로 깔끔하게 포장된 아코디언 메뉴
                        with st.expander("🧠 AI 교차 검증 추론 과정 (로그 보기)"):
                            st.markdown(f"*{thinking_content}*")
                        
                        # 7단계 리포트 본문 출력
                        st.markdown(report_content)
                    else:
                        st.markdown(result_text)

            except Exception as e: 
                st.error(f"🚨 시스템 런타임 오류 발생: {e}")
            finally:
                for f in glob.glob("temp_*"): 
                    os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
