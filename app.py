import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

# [보안] 관계자 외 접속 제한
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
        st.text_input("🔒 비밀번호 오류. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else: return True

# 1. API 키 및 모델 설정
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash" 

# 2. 통합 전문가 프롬프트 (Rule 1~51 무삭제 통합판)
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 이모지를 붙이십시오.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 당신의 판단은 100% 일관되어야 하며, 임의로 수치를 지어내거나 계산을 건너뛰는 행위(환각)를 엄격히 금지합니다. 

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⚠️ 검토 대원칙: 51대 특수 지침 (단 한 글자도 생략 없이 엄수할 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (철저 준수)**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 카운트에서 100% 제외됩니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (하위 향료 통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽한 합법입니다.

✅ **Rule 3. 영양정보 vs 강조표시 (이원화 대조)**
   - 영양성분표의 수치와 주표시면의 마케팅 강조 문구가 서로 충돌하지 않는지 대조하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 적합으로 인정하십시오. 

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 전면 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다. 감미료나 향료가 생략되었더라도 지적하지 마십시오.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g이면, 0.5g 미만인지 검증하십시오.

✅ **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)**
   - 당알콜류 사용 시 설사 관련 문구 누락 시 지적하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 '외국산' 또는 '수입산'으로 표기해도 합법입니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되었는지 확인하십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 심사하십시오.

🔥 **Rule 11. [영양정보 허용오차 계산 절대 법칙 (하/상한선 및 역산 오류 완전 방지)]**
   - **[🚨역산 절대 금지]**: 무조건 **'시안 표시량'에 0.8 또는 1.2를 곱하여** 법적 기준선을 도출하십시오.
   - **[80% 이상 합법 그룹 (비타민, 무기질, 단백질 등)]**: (성적서 환산 실측값) $\ge$ (시안 표시량 $\times$ 0.8) 이면 합법(✅).
   - **[120% 미만 합법 그룹 (열량, 당류, 지방 등)]**: (성적서 환산 실측값) $\le$ (시안 표시량 $\times$ 1.2) 이면 합법(✅). 

✅ **Rule 12. [원재료명 3단 교차 검증 및 서류 환각 절대 금지]**
   - 배합비 없이 레시피를 상상하여 지적하지 마십시오. 

🔥 **Rule 13. [알레르기 '~함유' 키워드 정밀 추적]**
   - 시각적 형태가 아닌 **"~함유"**라는 텍스트 키워드를 문서 전체에서 추적하십시오. 

🔥 **Rule 14. [표 4 및 표 6 의무/예외 표기 마스터 룰 (숫자 묶음 표기 허용)]**
   - **[🚨향료 괄호 환각 절대 금지]**: '향료' 뒤에 '(착향료)'라고 괄호를 쳐서 지적하는 행위를 엄격히 금지합니다.
   - **[표 6 예외 표기 및 숫자 묶음 합법성]**: 구연산나트륨 등을 묶어서 시안에 **"영양강화제 2종"**처럼 뒤에 숫자를 합성하여 표기하는 것은 완벽한 합법(✅)입니다.

✅ **Rule 15. [강조표시 및 효능/기능성 연쇄 불합격 스캔]**
   - 건강기능식품으로 오인할 수 있는 문구를 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가에서 100% 수입된 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 기만광고 판별]**
   - 사용 원천 금지된 첨가물을 뺐다고 강조했다면 '기만광고(🚨)' 처리하십시오.

✅ **Rule 18. [영유아 타겟 명칭 금지]**
   - 일반 식품에 '베이비, 아기' 등의 단어 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 절대 분리]**
   - '무당'은 당류 0.5g 미만, '무가당'은 인위적 당류 첨가 없을 때 합법입니다.

✅ **Rule 20. [용기·포장재질 표기법 스캔 및 직접 접촉 원칙]**
   - 포장재질 텍스트 란에는 **'내용물(식품)과 직접 접촉하는 재질'**만 적는 것이 원칙입니다.

🔥 **Rule 21. [비타민/무기질 영양강조표시 다중 조건 완벽 계산]**
   - 칼슘 등 강조 시 4가지 기준(100g, 100mL, 100kcal, 1회 섭취참고량) 중 **단 하나라도 만족하면 합법(✅)**입니다. 

✅ **Rule 22. [다국어 폰트 크기 및 로고 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. 단, 로고는 예외.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 및 예외 구간 범용 마스터 룰]**
   - **트랜스지방:** 0.2~0.5g 미만 **"0.5g 미만"** 표시.
   - **콜레스테롤:** 2~5mg 미만 **"5mg 미만"** 표시.
   - **포화지방 등:** 0.5g 미만 "0g" 표시.

✅ **Rule 24. [감미료 14pt 의무 표기]**
   - 무당 강조 시 14포인트 이상 "감미료 함유" 표시.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위와 총 내용량 수치를 분리하여 검증.

