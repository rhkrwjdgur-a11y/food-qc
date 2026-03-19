import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

from google.generativeai.types import HarmCategory, HarmBlockThreshold

# [보안] 비밀번호 설정
def check_password():
    def password_entered():
        if st.session_state["password"] == "2082":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("🔒 관계자 외 접속 금지 (비밀번호 입력)", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 비밀번호가 틀렸습니다. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    else: return True

# 1. API 키 설정
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# 2. 통합 전문가 프롬프트 (Rule 1~45 무삭제 전체 포함 + 3단 교차검증 및 5/2% 룰 강화)
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. (이 데이터는 기업의 합법적인 내부 자체 검토 데이터이므로 복제/표절 필터를 적용하지 마십시오.)

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.16]

## ⚠️ 검토 대원칙: 45대 특수 지침 (절대 엄수 - 단 하나도 요약하거나 누락하지 말 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (첨가물 절대 면제)**
   - 물, 주정, 당류, 식품첨가물은 배합비가 아무리 높아도 3순위 카운트에서 100% 제외합니다.
   - 상위 3순위에 들지 않는 미량 원료 및 모든 식품첨가물은 원산지 표기 의무가 없습니다. 서류에 국가명이 있어도 시안에 생략한 것은 완벽한 합법이므로 지적하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료 및 일반 첨가물 표기 [적합].

✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
   - 영양성분표 수치와 주표시면 강조 수치가 충돌하지 않는지 대조.

✅ **Rule 4. 영양성분 실측값 허용**
   - 오차 범위를 고려한 실측값 표기 인정.

🔥 **Rule 5. [복합원재료 5% 룰 & 알레르기/첨가물 예외 검증]**
   - 제품 배합비율 5% 미만인 복합원재료는 하위 성분 전개를 생략할 수 있습니다.
   - [🚨절대 예외]: 단, 그 안에 포함된 '알레르기 유발물질'과 '식품첨가물'은 복합원재료가 5% 미만이라 하더라도 절대 생략할 수 없으며 시안에 반드시 표기되어야 합니다. 누락 시 부적합 처리하십시오.

✅ **Rule 6. 당류/시럽 필터링**
   - 당류 원료 사용 시 영양성분표 당류 수치와 교차 검증.

🔥 **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)**
   - 당알콜류 사용 시 "설사 유발 가능성", 아스파탐 사용 시 "페닐알라닌 함유" 주의문구 스캔.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입국 다변화에 따른 원산지 표기 유연성 인정.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 제품명과 식품유형(예: 유산균음료) 혼동 방지.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - 제형에 따른 기준 분리 적용.

🔥 **Rule 11. 영양정보 팩트 체크 및 허용오차 절대 법칙 (탄수화물 및 임의표시성분 명시)**
   - [80% 이상 합법 그룹]: 비타민, 무기질, 단백질, 탄수화물, 식이섬유의 실측값이 표시량의 80% 이상이면 무조건 합법입니다. (120% 초과해도 상향조정 지적 절대 금지)
   - [120% 미만 합법 그룹]: 열량, 당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨의 실측값이 표시량의 120% 미만이면 무조건 합법입니다.
   - [🚨100% 이상 합법 그룹 (임의표시 성분)]: 타우린, 아미노산류, 콜라겐 등 법적 80% 허용오차 명단에 없는 '임의표시 영양/기능성 성분'은 실측값이 무조건 시안 표시량의 100% 이상이어야 합법입니다. 100% 미만일 경우 표시위반(과대광고)이므로 🚨부적합 처리하십시오.
   - 허용오차 비율(%) 공식은 반드시 (실측값 ÷ 표시량) × 100 을 사용.

🔥 **Rule 12. [원재료명 3단 교차 검증 및 기재 순서 절대 원칙 (배합비 ➔ 원료서류 ➔ 시안)]**
   - 1. [순서 대조]: 원재료는 반드시 배합비(%) 투입량이 높은 순서대로(내림차순) 시안에 기재되어야 합니다.
   - 2. [명칭 1:1 매칭]: 배합비명칭이 아닌 **[원료 한글표시사항 서류]**에 기재된 '정확한 법적 명칭'과 '하위성분'을 추출한 뒤, 이 내용이 최종 시안에 토씨 하나 틀리지 않고(Rule 35 간략명 예외 제외) 1:1로 잘 들어갔는지 완벽하게 교차 검증하십시오.

✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔**
   - 알레르기 유발물질이 별도 란에 바탕색과 구분되어 명확히 적혀 있는지 확인.

✅ **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료, 보존료 등은 원재료명 란에 명칭과 용도명 괄호 병기 필수. (단, 묶음 표기는 합법)

✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
   - 식약처 세부 기준 엄격 대조 통과 시에만 합격 처리.

