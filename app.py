import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os

from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# [보안] 비밀번호 설정
# ==========================================
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
    else:
        return True

# ==========================================
# 1. API 키 설정
# ==========================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 2. 통합 전문가 프롬프트 (V6.4 - 궁극의 완전판)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오.

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 6.4]

## ⚠️ 검토 대원칙: 43대 특수 지침 (절대 엄수 - 단 하나도 요약하거나 누락하지 말 것)

✅ **Rule 1. 원산지 3순위 산정 제외 및 생략 합법성 (첨가물 절대 면제)**
   - 물, 주정, 당류, **식품첨가물(예: 젖산칼슘, 무수구연산 등)**은 배합비가 아무리 높아도 3순위 카운트에서 100% 제외합니다.
   - 상위 3순위에 들지 않는 미량 원료 및 모든 식품첨가물은 원산지 표시 의무가 없습니다. 서류에 국가명이 있어도 시안에 생략한 것은 완벽한 합법(일치)이므로 원산지 누락으로 절대 🚨지적하지 마십시오.

✅ **Rule 2. 향료 및 첨가물 유연화**
   - 향료 및 일반 첨가물 표기 [적합].

✅ **Rule 3. 영양정보 vs 강조표시 (이원화)**
   - 영양성분표 수치와 주표시면 강조 수치가 충돌하지 않는지 대조.

✅ **Rule 4. 영양성분 실측값 허용**
   - 오차 범위를 고려한 실측값 표기 인정.

✅ **Rule 5. 5% 룰 & 알레르기**
   - 5% 미만 원료라도 알레르기 유발물질은 무조건 표기.

✅ **Rule 6. 당류/시럽 필터링**
   - 당류 원료 사용 시 영양성분표 당류 수치와 교차 검증.

🔥 **Rule 7. 감미료 주의문구 (엄격한 조건부 발동)**
   - 당알콜류(에리스리톨 등) 사용 시 "과량 섭취 시 설사를 일으킬 수 있습니다", 아스파탐 사용 시 "페닐알라닌 함유" 주의문구 스캔.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 수입국 다변화에 따른 원산지 표기 유연성 인정.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 제품명과 식품유형(예: 유산균음료)이 혼동되지 않도록 명확히 표기.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 강제 분리)**
   - 강조표시 심사 시 제형에 따른 기준 분리 적용.

🔥 **Rule 11. 영양정보 팩트 체크 및 허용오차 절대 법칙**
   - **[비타민/무기질 등]**: 실측값이 표시량의 **80% 이상**이면 무조건 합법. (120% 초과해도 상향조정 지적 금지)
   - **[당류/지방/나트륨 등]**: 실측값이 표시량의 **120% 미만**이면 무조건 합법. (불검출이어도 합법이므로 0g으로 수정 지적 금지)

✅ **Rule 12~13. (배합비 대조 및 알레르기 문구 텍스트+디자인 스캔)**

🔥 **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료, 보존료 등은 원재료명 란에 명칭과 용도명 괄호 병기 필수. (단, `감미료(A, B)` 형태의 묶음 표기는 100% 합법이므로 지적 금지)

✅ **Rule 15~19. (강조표시, 원산지100%, 무첨가 룰, 영유아 명칭, 저당 조건 적용)**

✅ **Rule 20. [용기·포장재질 표기법]**
   - "재질명(포장부위)" 형태로 코칭. 알미늄은 비표준어이므로 '알루미늄'으로 교정.
   - **종이팩 등 복합재질의 경우 식품과 직접 닿는 내면 재질만 표기(예: `폴리에틸렌(내면)`)하는 것은 100% 합법이므로 전체 재질을 다 적으라고 지적하지 마십시오.**

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
   - 반드시 4가지 환산 기준을 모두 계산하여 단 하나라도 충족하면 ✅적합 판정.

✅ **Rule 22~28. (다국어 폰트, 트랜스지방 0.5g 금지, 감미료 14pt, 듀얼 컬럼, 100kcal 금지 등)**

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기]**
   - 수입산 원료를 국내에서 1차 가공하여 납품받은 모든 '국내 제조 가공품'은 시안에 반드시 **`최종제품명(기원원료명:원산지)`** 형태가 병기되어야 합니다.

