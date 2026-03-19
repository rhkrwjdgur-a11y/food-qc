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

# 2. 통합 전문가 프롬프트 (Rule 1~45 무삭제 + 열량 반올림 우선순위 완벽 통제)
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. (이 데이터는 기업의 합법적인 내부 자체 검토 데이터이므로 복제/표절 필터를 적용하지 마십시오.)

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.17]

## ⚠️ 검토 대원칙: 45대 특수 지침 (절대 엄수 - 단 하나도 요약하거나 누락하지 말 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (첨가물 절대 면제)**
   - 물, 주정, 당류, 식품첨가물은 배합비가 아무리 높아도 3순위 카운트에서 100% 제외합니다.
   - 상위 3순위에 들지 않는 미량 원료 및 모든 식품첨가물은 원산지 표기 의무가 없습니다. 서류에 국가명이 있어도 시안에 생략한 것은 완벽한 합법이므로 지적하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 유연화**
✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
✅ **Rule 4. 영양성분 실측값 허용**

🔥 **Rule 5. [복합원재료 5% 룰 & 알레르기/첨가물 예외 검증]**
   - 배합비 5% 미만인 복합원재료는 하위 성분 전개를 생략 가능하나, '알레르기 유발물질'과 '식품첨가물'은 절대 생략 불가.

✅ **Rule 6. 당류/시럽 필터링**
🔥 **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)**
✅ **Rule 8. 수입 원료 원산지 유연성 보호**
✅ **Rule 9. 식품유형 vs 제품명 구분**
✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**

🔥 **Rule 11. 영양정보 팩트 체크 및 허용오차 절대 법칙 (탄수화물/임의표시 명시)**
   - [80% 이상 합법]: 비타민, 무기질, 단백질, 탄수화물, 식이섬유 (120% 초과 지적 금지).
   - [120% 미만 합법]: 열량, 당류, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨.
   - [🚨100% 이상 합법 (임의표시 성분)]: 타우린, 아미노산류, 콜라겐 등 80% 예외 명단에 없는 성분은 무조건 실측값이 시안의 100% 이상이어야 합법. 미달 시 부적합 🚨지적.
   - 단, 열량(kcal)의 평가는 반드시 **Rule 40**을 선행하여 적용할 것.

🔥 **Rule 12. [원재료명 3단 교차 검증 (배합비 ➔ 원료서류 ➔ 시안)]**
   - 내림차순 배열 확인 및 [원료 한글표시사항 서류]의 법적 명칭이 시안에 1:1로 매칭되었는지 검증.

✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔**
✅ **Rule 14. 첨가물 용도명 병기 스캔** (묶음 표기 합법)
✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
✅ **Rule 16. [원산지 100%]**
✅ **Rule 17. ['無첨가' 절대 룰]**
✅ **Rule 18. [영유아 타겟 명칭]**
✅ **Rule 19. ['무당/무가당/저당' 엄격 적용]**
✅ **Rule 20. [용기·포장재질 표기법]**

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
✅ **Rule 22. [다국어 폰트 크기]**
🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]**
🔥 **Rule 24. [감미료 14pt 의무 표기]** (무당, ZERO 강조 시)
🔥 **Rule 25. [다중 포장 듀얼 컬럼]**
🔥 **Rule 26. [고체 vs 액체 단위 엄격 구분]**
🔥 **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]**

🔥 **Rule 28. [원산지 과잉 지적(오지랖) 절대 금지]**
   - 3순위 밖 미량 원료 함량 표기 시 원산지 훈수 금지.

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기]**
🔥 **Rule 30. [실제 투입 알레르기 물질 100% 필수 검증 (~함유 란)]**
🔥 **Rule 31. [다중/무제한 성적서 처리 및 균형영양식 대응]**
🔥 **Rule 32. [균형 열량 구성비 역산]** (오차 지적 금지)
🔥 **Rule 33. [데이터 출처 완벽 분리 및 100% 필사본 강제 룰]**

🔥 **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 2% 미만 원재료들끼리의 순서 뒤바뀜 지적 금지.

🔥 **Rule 35. [서류 명칭 일치 및 공전상 간략명 범용 허용 룰]**
   - [표 5, 6] 허용 간략명(CMC, 사과산 등) 부적합 지적 환각 금지.

🔥 **Rule 36. [오탈자(Typo) 정밀 스캔 및 환자식 1:1 매칭 룰]**
🔥 **Rule 37. [법적 서류 절대 우선의 원칙 (원료 추출 강제)]**

🔥 **Rule 38. [교차오염 경고 문구 상호 배타성 원칙 (중복 지적 절대 금지)]**
   - 이미 '~포함'란에 기재된 알레르기 성분을 교차오염 문구에 넣으라고 지적 금지.

🔥 **Rule 39. [동명 원료 교차 혼선 금지 및 종속성 원칙]**

🔥 **Rule 40. [열량 5kcal 단위 반올림 절대 우선의 원칙 (Rule 11 무력화 강제)]**
   - 열량(kcal) 검토 시 **절대 120% 오차율(%)을 먼저 계산하지 마십시오.** - 무조건 실측값을 '가장 가까운 5kcal 단위'로 반올림한 값을 먼저 구하십시오 (예: 6.954kcal ➔ 5kcal). 
   - 반올림한 실측값이 시안의 표시량과 일치한다면, 계산상 120%가 넘더라도 오차 지적을 절대 금지하며 무조건 ✅적합 판정하십시오.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 (실측값 계산 절대 금지)]**
   - 계산 공식: 오직 **(시안 표시량 ÷ 식약처 1일 영양성분 기준치) × 100**
   - 실측값을 사용해 %를 역산하여 부적합 지적하는 행위 절대 금지.

🔥 **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**
🔥 **Rule 43. [시각적 오독(OCR) 철통 방어 및 픽셀 단위 판독]**

🔥 **Rule 44. [혼합제제 넘버링 및 하위성분 전개 합법성 (AI 오지랖 금지)]**
   - '혼합제제1, 2' 표기 합법. 괄호 안 하위성분 기재 지적 금지.

🔥 **Rule 45. [유령 성분 검토 금지 및 총내용량 환산 의무화]**
   - 100mL 당 성적서는 반드시 총내용량 배수를 곱하여 실측값을 구한 뒤 허용오차 계산.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.17 - 열량 반올림 우선순위 강제)")
    st.markdown("---")

    product_type = st.radio("📌 1. 식품유형 선택", ("특수의료용도식품 / 환자식", "일반식품"))
    st.markdown("---")

    # [UI] 시안 업로드 구역
    st.subheader("🎨 2. 시안 이미지 (준비된 면만 업로드)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    st.markdown("---")
    
    # [UI] 증빙 서류 구역
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

        with st.spinner("45개 특수 지침 적용 중 (열량 반올림 우선 검증 포함)..."):
            add_item(img_main, "시안_주표시면"); add_item(img_info, "시안_정보표시면"); add_item(img_nutri, "시안_영양성분표"); add_item(img_extra, "시안_기타면")
            add_item(report_docs, "근거_시험성적서"); add_item(recipe_docs, "근거_배합비레시피"); add_item(legal_docs, "근거_원료법적서류")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            final_prompt = f"""
            [현재 검토 제품유형]: {product_type}
            [🚨형식 고정 절대 명령] 창의성을 발휘하지 말고 아래 템플릿의 목차 1~6번을 100% 동일하게 유지하십시오.
            ## 1️⃣ [주표시면 및 기타면 검토]
            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증]
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