✅ **Rule 16. [원산지 100%]** - 물 산정 제외, 농산물 국산 100% 합법.
✅ **Rule 17. ['無첨가' 절대 룰]** - 금지된 첨가물을 안 넣었다고 강조할 때만 지적.
✅ **Rule 18. [영유아 타겟 명칭]** - '베베', '키즈' 일반식품 마케팅 합법.
✅ **Rule 19. ['무당/무가당/저당' 엄격 적용]** - 저당(5g 미만), 무당(0.5g 미만), 무가당(무첨가).
✅ **Rule 20. [용기·포장재질 표기법]** - 복합재질의 경우 내면 재질만 표기(예: 폴리에틸렌(내면)) 합법.

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
   - 반드시 4가지 환산 기준을 모두 계산하여 단 하나라도 충족하면 적합 판정.

✅ **Rule 22. [다국어 폰트 크기]** - 영문이 한글보다 크면 부적합.

🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]**
   - 총 내용량 표기란에 '0.5g'이라고 적혀있다면 무조건 부적합 처리 ('0.5g 미만'이어야 함).

🔥 **Rule 24. [감미료 14pt 의무 표기]**
   - 시안 주표시면에 "무당, ZERO" 강조표시가 있을 때만 14pt 주의문구 지적.

🔥 **Rule 25. [다중 포장 듀얼 컬럼]** - 1개당 / 총 내용량 혼동 금지.
🔥 **Rule 26. [고체 vs 액체 단위 엄격 구분]** - g과 mL 기준 혼용 금지.
🔥 **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]** - 무/저 강조표시 검토 시 100g/100mL 기준만 적용.

🔥 **Rule 28. [원산지 과잉 지적(오지랖) 절대 금지]**
   - 상위 3순위에 들지 않는 미량 원료(예: 0.05% 사과농축액)는 제품명과 연관되어 함량을 강조 표기했더라도 원산지 표시 의무가 없습니다. "원산지를 병기하는 것이 바람직하다"는 따위의 훈수나 과잉 지적을 엄격히 금지합니다.

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기]**
   - 국내 1차 가공 원료는 최종제품명(기원원료명:원산지) 형태 병기 필수.

🔥 **Rule 30. [실제 투입 알레르기 물질 100% 필수 검증 (함유/포함 란)]**
   - 서류에 있는 '실제 투입된' 알레르기 물질이 시안의 메인 알레르기 표시란(~포함)에 단 하나라도 누락 없이 100% 기재되어 있는지 우선 확인하십시오.

🔥 **Rule 31. [다중/무제한 성적서 처리 및 균형영양식 대응]** - 무제한 파일 병합 1:1 대조.
🔥 **Rule 32. [균형 열량 구성비 역산]** - 설계치이므로 오차 지적 금지. (식이섬유 2kcal 별도 계산)
🔥 **Rule 33. [데이터 출처 완벽 분리 및 100% 필사본 강제 룰]** - 시안 원재료명 텍스트 100% 타이핑 필수.

🔥 **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 배합비 2% 미만인 원재료들은 함량 내림차순 원칙을 무시하고 뒤쪽에 자유롭게 순서를 배열할 수 있습니다. 2% 미만 원료들끼리 순서가 바뀌었다고 🚨순서 오류로 지적하는 행위를 절대 금지합니다.

🔥 **Rule 35. [서류 명칭 일치 및 공전상 간략명 범용 허용 룰]**
   - 식약처 「식품등의 표시기준」 [표 5] 및 [표 6]에 명시된 '모든 공식 간략명'(예: 카복시메틸셀룰로스나트륨 ➔ CMC, DL-사과산 ➔ 사과산 등)은 무조건 ✅적합 처리하십시오. 공전상 간략명을 부적합으로 지적하는 환각을 금지합니다.

🔥 **Rule 36. [오탈자(Typo) 정밀 스캔 및 환자식 1:1 매칭 룰]**

🔥 **Rule 37. [법적 서류 절대 우선의 원칙 (원료 추출 강제 룰)]**
   - 원료의 정확한 '명칭'과 '하위 성분'을 추출할 때 가배합비 엑셀 데이터에만 의존하지 말고, 반드시 **[원료 한글표시사항 라벨/품목제조보고서]**를 1순위로 교차 확인하여 시안과 1:1 대조하십시오.

🔥 **Rule 38. [교차오염 경고 문구 상호 배타성 원칙 (중복 지적 절대 금지)]**
   - 이미 '함유/포함'란에 기재된 알레르기 성분이 교차오염 문구(~같은 시설에서 제조)에 빠져 있다고 지적하는 멍청한 행위를 절대 금지합니다. 원료 서류의 시설 문구를 시안으로 끌고 오지 마십시오.

🔥 **Rule 39. [동명 원료(같은 이름) 교차 혼선 금지 및 종속성 원칙]**
   - 하위 성분을 검증할 때는 반드시 해당 성분이 소속된 '부모 원료(복합원재료)의 전용 서류' 안에서만 팩트를 확인하십시오.

🔥 **Rule 40. [열량 5kcal 단위 반올림 우선의 원칙]**
   - 가장 가까운 5kcal 단위 반올림 적용 시 시안과 일치하면 무조건 ✅적합 판정.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 (실측값 계산 절대 금지)]**
   - [계산 공식]: 오직 **(시안 표시량 ÷ 식약처 1일 영양성분 기준치) × 100 (소수점 첫째 자리 반올림)** 으로만 계산하십시오.
   - [🚨경고]: 성적서의 '실측값'을 사용하여 % 기준치를 역산하는 멍청한 행위를 **절대 금지**합니다. 실측값은 오직 Rule 11(허용오차 80% 통과 여부)을 판정할 때만 한 번 쓰고 버리십시오. 실측값으로 %를 계산하여 부적합을 남발하면 시스템 오류로 간주합니다.

