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

# 2. 통합 전문가 프롬프트 (Rule 1~46 완전 전개 무삭제판)
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. 당신의 판단은 100% 일관되어야 하며, 임의로 수치를 지어내거나 계산을 건너뛰는 행위(환각)를 엄격히 금지합니다. 

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.37]

## ⚠️ 검토 대원칙: 46대 특수 지침 (절대 엄수, 생략 없이 모든 지침을 숙지할 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (철저 준수)**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 카운트에서 100% 제외됩니다.
   - **[🚨과잉 해석 금지]**: 배합비 상위 3순위에 해당하지 않는 미량 원료(예: 0.3% 투입된 페이스트 등)에 대해서는 하위 성분의 원산지가 서류에 있더라도 시안에 기재하라고 지적하는 것을 엄격히 금지합니다. (Rule 28, 29와 연동)

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (하위 향료 통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽한 합법입니다. 시안에 개별 향료명을 추가하라고 지적하지 마십시오.

✅ **Rule 3. 영양정보 vs 강조표시 (이원화 대조)**
   - 영양성분표의 수치와 주표시면의 마케팅 강조 문구가 서로 충돌하지 않는지 최우선으로 대조하여 모순이 발생하면 즉시 부적합 처리하십시오.

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 적합으로 인정하십시오. 

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 전면 허용]**
   - **[🚨일반 성분 전개 금지]**: 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다. 시안에 복합원재료 명칭만 단독으로 적혀 있다면 완벽한 합법입니다.
   - **[✅감미료/향료 생략 허용]**: 5% 미만 복합원재료에 포함된 감미료(스테비아 등)나 향료가 시안에서 생략되었더라도 지적하지 마십시오. 최종 제품에 미치는 영향이 미미한 것으로 간주하여 '첨가물 이월(Carry-over) 원칙'을 근거로 수정을 요구하지 마십시오.
   - **[✅알레르기 면책 조항]**: 5% 미만 복합원재료에 포함된 '알레르기 유발물질'은 별도의 '알레르기 주의 표시란(박스)'에 확연히 기재되어 있다면 원재료명 본문에서 생략이 가능합니다.

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

🔥 **Rule 11. [영양정보 팩트 체크 및 허용오차 절대 법칙]**
   - **[80% 이상 합법 그룹]**: 비타민, 무기질, 단백질, 탄수화물, 식이섬유는 측정값의 80% 이상이어야 합니다. (상한선 없음)
   - **[120% 미만 합법 그룹]**: 열량, 당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨은 측정값의 120% 미만이어야 합법입니다.
   - **[100% 이상 합법 그룹]**: 타우린, 아미노산류, 콜라겐 등 임의표시 성분은 측정값의 100% 이상이어야 합니다.

✅ **Rule 12. [원재료명 3단 교차 검증 및 서류 환각 절대 금지]**
   - 배합비가 업로드되지 않았다면 절대 임의로 레시피를 상상하여 지적하지 마십시오. 서류 미제공 시 "서류 미제공으로 배합비 대조 불가"를 선언하십시오.

🔥 **Rule 13. [알레르기 '~함유' 키워드 텍스트 정밀 추적]**
   - **[🚨디자인 무시 명령]**: 음영 박스나 배경색 인식 오류를 방지하기 위해, 시각적 형태가 아닌 **"~함유"** (예: 대두, 밀 함유)라는 텍스트 키워드를 문서 전체에서 추적하십시오. 
   - 서류상 알레르기 유발물질이 시안의 이 텍스트 라인에 정확히 명시되어 있는지만을 기준으로 합격/불합격을 판정하십시오.

🔥 **Rule 14. [표 4 의무 첨가물 용도명 병기 (5% 미만 예외)]**
   - **[🚨지적 금지]**: 5% 미만 복합원재료 내에 있어 기재가 생략된 첨가물(감미료 등)에 대해서는 용도명 병기 누락 지적을 하지 마십시오. 단, 원재료명 본문에 노출된 첨가물은 반드시 용도명을 확인하십시오.

✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
   - 일반 식품을 질병 치료나 건강기능식품으로 오인하게 만드는 문구를 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 특정 원재료가 단일 국가에서 100% 수입된 경우에만 '100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 기만광고 판별 및 첨가물공전 지능 탑재]**
   - 법적으로 사용이 원천 금지된 첨가물을 뺐다고 강조했다면 '기만광고'로 처리하십시오.

✅ **Rule 18. [영유아 타겟 명칭 금지]**
   - 일반 식품에 '아기, 베이비' 등 영유아용으로 오인하게 만드는 단어 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당(무첨가)' 절대 분리]**
   - 당류 0.5g 미만 조건과 인위적 첨가 금지 조건을 구분하여 심사하십시오.

