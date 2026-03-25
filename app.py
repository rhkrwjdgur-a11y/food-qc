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
   - **[🚨과잉 해석 금지]**: 배합비 상위 3순위에 해당하지 않는 미량 원료(예: 0.3% 투입된 페이스트, 천일염 등)에 대해서는 하위 성분의 원산지가 서류에 있더라도 시안에 기재하라고 지적하는 것을 엄격히 금지합니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (하위 향료 통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽한 합법입니다. 시안에 개별 향료명을 추가하라고 지적하지 마십시오.

✅ **Rule 3. 영양정보 vs 강조표시 (이원화 대조)**
   - 영양성분표의 수치와 주표시면의 마케팅 강조 문구가 서로 충돌하지 않는지 최우선으로 대조하여 모순이 발생하면 즉시 부적합 처리하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 적합으로 인정하십시오. 

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 전면 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다. 시안에 복합원재료 명칭만 단독으로 적혀 있다면 완벽한 합법입니다.
   - **[✅감미료/향료 생략 허용]**: 5% 미만 복합원재료에 포함된 감미료(스테비아 등)나 향료가 시안에서 생략되었더라도 지적하지 마십시오. 첨가물 이월(Carry-over) 원칙을 근거로 수정을 요구하지 마십시오.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 포함되어 있음에도 영양성분표의 당류가 0g으로 표기되어 있다면, 1회 제공량 당 0.5g 미만인지 수식을 역산하여 논리적 일치 여부를 검증하십시오.

✅ **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)**
   - 당알콜류 사용 시 설사 관련 문구를, 아스파탐 사용 시 "페닐알라닌 함유" 주의문구를 반드시 스캔하여 누락 시 지적하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 '외국산' 또는 '수입산'으로 표기해도 합법으로 간주하십시오.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분하여 표기되었는지 확인하십시오. (식품유형: 가공두유 등)

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 심사하십시오.

🔥 **Rule 11. [영양정보 허용오차 계산 절대 법칙 (하/상한선 및 역산 오류 완전 방지)]**
   - **[🚨역산 절대 금지]**: 성적서 실측값에 0.8을 곱하는 멍청한 짓을 절대 하지 마십시오. 무조건 **'시안 표시량'에 0.8 또는 1.2를 곱하여** 법적 기준선을 도출하십시오.
   - **[80% 이상 합법 그룹 (좋은 영양소)]**: 비타민, 무기질, 단백질, 탄수화물, 식이섬유. 
     * 수식: **(성적서 환산 실측값) $\ge$ (시안 표시량 $\times$ 0.8)** 이면 합법(✅)입니다. 상한선은 절대 없습니다.
   - **[120% 미만 합법 그룹 (나쁜 영양소)]**: 열량, 당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨. 
     * 수식: **(성적서 환산 실측값) $\le$ (시안 표시량 $\times$ 1.2)** 이면 합법(✅)입니다. 

✅ **Rule 12. [원재료명 3단 교차 검증 및 서류 환각 절대 금지]**
   - 배합비가 업로드되지 않았다면 절대 임의로 레시피를 상상하여 지적하지 마십시오. 

🔥 **Rule 13. [알레르기 '~함유' 키워드 텍스트 정밀 추적]**
   - 시각적 형태가 아닌 **"~함유"** (예: 대두, 밀 함유)라는 텍스트 키워드를 문서 전체에서 추적하십시오. 

🔥 **Rule 14. [표 4 및 표 6 의무/예외 표기 마스터 룰 (숫자 묶음 표기 허용)]**
   - **[표 4]**: 6가지 용도(감미료, 발색제, 보존료, 산화방지제, 착색료, 향미증진제)에 대해서만 용도명을 괄호로 병기하십시오.
   - **[표 6 예외 표기 및 숫자 묶음 합법성]**: 구연산나트륨, 제이인산나트륨 등은 개별 명칭 대신 **'영양강화제' 또는 '산도조절제'**라는 주용도명으로 묶어서 표기하는 것이 합법입니다.
   - **[✅ N종 묶음 표기 전면 허용]**: 이때 시안에 **"영양강화제 2종"**처럼 뒤에 숫자를 합성하여 묶음 표기하는 것도 실무적으로 완벽한 합법(✅)입니다. 숫자가 붙었다고 임의 합성이라며 지적하거나 빼라고 지시하는 것을 엄격히 금지합니다.