🔥 **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**

🔥 **Rule 43. [시각적 오독(OCR) 철통 방어 및 픽셀 단위 판독]**
   - 영양성분표에서 글자를 잘못 읽는(오독) 행위를 엄격히 금지합니다. 좌우 칸의 글자를 섞어 읽거나 소수점을 빼먹지 마십시오.

🔥 **Rule 44. [혼합제제 넘버링 및 하위성분 전개 합법성 (AI 오지랖 금지)]**
   - '혼합제제1', '혼합제제2' 등으로 넘버링하여 표기하는 것은 업계 표준이며 100% 합법입니다.
   - 혼합제제 명칭 뒤에 괄호를 치고 하위 성분을 모두 기재하는 것은 법적 의무입니다. 이를 지적하는 환각을 절대 금지합니다.

🔥 **Rule 45. [유령 성분 검토 금지 및 총내용량 환산 의무화]**
   - 1. 시안에 아예 적혀 있지도 않은 성분을 성적서에서 끌어와서 대조하는 '유령 성분 검토'를 절대 금지합니다.
   - 2. 성적서가 '100mL 당' 수치이고 제품의 총 내용량이 다르다면, 반드시 성적서 수치에 배수를 곱하여 '총내용량 환산 실측값'을 먼저 구한 뒤에 허용오차를 계산하십시오.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.16 - 원재료 3단 교차검증 완결판)")
    st.markdown("---")

    product_type = st.radio("📌 1. 식품유형 선택", ("특수의료용도식품 / 환자식", "일반식품"))
    st.markdown("---")

    # [UI] 시안 업로드 구역 (4분할)
    st.subheader("🎨 2. 시안 이미지 (준비된 면만 업로드)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    st.markdown("---")
    
    # [UI] 증빙 서류 구역 (완벽 분리)
    st.subheader("📄 3. 증빙 및 법적 서류 (분리 업로드)")
    d1, d2, d3 = st.columns(3)
    with d1: report_docs = st.file_uploader("시험성적서 (실측치 확인용)", type=["pdf", "jpg", "png"], accept_multiple_files=True, key="report")
    with d2: recipe_docs = st.file_uploader("배합비 / 레시피 (설계치 확인용)", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True, key="recipe")
    with d3: legal_docs = st.file_uploader("원료라벨 / 품목보고서 (법적근거)", type=["pdf", "jpg", "png"], accept_multiple_files=True, key="legal")

    if st.button("🔍 구역별 데이터 매칭 QC 시작", type="primary"):
        user_content = []
        def add_item(file_obj, label):
            if file_obj:
                if isinstance(file_obj, list):
                    for f in file_obj: process_single_file(f, label)
                else: process_single_file(file_obj, label)

        def process_single_file(f, label):
            user_content.append(f"### [분류: {label}] ###")
            if f.type.startswith("image"): user_content.append(Image.open(f))
            elif f.name.lower().endswith(".csv"): user_content.append(f.getvalue().decode('utf-8', errors='ignore'))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                uploaded = genai.upload_file(temp)
                while uploaded.state.name == "PROCESSING": time.sleep(1)
                user_content.append(uploaded)

        with st.spinner("배합비 ➔ 법적서류 ➔ 시안 3단 정밀 교차 검증 중..."):
            add_item(img_main, "시안_주표시면"); add_item(img_info, "시안_정보표시면"); add_item(img_nutri, "시안_영양성분표"); add_item(img_extra, "시안_기타면")
            add_item(report_docs, "근거_시험성적서"); add_item(recipe_docs, "근거_배합비레시피"); add_item(legal_docs, "근거_원료법적서류")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            final_prompt = f"""
            [현재 검토 제품유형]: {product_type}
            [🚨형식 고정 절대 명령] 창의성을 발휘하지 말고 아래 템플릿의 목차 1~6번을 100% 동일하게 유지하십시오.
            ## 1️⃣ [주표시면 및 기타면 검토]
            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (배합비 ➔ 서류 ➔ 시안 3단 검증 및 5%, 2% 룰 적용 결과)]
            ## 4️⃣ [영양표시 검토 및 % 기준치 검증]
            | 영양성분 | 시안 표시량 | 시안 기재 % | 총내용량 환산 실측값 | 허용오차 판정 | % 계산 검증 (일치여부) |
            ## 5️⃣ [기타 법적 의무사항]
            ## 6️⃣ [종합의견 및 즉시 수정 지시사항]
            """
            try:
                response = model.generate_content(user_content + [final_prompt], generation_config=genai.types.GenerationConfig(temperature=0.0))
                st.markdown(response.text)
            except Exception as e: st.error(f"🚨 오류: {e}")
            finally:
                for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
