import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

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
# 📚 2. 통합 전문가 프롬프트 (54대 룰 완전 원상복구본)
# ==========================================
RULE_BOOK = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## 🚨 [⚖️ 1일 영양성분 기준치 (외부 데이터 개입 차단)] 🚨
주의: 사전 학습된 글로벌 데이터(예: 칼슘 1000mg 등) 적용을 금지합니다. 오직 아래 명시된 **한국 식약처 기준치**만 대입하여 %를 산출해야 합니다.
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

## ⚠️ 검토 대원칙: 54대 품질관리 지침 (단 한 글자도 생략 없이 엄수할 것)

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

🔥 **Rule 13. [알레르기 '~함유' 키워드 정밀 추적 및 역방향 검증]**
   - 시안의 **"~함유"** 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 존재해야 합니다.
   - **[🚨임의 판단 금지]**: 원재료명에 없는 물질이 '~함유'에 기재되어 있다면, 교차오염 등의 사유로 임의 해석하지 마시고 무조건 부적합(🚨) 처리하십시오.

🔥 **Rule 14. [표 4 및 표 6 의무/예외 표기 마스터 룰 (묶음 표기 허용)]**
   - **[🚨향료 괄호 관련 임의 지적 금지]**: '향료' 뒤에 '(착향료)' 용도명을 병기하라고 지적하는 것을 엄격히 금지합니다.
   - **[표 6 묶음 표기 적합성]**: 구연산나트륨 등을 묶어서 시안에 **"영양강화제 2종"**처럼 표기하는 것은 완벽한 적합(✅)입니다.

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

✅ **Rule 24. [감미료 14pt 의무 표기]**
   - 무당 강조 시 14포인트 이상 크기로 "감미료 함유"를 표시해야 합니다.

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

✅ **Rule 40. [열량 5kcal 단위 반올림 원칙]**
   - 오차율 계산 전 가장 가까운 5kcal 단위로 반올림 규정을 우선 적용하십시오.

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

🔥 **Rule 51. [사용자 커스텀 PDF 폼 해독]**
   - 제공된 문서의 시안 텍스트 열과 합법 기준 데이터 열을 1:1로 정확히 매칭하여 판별하십시오.