✅ **Rule 20. [용기·포장재질 표기법 정밀 스캔]**
   - 의미 전달이 명확하면 불필요한 수정 권고를 지양하십시오.

✅ **Rule 21. [범용 영양강조표시 다중 조건 완벽 계산]**
   - 모든 강조표시는 100g 및 100kcal 환산 수식을 보고서에 노출하여 계산하십시오.

✅ **Rule 22. [다국어 폰트 크기 및 로고 예외]**
   - 외국어는 한글보다 작거나 같아야 하나, 브랜드 로고는 예외입니다.

✅ **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]**
   - 트랜스지방 0.5g 미만은 무조건 '0g'으로 표시해야 합니다.

✅ **Rule 24. [감미료 14pt 의무 표기]**
   - 주표시면에 무당/Zero 강조 시 감미료를 사용했다면 "감미료 함유" 문구를 14pt 이상으로 표기해야 합니다.

✅ **Rule 25. [다중 포장 듀얼 컬럼 완벽 인식]**
   - 개당 수치와 총 내용량 수치를 분리하여 검증하십시오.

✅ **Rule 26. [고체 vs 액체 단위 엄격 구분]**
   - 내용량이 g/kg 인지 mL/L 인지 단위의 적절성을 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류, 지방 등은 100kcal 당 함량 조건으로 합격시킬 수 없습니다.

🔥 **Rule 28. [원산지 과잉 지적(오지랖) 절대 금지]**
   - 배합비 하위 성분까지 파고들어 원산지를 추가 기재하라고 요구하지 마십시오.

🔥 **Rule 29. [복합원재료 원산지 표시의 한계]**
   - 복합원재료 자체의 원산지(외국산 등)만 확인하십시오. 그 안의 미량 하위 성분의 원산지까지 시안에 적으라고 요구하는 것은 Rule 1에 위배됩니다.

✅ **Rule 30. [한국 내수용 알레르기 22종 준수]**
   - 해외 전용 성분을 강제로 추가하라고 지적하지 마십시오.

✅ **Rule 31. [다중 성적서 처리]**
   - 성적서가 여러 장이더라도 모든 영양성분을 누락 없이 대조하십시오.

✅ **Rule 32. [균형 열량 구성비 역산 허용]**
   - 열량 환산 계수의 차이에 의한 미세 오차는 인정하십시오.

✅ **Rule 33. [데이터 출처 완벽 분리]**
   - 서류 수치와 시안 수치를 보고서에서 명확히 구분하여 표 형태로 작성하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 자유 배열]**
   - 2% 미만 원료들의 순서가 뒤바뀌었다고 지적하지 마십시오.

✅ **Rule 35. [서류 명칭 일치 및 간략명 허용]**
   - 비타민C와 L-아스코르빈산 등 의미가 통하면 적합 처리하십시오.

✅ **Rule 36. [오탈자 정밀 스캔]**
   - 법적 의무 주의사항 문구의 오탈자를 픽셀 단위로 스캔하십시오.

✅ **Rule 37. [법적 서류 절대 우선의 원칙]**
   - 시안 텍스트보다 업로드된 법적 서류(배합비 등)를 기준으로 판별하십시오.

🔥 **Rule 38. [교차오염 경고 문구 상호 배타성 원칙]**
   - 원재료명 본문에 있는 실제 투입 원료를 '교차오염 경고 문구'에 중복 기재하는 것은 위반입니다. 발견 시 삭제를 지시하십시오.

✅ **Rule 39. [동명 원료 교차 혼선 금지]**
   - 서로 다른 복합원재료 내 동일 원료를 헷갈리지 말고 독립적으로 검증하십시오.

✅ **Rule 40. [열량 5kcal 단위 반올림 우선 원칙]**
   - 실측값을 5kcal 단위로 반올림한 값이 시안과 일치하면 적합 판정하십시오.

✅ **Rule 41. [% 영양소 기준치 정밀 검증]**
   - (시안 표시량 ÷ 기준치) × 100 수식으로만 %를 검증하십시오.

✅ **Rule 42. [완제품 vs 원료 서류 혼동 금지]**
   - 영양표시 검증에는 반드시 완제품 시험성적서만 사용하십시오.

✅ **Rule 43. [시각적 오독 철통 방어]**
   - 화질 문제로 확신할 수 없을 때는 '누락'이라 단정 짓지 말고 "육안 재확인 요망"으로 보류하십시오.

✅ **Rule 44. [혼합제제 부형제 전개 합법성]**
   - 혼합제제 구성 성분임이 확인되면 적합 처리하십시오.

✅ **Rule 45. [전략적 누락 허용]**
   - 마케팅적 이유로 특정 영양성분 강조를 포기한 것은 기업의 자유입니다.