✅ **Rule 15. [강조표시 및 효능/기능성 연쇄 불합격 스캔]**
   - 건강기능식품으로 오인할 수 있는 마케팅 문구가 있는지 스캔하여 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 특정 원재료가 단일 국가에서 100% 수입된 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 기만광고 판별 및 첨가물공전 지능 탑재]**
   - 법적으로 사용이 원천 금지된 첨가물을 뺐다고 강조했다면 '기만광고(🚨부적합)'로 처리하십시오.

✅ **Rule 18. [영유아 타겟 명칭 금지]**
   - 일반 식품의 제품명이나 광고에 '유아, 영아, 베이비, 아기' 등의 단어를 사용하여 영유아용으로 오인하게 만드는 행위를 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당(무첨가)' 절대 분리]**
   - '무당(Zero)'은 100g당 당류 0.5g 미만일 때만 합법, '무가당'은 인위적 당류 첨가가 없어야 합법입니다.

✅ **Rule 20. [용기·포장재질 표기법 정밀 스캔]**
   - 식약처 표준 포맷을 권장하나, 의미 전달이 가능하면 불필요한 수정 권고를 금지합니다.

✅ **Rule 21. [범용 영양강조표시 다중 조건 완벽 계산]**
   - 영양강조표시 심사 시 반드시 100g 환산 수식, 100kcal 환산 수식 등을 계산하십시오.

✅ **Rule 22. [다국어 폰트 크기 및 로고 예외]**
   - 외국어를 병기할 때는 한글 제품명보다 활자 크기가 작거나 같아야 합니다. 단, 로고는 예외.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 및 예외 구간 범용 마스터 룰]**
   모든 영양성분은 환산값이 '0 표시 기준'을 초과할 경우, 무식하게 1단위로 반올림하지 말고 아래의 **예외 구간 표기법**을 범용적으로 적용하십시오.
   - **트랜스지방:** 0.2g 미만 "0g" / 0.2g 이상 ~ 0.5g 미만은 **"0.5g 미만"** 으로 표시 / 0.5g 이상은 소수점 첫째 자리 표시.
   - **콜레스테롤:** 2mg 미만 "0mg" / 2mg 이상 ~ 5mg 미만은 **"5mg 미만"** 으로 표시 / 5mg 이상은 5mg 단위 반올림.
   - **포화지방, 당류, 지방, 탄수화물, 단백질:** 0.5g 미만 "0g" 표시 / 0.5g 이상은 소수점 첫째 자리 또는 정수 표시 유지.
   - **열량:** 5kcal 미만 "0kcal" 표시 / 5kcal 이상은 5kcal 단위 반올림.
   - **나트륨:** 5mg 미만 "0mg" 표시.

✅ **Rule 24. [감미료 14pt 의무 표기]**
   - 무당/Zero 강조 시 반드시 14포인트 이상의 글씨로 "감미료 함유"를 표시해야 합니다.

✅ **Rule 25. [다중 포장 듀얼 컬럼 분리 검증]**
   - [1단위(개당)] 수치와 [총 내용량(전체)] 수치를 분리하여 검증하십시오.

✅ **Rule 26. [고체 vs 액체 단위 엄격 구분]**
   - 내용량이 고체면 중량, 액체면 용량으로 표기되었는지 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]**
   - 열량, 당류, 지방 등 '제한'해야 하는 성분은 100kcal 당 조건을 적용하여 강제 합격시키지 마십시오.

🔥 **Rule 28. [원산지 과잉 지적(오지랖) 절대 금지]**
   - 배합비 하위 성분까지 파고들어 원산지를 추가 기재하라고 요구하지 마십시오.

🔥 **Rule 29. [복합원재료 원산지 표시의 한계]**
   - 복합원재료 자체의 원산지만 확인하십시오. 미량 하위 성분의 원산지 기재 요구는 금지합니다.