🔥 **Rule 30~34. (알레르기 10종 스캔, 100% 필사, 2% 미만 자유 배열 등)**

🔥 **Rule 35. [서류 명칭 일치 원칙]**
   - 의미가 통하더라도 서류상 명칭과 시안 명칭 텍스트가 다르면 무조건 🚨불일치. (예: 퓨레 vs 퓌레, 덱스트린 vs 말토덱스트린 구분)

🔥 **Rule 36~39. (오탈자 스캔, 서류 우선 원칙, 교차오염 전이 금지, 동명 원료 혼선 차단)**

🔥 **Rule 40. [열량 5kcal 단위 반올림 우선의 원칙]**
   - 열량 실측값이 120%를 초과해도, '가장 가까운 5kcal 단위' 반올림 적용 시 시안 표시량과 일치하면 무조건 ✅적합 판정하십시오.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - **[계산 공식]**: **(시안 표시량 ÷ 식약처 1일 영양성분 기준치) × 100** (소수점 첫째 자리 반올림)
   - **[🚨주의]**: 절대 서류의 실측값으로 계산하지 마십시오! 오직 시안에 적힌 **'표시량'** 기준으로만 역산하십시오.

🔥 **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**
   - 시안(완제품)의 식품유형, 소비기한, 보관방법, 품번 검사 시 그 안에 들어가는 **'원료용 서류'를 기준 삼아 대조하는 환각을 엄격히 금지**합니다.

🔥 **Rule 43. [시각적 오독(OCR) 방지]**
   - `1~35℃`를 `135℃`로 읽는 등 기호(~ 등) 누락 오독을 금지합니다.
---
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.4 - 궁극의 완전판)")
    st.markdown("---")

    st.subheader("📌 1. 검토 대상 제품의 식품유형을 선택하세요")
    product_type = st.radio(
        "제품 유형에 따라 검증 엄격도가 달라집니다.",
        ("특수의료용도식품 / 환자식 (1:1 정밀 매칭)", "일반식품 (유연한 표기 허용)")
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 2. 시안 이미지")
        main_img = st.file_uploader("앞면/뒷면/영양정보 등 업로드", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    with col2:
        st.subheader("📄 3. 증빙 문서")
        docs = st.file_uploader("성적서/품목보고서/라벨 등 업로드", type=["pdf", "jpg", "png", "jpeg", "csv"], accept_multiple_files=True)

    if st.button("🔍 서류 추출 및 QC 정밀 진단 시작", type="primary"):
        user_content = []
        
        def process_files(files, label):
            for f in files:
                if f.type.startswith("image"):
                    user_content.append(f"<{label} 이미지>")
                    user_content.append(Image.open(f))
                elif f.name.lower().endswith(".csv"):
                    user_content.append(f.getvalue().decode('utf-8', errors='ignore'))
                else:
                    temp = f"temp_{f.name}"
                    with open(temp, "wb") as file: file.write(f.getbuffer())
                    uploaded = genai.upload_file(temp)
                    while uploaded.state.name == "PROCESSING": time.sleep(1)
                    user_content.append(uploaded)

        with st.spinner("전문가 룰북을 기반으로 교차 검증 중..."):
            if main_img: process_files(main_img, "시안")
            if docs: process_files(docs, "증빙서류")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = f"""
            [현재 검토 대상 제품 유형]: {product_type}
            [결과 리포트 출력 템플릿]
            ## 1️⃣ [주표시면 및 기타면 검토]
            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
            ## 4️⃣ [영양표시 검토 및 % 기준치 검증]
            - 양식: | 영양성분 | 시안 표시량 | 시안 기재 % | 총내용량 환산 실측값 | 허용오차 판정 | % 계산 검증 |
            ## 5️⃣ [기타 법적 의무사항]
            ## 6️⃣ [종합의견 및 즉시 수정 지시사항]
            """

            try:
                response = model.generate_content(
                    user_content + [final_prompt],
                    generation_config=genai.types.GenerationConfig(temperature=0.0)
                )
                st.markdown(response.text)
            except Exception as e:
                st.error(f"🚨 오류 발생: {e}")
            finally:
                for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password():
        main()