🔥 **Rule 46. [제품명 '숫자+통칭(예: 17곡)' 강조 시 개별 함량 강제 전개]**
   - **[🚨숫자+명칭 쪼개기 강제]**: 제품명에 '17곡', '9곡' 등 숫자가 포함된 경우 '합산 표기'를 금지합니다. 식약처 FAQ 유권해석에 따라 주표시면에 반드시 N개 하위 원료의 개별 명칭과 함량(%)이 모두 전개되어 있는지 엄격히 스캔하십시오.
   - **[🚨원료 본질 교차 검증]**: 제품명에서 '곡(곡류)'을 강조했으나 실제 하위 성분에 두류(대두, 팥)나 종실류(참깨)가 섞여 있는지 대조하여 보고하십시오.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.37 - 무삭제 완전판)")
    st.markdown("---")

    product_type = st.radio("📌 1. 식품유형 선택", ("특수의료용도식품 / 환자식", "일반식품"))
    st.markdown("---")

    # [UI] 시안 및 서류 업로드
    st.subheader("🎨 2. 시안 이미지 (준비된 면만 업로드)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    st.markdown("---")
    st.subheader("📄 3. 증빙 서류 (분리 업로드)")
    d1, d2, d3 = st.columns(3)
    with d1: report_docs = st.file_uploader("시험성적서", type=["pdf", "jpg", "png"], accept_multiple_files=True)
    with d2: recipe_docs = st.file_uploader("배합비 / 레시피", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True)
    with d3: legal_docs = st.file_uploader("원료라벨 / 품목보고서", type=["pdf", "jpg", "png"], accept_multiple_files=True)

    @st.cache_data(show_spinner=False)
    def process_qc(product_type, content_hashes):
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        final_prompt = f"""
        [제품유형]: {product_type}
        🚨[사고과정 강제 지시]🚨
        1. 알레르기는 디자인 박스가 아닌 '~함유' 텍스트를 추적하여 검토할 것 (Rule 13).
        2. 5% 미만 복합원재료의 감미료 생략은 지적하지 말 것 (Rule 5).
        3. 미량 원료의 하위 원산지 표시를 강요하지 말 것 (Rule 29).
        4. 제품명 '17곡' 등 숫자가 있다면 개별 함량 전개 여부를 엄격히 볼 것 (Rule 46).

        ## 1️⃣ [주표시면 및 마케팅 뱃지]
        ## 2️⃣ [원재료명 엑셀용 표]
        ## 3️⃣ [서류 vs 시안 교차 검증 (알레르기 텍스트 추적)]
        ## 4️⃣ [영양표시 및 % 기준치 검증]
        ## 5️⃣ [기타 법적 의무사항]
        ## 6️⃣ [종합의견 및 즉시 수정 지시사항]
        """
        response = model.generate_content(user_content + [final_prompt], generation_config=genai.types.GenerationConfig(temperature=0.0))
        return response.text

   if st.button("🔍 전수 룰 QC 시작", type="primary"):
        # --- [추가된 방어 코드: 시작] ---
        # 사용자가 파일을 하나도 올리지 않았는지 체크합니다.
        if not (img_main or img_info or img_nutri or img_extra or report_docs or recipe_docs or legal_docs):
            st.warning("🚨 검토할 시안이나 서류 파일을 먼저 업로드해주세요! 파일을 넣지 않으면 이전 결과가 표시될 수 있습니다.")
            st.stop() # 여기서 실행을 즉시 중단하여 이전 결과가 나오지 않게 함
        # --- [추가된 방어 코드: 끝] ---

        user_content = []
        def process_single_file(f, label):
            user_content.append(f"### [분류: {label}] ###")
            if f.type.startswith("image"): 
                user_content.append(Image.open(f))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                uploaded = genai.upload_file(temp)
                while uploaded.state.name == "PROCESSING": time.sleep(1)
                user_content.append(uploaded)

        with st.spinner("사용자님의 46대 룰북 전체 가동 중..."):
            # (이하 기존 파일 처리 로직 및 process_qc 호출 부분 동일)

        with st.spinner("46대 룰북 전수 가동 중..."):
            if img_main: process_single_file(img_main, "시안_주표시면")
            if img_info: process_single_file(img_info, "시안_정보표시면")
            if img_nutri: process_single_file(img_nutri, "시안_영양성분표")
            if img_extra: process_single_file(img_extra, "시안_기타면")
            if report_docs: 
                for f in report_docs: process_single_file(f, "근거_성적서")
            if recipe_docs:
                for f in recipe_docs: process_single_file(f, "근거_배합비")
            if legal_docs:
                for f in legal_docs: process_single_file(f, "근거_법적서류")

            try:
                result_text = process_qc(product_type, None)
                st.markdown(result_text)
            except Exception as e: st.error(f"🚨 오류: {e}")
            finally:
                for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