🔥 **Rule 52. [논리적 모순 탐지 및 정합성 검증]**
   - 제품명이나 마케팅 문구에 특정 숫자(예: '23곡', '15종', '5無')가 명시되어 있다면, 괄호 안 원재료명에 나열된 실제 항목의 개수(쉼표 개수 기반)와 **논리적/수학적으로 정확히 일치하는지 반드시 대조 카운트**하십시오.
   - 개수가 불일치하거나 데이터 간 충돌이 발생할 경우 임의로 적합 처리하지 말고, 무조건 🚨(확인 요망) 플래그와 함께 불일치 사유를 상세히 리포트하십시오.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 주표시면(앞면)의 **'제품명'에 특정 농수산물이나 원재료의 명칭(예: 딸기, 고구마, 홍삼 등)이 포함**되어 있는지 스캔하십시오.
   - 포함되어 있다면 다음 2가지를 강제 대조 검증하십시오.
     1) **함량 검증:** 주표시면에 해당 원료의 함량(%)이 명확히 명시되어 있는지 확인. (누락 시 🚨 부적합)
     2) **원산지 검증:** 해당 원료가 배합비 상위 3순위 밖 미량 원료이더라도, 정보표시면의 원재료명 리스트에 **해당 원료의 '원산지'가 반드시 기재**되어 있어야 합니다. (누락 시 🚨 부적합)

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성 검증 룰]**
   - 정보표시면 원재료명에 단일 원료에 대해 2개 이상의 국가가 쉼표(,)로 병기되어 있고(예: 가나산, 에콰도르산), **각 국가별 혼합 비율(%)이 기재되어 있지 않은 경우** 덮어놓고 적합(✅)으로 판정하지 마십시오.
   - 이 경우 반드시 🚨(확인 요망) 플래그를 띄우고, 판정 결과 란에 다음 문구를 출력하십시오: "복수 원산지가 혼합 비율(%) 없이 기재되었습니다. 농산물 원산지표시법에 따른 예외 조건(최근 3년 내 연평균 3회 이상 비율 변경 등)을 충족하는지 내부 실무 부서(수급/구매팀)와 확인이 필요합니다."
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

    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V24.0 - 3단계 완벽 검증판)")
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

    if st.button("🔍 3단계 파이프라인 정밀 검수 시작", type="primary"):
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

        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.markdown("🔄 **[준비 중]** 서류 및 이미지 데이터를 AI 분석 엔진에 로드합니다...")
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

        for f in glob.glob("temp_*"): 
            os.remove(f)

        progress_bar.progress(20)
        
        model = genai.GenerativeModel(MODEL_NAME)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=8192)

        try:
            # ==========================================================
            # 🟢 [1단계]: Thinking 에이전트 (원시 데이터 심층 추출 및 분석)
            # ==========================================================
            status_text.markdown("🧠 **[1/3 단계: Thinking]** 54대 룰북 원문을 기반으로 서류에서 모든 계산식과 데이터를 샅샅이 추출 중입니다...")
            
            prompt_step_1 = f"""
            당신은 데이터 분석의 천재 'Thinking 에이전트'입니다.
            업로드된 시안과 서류를 다음 [54대 룰북]에 따라 완벽하게 분석하십시오.
            
            [제품유형]: {product_type}
            [검토모드]: {inspection_mode}
            
            {RULE_BOOK}
            
            [지시사항]
            1. 절대 마크다운 표를 그리지 마십시오. 오직 분석 로그(텍스트)만 작성하십시오.
            2. [원재료명 파트]: 시안에 적힌 원료, 한글라벨 원료, 배합비 서류의 원료와 '투입 순위(%)'를 하나도 빠짐없이 텍스트로 적어두십시오.
            3. [영양성분 파트]: 9개 영양성분의 성적서 실측값, 환산 실측값, 시안 표시량, 그리고 식약처 허용오차 기준선 계산 수식을 직접 수학적으로 계산하여 적어두십시오.
            4. 글이 끊기지 않게 핵심만 명확히 개조식으로 기록하십시오.
            """
            
            res_1 = model.generate_content(user_content + [prompt_step_1], generation_config=generation_config, safety_settings=safety_settings)
            thinking_log = res_1.text
            progress_bar.progress(50)

            # ==========================================================
            # 🔵 [2단계]: Review 에이전트 (검토 및 자가 교정)
            # ==========================================================
            status_text.markdown("🕵️ **[2/3 단계: 검토/Review]** 1단계 분석 로그의 계산 오류, 누락된 데이터, 54번 룰 위반 여부를 철저히 교차 검증 중입니다...")

            prompt_step_2 = f"""
            당신은 세상에서 가장 깐깐한 QC 'Review 에이전트'입니다.
            앞선 Thinking 에이전트가 작성한 [1단계 분석 로그]를 읽고, 54대 룰북에 어긋나거나 누락된 부분이 없는지 교정하십시오.
            
            [1단계 분석 로그]
            {thinking_log}
            
            [교정 지시사항]
            1. '영양성분' 파트에서 1일 기준치 계산이 누락되었다면 직접 계산해서 채워 넣으십시오.
            2. '원재료명' 파트에서 배합비 순위가 없다면 반드시 추가하십시오.
            3. 교정이 완료된 완벽하고 깨끗한 [최종 분석 데이터] 텍스트만 출력하십시오. 표는 아직 그리지 마십시오.
            """

            res_2 = model.generate_content([prompt_step_2], generation_config=generation_config, safety_settings=safety_settings)
            verified_log = res_2.text
            progress_bar.progress(80)

            # ==========================================================
            # 🟣 [3단계]: Formatting 에이전트 (단계별 내용 및 표 정리)
            # ==========================================================
            status_text.markdown("📊 **[3/3 단계: 표 정리/Formatting]** 검증이 끝난 데이터를 바탕으로 7단계 최종 마크다운 리포트를 렌더링 중입니다...")

            prompt_step_3 = f"""
            당신은 마크다운 디자인 마스터 'Formatting 에이전트'입니다.
            앞선 Review 에이전트가 완벽하게 교정한 [최종 분석 데이터]를 바탕으로 7단계 정식 리포트 표를 생성하십시오.
            
            [최종 분석 데이터]
            {verified_log}
            
            🚨 [강제 렌더링 규칙] 🚨
            1. 표 작성 시 반드시 행마다 엔터(줄바꿈)를 엄수하여 표가 깨지지 않도록 하십시오.
            2. 데이터가 누락된 빈칸을 남기지 마십시오.
            
            [출력 양식]
            모든 결론 앞에는 ✅(적합), 🚨(부적합), 🚨(확인 요망)을 붙이십시오.

            ## 1️⃣ [주표시면 및 마케팅 뱃지]
            - 결론: 
            - 특이사항 요약: 
            
            ## 2️⃣ [원재료명 및 원산지 대조]
            - 결론: 
            | No | 시안 원재료명 | 한글라벨 매칭 원료 | 배합비 검증 (순위 필수) | 판정 및 수정안 |
            |---|---|---|---|---|
            (여기에 완벽한 줄바꿈으로 표 작성)
            
            ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
            - 결론: 
            
            ## 4️⃣ [영양표시 및 % 기준치 검증]
            - 결론: 
            | 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식) | 1일 기준치 | 시안 % | % 검증 | 판정 |
            |---|---|---|---|---|---|---|---|---|
            (여기에 완벽한 줄바꿈으로 표 작성)
            
            ## 5️⃣ [기타 법적 의무사항]
            - 결론: 
            
            ## 6️⃣ [외포장 vs 내포장 1:1 전수 대조 결과]
            - 결론: 
            
            ## 7️⃣ [종합의견 및 조치 필요사항]
            """

            res_3 = model.generate_content([prompt_step_3], generation_config=generation_config, safety_settings=safety_settings)
            
            progress_bar.progress(100)
            status_text.markdown("✨ **[완료]** 3단계 정밀 검증 파이프라인이 성공적으로 종료되었습니다.")
            time.sleep(1)
            
            progress_bar.empty()
            status_text.empty()

            # UI 출력 구성
            with st.expander("🧠 1단계 [Thinking] 및 2단계 [Review] 상세 로그 보기"):
                st.markdown("### 1. Thinking 엔진 로그")
                st.markdown(thinking_log)
                st.markdown("---")
                st.markdown("### 2. Review 엔진 교정 로그")
                st.markdown(verified_log)
            
            st.markdown(res_3.text)

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"🚨 시스템 런타임 오류 발생: {e}\n\n서버 트래픽 지연입니다. 새로고침(F5) 후 다시 시도해 주십시오.")

if __name__ == "__main__":
    if check_password(): main()