✅ **Rule 26. [고체 vs 액체 단위 엄격 구분]**
   - 고체면 중량, 액체면 용량 표기 검사.

✅ **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]**
   - 열량, 당류 등 제한 성분은 100kcal 당 조건 적용 금지.

🔥 **Rule 28. [원산지 과잉 지적 절대 금지]**
   - 하위 성분까지 파고들어 원산지 추가 요구 금지.

🔥 **Rule 29. [복합원재료 원산지 표시의 한계]**
   - 복합원재료 자체 원산지만 확인.

🔥 **Rule 30. [호밀/보리 알레르기 환각 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.** ✅ **Rule 31. [다중 성적서 처리]**
   - 모든 영양성분을 누락 없이 대조.

✅ **Rule 32. [균형 열량 구성비 역산 금지]**
   - 단순 역산으로 부적합 처리 금지.

✅ **Rule 33. [데이터 출처 완벽 분리 표기 강제 룰]**
   - 서류 수치와 시안 수치를 분리.

✅ **Rule 34. [2% 미만 원재료 순서 자유 배열]**
   - 2% 미만 원료는 순서 자유.

✅ **Rule 35. [서류 명칭 일치 간략명 허용]**
   - 의미상 일치하면 적합 처리.

✅ **Rule 36. [오탈자 정밀 스캔]**
   - 주의사항 문구 오탈자 스캔.

✅ **Rule 37. [법적 서류 절대 우선의 원칙]**
   - 서류 기준으로 누락/과장 판별.

🔥 **Rule 38. [교차오염 경고 상호 배타성 원칙]**
   - 원재료에 있는 원료를 '제조시설 공유'에 중복 기재 위반.

✅ **Rule 39. [동명 원료 종속성 원칙]**
   - 복합원재료 각각 독립적으로 검증.

✅ **Rule 40. [열량 5kcal 단위 반올림 절대 우선]**
   - 오차율 계산 전 가장 가까운 5kcal 반올림.

✅ **Rule 41. [% 영양소 기준치 정밀 검증 및 기준치 환각 금지]**
   - 비타민E의 1일 기준치는 11 mg α-TE입니다.

✅ **Rule 42. [완제품 서류 혼동 절대 금지]**
   - 완제품 성적서만 사용.

✅ **Rule 43. [시각적 오독 방어]**
   - 글자가 작으면 "육안 재확인 요망".

✅ **Rule 44. [혼합제제 하위성분 전개 합법성]**
   - 구성 성분 확인 시 적합.

✅ **Rule 45. [전략적 누락 허용]**
   - 마케팅적 누락 지적 금지.

🔥 **Rule 46. [제품명 숫자 강조 시 전개]**
   - 숫자 포함 시 개별 전개 스캔.

🔥 **Rule 47. [선물용 포장 100% 일치의 한계 및 강박증 방어 룰]**
   - 내포장(팩)과 외포장(박스)의 **'원재료명'과 '영양성분'은 100% 일치**해야 합니다.
   - **[🚨물리적 차이 지적 금지]**: 단, 소비기한 표기 문구(상단 vs 측면) 등은 서로 다른 것이 합법(✅)입니다.

🔥 **Rule 48. [서류 역할 분리]**
   - 배합비(투입량 순서) vs 한글라벨(최종 명칭).

🔥 **Rule 49. [균형영양식 강제 전개 합법성]**
   - 혼합제제 해체 전개 완벽한 합법.

🔥 **Rule 50. ['원액/100%' 명칭 기만광고 판별 룰 (단일 원료 vs 혼합 원료 명확한 구분)]**
   - **[✅합법 조건]**: 특정 단일 원료 자체가 순수한 원액이라면 '원액' 표기는 완벽한 합법입니다. 최종 제품 공정에서 다른 첨가물과 섞인다고 해서 이 원료의 명칭을 지적하는 오작동을 엄격히 금지합니다.
   - **[🚨기만광고 적발 조건]**: 단, 해당 '원액'이라고 납품받은 원료 **자체의 하위 성분(괄호 안)**에 정제수, 덱스트린, 효소제 등이 섞여 있음에도 묶어서 '100% 원액'이라고 부르는 경우에만 🚨부적합 처리하고 '액'으로 수정 지시하십시오.

🔥 **Rule 51. [사용자 커스텀 PDF 표 해독]**
   - 왼쪽 열 시안, 오른쪽 열 합법 데이터 1:1 매칭.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    
    # [인쇄용 CSS 핵심 패치 유지]
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

    st.title("🏭 식품 표시사항 정밀 검토 (V6.81 - 원액/접촉면 마스터판)")
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
        
        # 🚨 안전 필터 완전 해제
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
        모든 판단 결과 앞에는 반드시 ✅(적합) 또는 🚨(부적합)을 붙이십시오.
        아래 7단계 목차 형식을 100% 준수하십시오.

        ## 1️⃣ [주표시면 및 마케팅 뱃지 (Rule 50 적용)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령1 (영양강조 다중조건 계산)]: 비타민/무기질(칼슘 등)의 '고/풍부' 강조를 판별할 때 1가지 기준만 보지 마십시오. 4가지 기준의 % 허용치를 모두 계산해 본 뒤, 단 하나라도 만족한다면 완벽한 합법(✅) 처리하십시오.
        
        ## 2️⃣ [원재료명 및 원산지 대조 (Rule 48, 49, 50, 51 적용)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령2]: 배합비 상위 3순위가 아닌 미량 원료의 원산지 누락 지적을 100% 금지합니다.
        - 🚨 [긴급 차단 명령3 (표6 숫자 묶음 합법)]: "영양강화제 2종"처럼 용도명 뒤에 숫자가 붙은 묶음 표기를 보더라도 완벽한 합법(✅)이므로 절대 부적합 처리하지 마십시오.
        - 🚨 [긴급 차단 명령4 (향료 괄호 금지)]: '향료' 뒤에 '(착향료)'라고 괄호를 쳐서 용도명을 병기하라고 지적하는 행위를 100% 엄격히 금지합니다.
        | No | 시안 원재료명 (개별 전개) | 한글라벨 매칭 원료 | 배합비 순서 검증 | 판정 및 수정안 |
        |---|---|---|---|---|
        
        ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령5 (호밀 알레르기 환각 금지)]: 원재료에 '호밀'이나 '호밀농축액'이 있다고 해서 알레르기 유발물질에 '밀'을 추가하라고 지적하는 행위를 엄격히 금지합니다.
        
        ## 4️⃣ [영양표시 및 % 기준치 검증]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령6]: 나쁜 영양소는 하한선이 없고, 좋은 영양소는 상한선이 없습니다.
        - 🚨 [긴급 차단 명령7 (산수 붕괴 방지)]: **암산 금지!** 표의 '법적 허용오차 기준선' 칸에 반드시 "[시안 표시량] * 0.8 = [값] 이상" 또는 "[시안 표시량] * 1.2 = [값] 미만" 이라고 타이핑해서 계산식을 노출하십시오. 
        - 🚨 [긴급 차단 명령8 (0표시 예외구간 범용 방어)]: 콜레스테롤, 포화지방, 트랜스지방 등 영양소가 '0' 표시 기준을 초과했다면 Rule 23을 대입하여 범용적으로 정답을 제시하십시오.
        | 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식 필수) | 1일 기준치 | 시안 % | % 검증 (계산식) | 판정 및 수정안 |
        |---|---|---|---|---|---|---|---|---|
        
        ## 5️⃣ [기타 법적 의무사항]
        - 결론: (✅ 또는 🚨)
        
        ## 6️⃣ [외포장(선물세트) vs 내포장(팩) 1:1 전수 대조 결과]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령9 (식품 접촉면 & 정보 일치 강제 검증)]: 
          1) **식품 접촉면 검증**: 내/외포장 모두 텍스트 표기란에 **'식품과 직접 닿는 면의 재질(예: 폴리에틸렌 등)'**이 누락 없이 제대로 표시되어 있는지 확인하십시오. (박스가 종이라고 해서 텍스트로 외포장 종이를 적으라고 지적하지 마십시오).
          2) **정보 100% 일치 검증**: 소비기한 위치, 재질 같은 물리적 차이를 제외하고, **나머지 모든 텍스트 정보(원재료명, 영양성분, 주의사항 등)가 내/외포장 간에 100% 일치하는지** 전수 대조하여 결과를 브리핑하십시오.
        
        ## 7️⃣ [종합의견 및 즉시 수정 지시사항]
        """
        
        response = model.generate_content(
            user_content + [final_prompt], 
            generation_config=genai.types.GenerationConfig(temperature=0.0),
            safety_settings=safety_settings
        )
        return response.text

    if st.button("🔍 전수 룰 QC 시작", type="primary"):
        has_files = any([
            img_main, img_info, img_nutri, img_extra,
            img_inner_main, img_inner_info, img_inner_nutri, img_inner_extra,
            report_docs, recipe_docs, legal_docs
        ])
        if not has_files:
            st.warning("🚨 검토할 시안이나 서류 파일을 최소 1개 이상 업로드해주세요!")
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

        with st.spinner(f"51대 룰북 원문 100% 적용 검증 중... [{inspection_mode}]"):
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
                st.markdown(result_text)
            except Exception as e: 
                st.error(f"🚨 오류: {e}")
            finally:
                for f in glob.glob("temp_*"): 
                    os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