✅ **Rule 30. [한국 내수용 알레르기 22종 절대 준수 룰]**
   - 22종 외의 해외 알레르기 성분을 강제로 추가하라고 지적하지 마십시오.

✅ **Rule 31. [다중/무제한 성적서 처리 및 균형영양식 대응]**
   - 성적서가 여러 장이더라도 누락 없이 모든 영양성분을 대조하십시오.

✅ **Rule 32. [균형 열량 구성비 역산 금지]**
   - 단순 역산하여 오차가 난다고 부적합 처리하지 마십시오.

✅ **Rule 33. [데이터 출처 완벽 분리 표기 강제 룰]**
   - 서류 수치와 시안 수치를 명확한 표 형태로 분리하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 배합비율이 2% 미만인 원료들은 투입량 순서와 관계없이 기재할 수 있습니다.

✅ **Rule 35. [서류 명칭 일치 및 공전상 간략명 허용 룰]**
   - 비타민C와 L-아스코르빈산 등 공식 명칭이 의미상 일치하면 적합 처리하십시오.

✅ **Rule 36. [오탈자 정밀 스캔 및 환자식 1:1 매칭 룰]**
   - 복잡한 주의사항 문구에 오탈자나 띄어쓰기 오류가 없는지 픽셀 단위로 스캔하십시오.

✅ **Rule 37. [법적 서류 절대 우선의 원칙]**
   - 반드시 업로드된 법적 서류를 기준으로 누락/과장을 판별하십시오.

🔥 **Rule 38. [교차오염 경고 문구 상호 배타성 원칙]**
   - 원재료명 본문에 함유되어 있다고 명시된 원료를 '제조시설 공유' 경고에 중복 기재하는 것은 위반입니다.

✅ **Rule 39. [동명 원료 교차 혼선 금지 및 종속성 원칙]**
   - 동일한 원재료가 복합원재료 A와 B에 각각 들어갔을 때 독립적으로 검증하십시오.

✅ **Rule 40. [열량 5kcal 단위 반올림 절대 우선의 원칙]**
   - 오차율 계산 전, 실측값을 '가장 가까운 5kcal 단위'로 반올림하십시오.

✅ **Rule 41. [% 영양소 기준치 정밀 검증]**
   - 1일 영양성분 기준치 비율(%)은 (시안 표시량 ÷ 식약처 기준치) × 100 으로 도출하여 검증하십시오. (단, Rule 23에 의해 "미만"으로 텍스트 표기될 경우, 환산 실측값을 대입하여 계산한 정수값을 기재)

✅ **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**
   - 영양표시 검증에는 반드시 완제품 시험성적서만 사용하십시오.

✅ **Rule 43. [시각적 오독(OCR) 철통 방어]**
   - 글자가 작아 확신할 수 없으면 "육안 재확인 요망" 처리하십시오.

✅ **Rule 44. [혼합제제 넘버링 및 하위성분 전개 합법성]**
   - 부형제나 희석제가 기재되어 있더라도 구성 성분임이 확인되면 적합 처리하십시오.

✅ **Rule 45. [전략적 누락 허용 및 유령 성분 검토 금지]**
   - 마케팅적 이유로 강조를 포기(누락)한 것은 자유이므로 지적하지 마십시오.

🔥 **Rule 46. [제품명 '숫자+통칭(예: 17곡)' 강조 시 개별 함량 강제 전개]**
   - 숫자가 포함된 경우 합산 표기를 100% 금지하고 개별 전개되었는지 스캔하십시오.

🔥 **Rule 47. [선물용 포장(외포장/아웃박스) 100% 일치성 전수 검증]**
   - 선물세트 모드 시, 내포장과 외포장 정보가 100% 동일한지 대조하십시오.

🔥 **Rule 48. [서류 역할의 완벽한 분리 (배합비 vs 한글라벨)]**
   - **배합비 서류의 역할**: 원료의 '투입량 순서' 검증용.
   - **한글라벨 서류의 역할**: 시안에 적힌 명칭, 원산지 대조의 최종 텍스트 기준. 

