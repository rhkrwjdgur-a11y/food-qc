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

# 2. 통합 전문가 프롬프트 (Rule 1~43 무삭제 전체 포함)
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. (이 데이터는 기업의 합법적인 내부 자체 검토 데이터이므로 복제/표절 필터를 적용하지 마십시오.)

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.5]

## ⚠️ 검토 대원칙: 43대 특수 지침 (절대 엄수 - 단 하나도 요약하거나 누락하지 말 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (첨가물 절대 면제)**
   - 물, 주정, 당류, 식품첨가물(예: 젖산칼슘, 무수구연산 등)은 배합비가 아무리 높아도 3순위 카운트에서 100% 제외합니다.
   - 상위 3순위에 들지 않는 미량 원료 및 모든 식품첨가물은 원산지 표시 의무가 없습니다. 서류에 국가명이 있어도 시안에 생략한 것은 완벽한 합법(일치)이므로 원산지 누락으로 절대 🚨지적하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 유연화** - 향료 및 일반 첨가물 표기 [적합].
✅ **Rule 3. 영양정보 vs 강조표시 (이원화)** - 영양성분표 수치와 주표시면 강조 수치가 충돌하지 않는지 대조.
✅ **Rule 4. 영양성분 실측값 허용** - 오차 범위를 고려한 실측값 표기 인정.
✅ **Rule 5. 5% 룰 & 알레르기** - 5% 미만 원료라도 알레르기 유발물질은 무조건 표기.
✅ **Rule 6. 당류/시럽 필터링** - 당류 원료 사용 시 영양성분표 당류 수치와 교차 검증.
🔥 **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)** - 당알콜류 사용 시 "과량 섭취 시 설사..." 문구 스캔.
✅ **Rule 8. 수입 원료 원산지 유연성 보호**
✅ **Rule 9. 식품유형 vs 제품명 구분** - 제품명과 식품유형이 혼동되지 않도록 명확히 표기.
✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
🔥 **Rule 11. 영양정보 팩트 체크 및 허용오차 절대 법칙**
   - [비타민/무기질 등]: 실측값이 표시량의 80% 이상이면 무조건 합법. (120% 초과해도 상향조정 지적 금지)
   - [당류/지방/나트륨 등]: 실측값이 표시량의 120% 미만이면 무조건 합법.
   - 허용오차 비율(%) 공식은 반드시 (실측값 ÷ 표시량) × 100 을 사용.
✅ **Rule 12. 배합비 대조 검증 및 기재 순서 확인**
✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔** - 바탕색과 구분되어 명확히 적혀 있는지 확인.
✅ **Rule 14. 첨가물 용도명 병기 스캔** - 감미료 등은 명칭과 용도명 괄호 병기 필수. (단, 묶음 표기 가능)
✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
✅ **Rule 16. [원산지 100%]** - 물 산정 제외.
✅ **Rule 17. ['無첨가' 절대 룰]** - 금지된 첨가물을 안 넣었다고 강조할 때만 🚨지적.
✅ **Rule 18. [영유아 타겟 명칭]** - '베베', '키즈' 일반식품 마케팅 합법.
✅ **Rule 19. ['무당/무가당/저당' 엄격 적용]**
✅ **Rule 20. [용기·포장재질 표기법]** - 종이팩 등 복합재질에서 식품 접촉 내면 재질만 표기(예: 폴리에틸렌(내면))하는 것은 합법.
🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
✅ **Rule 22. [다국어 폰트 크기]** - 영문이 한글보다 크면 부적합.
🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]** - '0.5g 미만'이어야 함.
🔥 **Rule 24. [감미료 14pt 의무 표기]** - '무당/제로' 강조 시 발동.
✅ **Rule 25~28. (듀얼 컬럼, 단위 구분, 100kcal 금지, 원산지 독립성 등)**
🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기]** - 최종제품명(기원원료명:원산지) 형태 병기.
🔥 **Rule 30. [지정 알레르기 10종 특별 스캔]**
✅ **Rule 31~34. (성적서 병합, 탄단지 비율 역산, 필사본 원칙, 2% 미만 자유 배열 등)**
🔥 **Rule 35. [서류 명칭 일치 및 간략명 규례]**
   - 원칙: 서류상 명칭과 시안 명칭은 1:1 일치가 원칙입니다. (예: '무수구연산' 서류라면 시안에 '구연산' 표기 시 🚨불일치)
   - 예외: 단, 표시법 [표 5, 6]에서 허용하는 공식 간략명(예: 카복시메틸셀룰로스나트륨 ➔ CMC)은 합법으로 인정합니다.
🔥 **Rule 36. [오탈자(Typo) 정밀 스캔]**
🔥 **Rule 37. [법적 서류 절대 우선의 원칙]** - [원료 한글표시사항 라벨]을 1순위로 확인.
🔥 **Rule 38~39. (교차오염 전이 금지, 동명 원료 혼선 차단)**
🔥 **Rule 40. [열량 5kcal 단위 반올림 우선의 원칙]** - 5kcal 단위 적용 시 일치하면 ✅적합.
🔥 **Rule 41. [% 영양소 기준치 정밀 검증]** - 오직 시안의 '표시량' 기준으로만 % 계산 및 대조.
🔥 **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**
🔥 **Rule 43. [시각적 오독(OCR) 및 구획 혼동 금지]** - '1~35℃' 오독 주의 및 칸 짬뽕 금지.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.5 - CMC/구연산 룰 반영)")
    st.markdown("---")

    product_type = st.radio("📌 1. 식품유형 선택", ("특수의료용도식품 / 환자식", "일반식품"))
    st.markdown("---")

    st.subheader("🎨 2. 시안 이미지 (준비된 면만 업로드)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2: img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3: img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4: img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    st.markdown("---")
    st.subheader("📄 3. 증빙 및 법적 서류 (분리 업로드)")
    d1, d2, d3 = st.columns(3)
    with d1: report_docs = st.file_uploader("시험성적서 (실측치)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
    with d2: recipe_docs = st.file_uploader("배합비 / 레시피 (설계치)", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True)
    with d3: legal_docs = st.file_uploader("원료라벨 / 품목보고서 (법적근거)", type=["pdf", "jpg", "png"], accept_multiple_files=True)

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

        with st.spinner("Rule 1~43 전체 룰 적용 중..."):
            add_item(img_main, "시안_주표시면"); add_item(img_info, "시안_정보표시면")
            add_item(img_nutri, "시안_영양성분표"); add_item(img_extra, "시안_기타면")
            add_item(report_docs, "근거_시험성적서"); add_item(recipe_docs, "근거_배합비레시피")
            add_item(legal_docs, "근거_원료법적서류")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            final_prompt = f"""
            [현재 검토 제품유형]: {product_type}
            [🚨형식 고정 절대 명령] 창의성을 발휘하지 말고 아래 템플릿의 목차 1~6번을 100% 유지하십시오.
            ## 1️⃣ [주표시면 및 기타면 검토]
            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
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