🔥 **Rule 49. [특수의료용도식품(균형영양식) 혼합제제 강제 전개 (Flattening) 합법성]**
   - 서류에 `혼합제제(A, B, C)`로 묶여 있더라도, 시안에서는 이를 해체하여 `A, B, C`로 각각 흩어지게 전개(Flattening)하여 기재한 것은 완벽한 합법입니다.

🔥 **Rule 50. [범용 '원액/100%' 명칭 기만광고 판별 룰 (효소/첨가물 스캔)]**
   - 원재료명이나 마케팅 문구에 **'원액'** 또는 **'100%'**가 포함되었다면, 하위 성분에 **식품첨가물(효소제, 향료 등)**이 혼합되어 있는지 확인하십시오. 첨가물이 있다면 기만광고이므로 즉시 🚨부적합 처리하고 '액'으로 수정 지시하십시오.

🔥 **Rule 51. [사용자 커스텀 문서(PDF 표) 해독 완벽 가이드]**
   - 사용자가 업로드한 표 문서의 **왼쪽 열은 패키지에 적혀야 할 시안 텍스트**, **오른쪽 열은 합법적인 원료명/전개 데이터**입니다. AI는 반드시 이 좌우 매칭 관계를 1:1로 엮어서 검증해야 합니다.
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

    st.title("🏭 식품 표시사항 정밀 검토 (V6.73 - 표 6 'N종' 묶음 완벽 허용판)")
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
        
        ## 2️⃣ [원재료명 및 원산지 대조 (Rule 48, 49, 50, 51 적용)]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령1]: 배합비 상위 3순위가 아닌 미량 원료의 원산지 누락 지적을 100% 금지합니다.
        - 🚨 [긴급 차단 명령2]: 시안에 적힌 원료를 무조건 개별 행으로 쪼개서 표에 1:1 매칭하십시오. 
        - 🚨 [긴급 차단 명령3 (표6 숫자 묶음 합법)]: "영양강화제 2종"처럼 용도명 뒤에 숫자가 붙은 묶음 표기를 보더라도, 서류에 제이인산나트륨, 구연산나트륨 등 해당 원료가 실제로 존재한다면 완벽한 합법(✅)이므로 절대 부적합 처리하지 마십시오.
        | No | 시안 원재료명 (개별 전개) | 한글라벨 매칭 원료 (Rule 51 PDF 독해 적용) | 배합비 순서 검증 | 판정 및 수정안 |
        |---|---|---|---|---|
        
        ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
        - 결론: (✅ 또는 🚨)
        
        ## 4️⃣ [영양표시 및 % 기준치 검증]
        - 결론: (✅ 또는 🚨)
        - 🚨 [긴급 차단 명령4]: 나쁜 영양소는 하한선이 없고, 좋은 영양소는 상한선이 없습니다.
        - 🚨 [긴급 차단 명령5 (산수 붕괴 방지)]: **암산 금지!** 표의 '법적 허용오차 기준선' 칸에 반드시 "[시안 표시량] * 0.8 = [값] 이상" 또는 "[시안 표시량] * 1.2 = [값] 미만" 이라고 타이핑해서 계산식을 노출하십시오. 
        - 🚨 [긴급 차단 명령6 (0표시 예외구간 범용 방어)]: 콜레스테롤, 포화지방, 트랜스지방 등 영양소가 '0' 표시 기준을 초과했다면 기계적 반올림을 하지 마십시오. Rule 23에 명시된 해당 성분의 법적 최소 표기 단위(예: '5mg 미만', '0.5g 미만', 소수점 첫째 자리 등)를 대입하여 범용적으로 정답을 제시하십시오.
        | 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식 필수) | 1일 기준치 | 시안 % | % 검증 (계산식) | 판정 및 수정안 |
        |---|---|---|---|---|---|---|---|---|
        
        ## 5️⃣ [기타 법적 의무사항]
        - 결론: (✅ 또는 🚨)
        
        ## 6️⃣ [외포장(선물세트) vs 내포장(팩) 1:1 전수 대조 결과]
        - 결론: (✅ 또는 🚨)
        
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
