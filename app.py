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
   - [비타민/무기질 등]: 실측값이 표시량의 80% 이상이면 무조건 합법. (120% 초과해도 상향조정 지적 금지)
   - [당류/지방/나트륨 등]: 실측값이 표시량의 120% 미만이면 무조건 합법. (불검출이어도 합법이므로 0g으로 수정 지적 금지)
   - 허용오차 비율(%) 공식은 반드시 (실측값 ÷ 표시량) × 100 을 사용.

✅ **Rule 12. 배합비 대조 검증 및 생략 코칭**
   - 원재료 배합비율과 기재 순서 대조 확인.

✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔**
   - 알레르기 유발물질이 별도 란에 바탕색과 구분되어 명확히 적혀 있는지 확인.

✅ **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료, 보존료 등은 원재료명 란에 명칭과 용도명 괄호 병기 필수. (단, 감미료(A, B) 형태의 묶음 표기는 100% 합법이므로 지적 금지)

✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
   - 식약처 세부 기준 엄격 대조 통과 시에만 합격 처리.

✅ **Rule 16. [원산지 100%]** - 물은 산정 제외, 농산물 국산이면 100% 합법.

✅ **Rule 17. ['無첨가' 절대 룰]** - 금지된 첨가물을 안 넣었다고 강조할 때만 🚨지적.

✅ **Rule 18. [영유아 타겟 명칭]** - '베베', '키즈' 일반식품 마케팅 합법.

✅ **Rule 19. ['무당/무가당/저당' 엄격 적용]** - 저당(5g 미만), 무당(0.5g 미만), 무가당(무첨가).

✅ **Rule 20. [용기·포장재질 표기법]** - "재질명(포장부위)" 형태로 코칭. 알미늄은 비표준어이므로 '알루미늄'으로 교정.
   - 종이팩 등 복합재질의 경우 식품과 직접 닿는 내면 재질만 표기(예: 폴리에틸렌(내면))하는 것은 100% 합법이므로 전체 재질을 다 적으라고 지적하지 마십시오.

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증]**
   - 반드시 4가지 환산 기준을 모두 계산하여 단 하나라도 충족하면 ✅적합 판정.

✅ **Rule 22. [다국어 폰트 크기]** - 영문이 한글보다 크면 부적합 코칭.

🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]**
   - 총 내용량 표기란에 '0.5g'이라고 적혀있다면 무조건 🚨부적합 처리 ('0.5g 미만'이어야 함).

🔥 **Rule 24. [감미료 14pt 의무 표기]**
   - [🚨발동 조건]: 시안 주표시면에 "무당, 당류 무첨가, 무가당 (ZERO, 제로 포함)" 강조표시가 있을 때만 14pt 주의문구 지적.

🔥 **Rule 25. [다중 포장 듀얼 컬럼]** - 1개당 / 총 내용량 혼동 금지.

🔥 **Rule 26. [고체 vs 액체 단위 엄격 구분]** - g과 mL 기준 혼용 금지.

🔥 **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]** - 무/저 강조표시 검토 시 100g/100mL 기준만 적용.

🔥 **Rule 28. [복합원재료 원산지 독립성 확인]** - 상위 3순위는 알레르기가 있어도 원산지 병기 필수.

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기 (모든 가공원료 범용 원리)]**
   - 수입산 원료를 국내에서 1차 가공하여 납품받은 모든 '국내 제조 가공품'은 시안에 반드시 최종제품명(기원원료명:원산지) 형태가 병기되어야 합니다.

🔥 **Rule 30. [지정 알레르기 10종 특별 스캔 (실제 투입 원료 한정)]**
   - 서류에 있는 '실제 투입된' 알레르기 물질이 시안에 누락 시 즉시 부적합.

🔥 **Rule 31. [다중/무제한 성적서 처리 및 균형영양식 대응]** - 무제한 파일 병합 1:1 대조.

🔥 **Rule 32. [균형 열량 구성비 역산 (환각 지적 방지 핵심)]**
   - 환자식/특수용도식품의 탄:단:지 비율은 설계치이므로 오차 지적 금지. (식이섬유 2kcal 별도 계산 반영)

🔥 **Rule 33. [데이터 출처 완벽 분리 및 100% 필사본 강제 룰]**
   - '제품 내 원재료명 (시안 기준)' 열은 시안에 적힌 텍스트를 토씨 하나 빼먹지 말고 100% 타이핑하십시오. 임의 요약 절대 금지.

🔥 **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 배합비 2% 미만 원재료는 순서 무관.

🔥 **Rule 35. [서류 명칭 일치 원칙 및 생략/추가 예외 (모든 원료 범용 원리)]**
   - 원칙: 의미가 통하더라도 서류상 명칭과 시안의 명칭 텍스트가 다르면 무조건 🚨불일치. (예: 퓨레 vs 퓌레, 덱스트린 vs 말토덱스트린 구분)
   - 예외 1: 미량 원료의 원산지 생략은 합법 (✅일치).
   - 예외 2: 영양성분 등 스펙(예: 칼슘 함량 32% 이상)의 자발적 추가 기재는 합법 (✅일치).

🔥 **Rule 36. [오탈자(Typo) 정밀 스캔 및 환자식 1:1 매칭 룰]**
   - 낱개 성분을 1:1 매칭하고, 오타 발견 시 즉시 🚨지적.

🔥 **Rule 37. [법적 서류 절대 우선의 원칙 (가배합비의 거짓말 차단)]**
   - 원료의 '서류 기준 명칭'을 추출할 때 가배합비를 무시하고 반드시 [원료 한글표시사항 라벨/품목제조보고서]를 1순위로 확인하십시오.

🔥 **Rule 38. [원료의 교차오염 주의문구 전이(Carry-over) 절대 금지]**
   - 원료 라벨 구석에 적힌 "본 제품은 ...과 같은 제조시설에서 제조하고 있습니다" 문구에 있는 돼지고기, 쇠고기 등은 우리 최종 시안 알레르기로 절대 끌고 오지 마십시오. 무조건 무시.

🔥 **Rule 39. [동명 원료(같은 이름) 교차 혼선 금지 및 종속성 원칙]**
   - 하위 성분을 검증할 때는 반드시 해당 성분이 소속된 '부모 원료(복합원재료)의 전용 서류' 안에서만 팩트를 확인하십시오. 다른 서류에 적힌 같은 이름의 원료 스펙을 끌어와 섞지 마십시오.

🔥 **Rule 40. [열량 5kcal 단위 반올림 우선의 원칙]**
   - 열량 실측값이 120%를 초과해도, '가장 가까운 5kcal 단위' 반올림 적용 시 시안 표시량과 일치하면 무조건 ✅적합 판정하십시오. Rule 11보다 우선 적용합니다.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - [계산 공식]: (시안 표시량 ÷ 식약처 1일 영양성분 기준치) × 100 (소수점 첫째 자리 반올림)
   - [🚨주의]: 절대 서류의 실측값으로 계산하지 마십시오! 오직 시안에 적힌 '표시량' 기준으로만 역산하십시오. 시안에 기재된 %와 직접 계산한 %가 다르면 즉시 지적하십시오.

🔥 **Rule 42. [완제품 vs 원료 서류 혼동 절대 금지]**
   - 시안(최종 제품)의 '식품유형', '소비기한', '보관방법', '품목보고번호'를 검증할 때, 그 안에 들어가는 원재료(예: 유산균배양액 등)의 품목제조보고서를 기준 삼아 대조하는 대형 환각을 엄격히 금지합니다.

🔥 **Rule 43. [시각적 오독(OCR) 및 구획 혼동 금지]**
   - 온도 표기의 물결표(~)를 숫자로 오독하지 마십시오. (예: 1~35℃를 135℃로 읽지 말 것). 소비기한 칸의 내용과 그 주변 칸의 텍스트를 마음대로 짬뽕해서 읽지 마십시오.
---
"""

def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (V6.5 - 무삭제 풀버전 & 분리 입력)")
    st.markdown("---")

    product_type = st.radio("📌 1. 식품유형 선택", ("특수의료용도식품 / 환자식", "일반식품"))
    st.markdown("---")

    # [UI] 시안 업로드 구역 (4분할)
    st.subheader("🎨 2. 시안 이미지 (준비된 면만 업로드)")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        img_main = st.file_uploader("주표시면(앞면)", type=["jpg", "png", "jpeg"], key="img_main")
    with c2:
        img_info = st.file_uploader("정보표시면(뒷면)", type=["jpg", "png", "jpeg"], key="img_info")
    with c3:
        img_nutri = st.file_uploader("영양성분표", type=["jpg", "png", "jpeg"], key="img_nutri")
    with c4:
        img_extra = st.file_uploader("기타면/측면", type=["jpg", "png", "jpeg"], key="img_extra")

    st.markdown("---")
    
    # [UI] 증빙 서류 구역 (성적서, 배합비, 원료서류 완벽 분리)
    st.subheader("📄 3. 증빙 및 법적 서류 (분리 업로드 시 정확도 향상)")
    d1, d2, d3 = st.columns(3)
    with d1:
        report_docs = st.file_uploader("시험성적서 (실측치 확인용)", type=["pdf", "jpg", "png"], accept_multiple_files=True, key="report")
    with d2:
        recipe_docs = st.file_uploader("배합비 / 레시피 (설계치 확인용)", type=["pdf", "csv", "jpg", "png"], accept_multiple_files=True, key="recipe")
    with d3:
        legal_docs = st.file_uploader("원료라벨 / 품목보고서 (명칭/원산지용)", type=["pdf", "jpg", "png"], accept_multiple_files=True, key="legal")

    if st.button("🔍 구역별 데이터 매칭 QC 시작", type="primary"):
        user_content = []
        
        def add_item(file_obj, label):
            if file_obj:
                if isinstance(file_obj, list):
                    for f in file_obj: process_single_file(f, label)
                else: process_single_file(file_obj, label)

        def process_single_file(f, label):
            user_content.append(f"### [데이터 분류: {label}] ###")
            if f.type.startswith("image"):
                user_content.append(Image.open(f))
            elif f.name.lower().endswith(".csv"):
                user_content.append(f.getvalue().decode('utf-8', errors='ignore'))
            else:
                temp = f"temp_{f.name}"
                with open(temp, "wb") as file: file.write(f.getbuffer())
                uploaded = genai.upload_file(temp)
                while uploaded.state.name == "PROCESSING": time.sleep(1)
                user_content.append(uploaded)

        with st.spinner("모든 룰(Rule 1~43)을 적용하여 정밀 검토 중입니다..."):
            add_item(img_main, "시안_주표시면")
            add_item(img_info, "시안_정보표시면")
            add_item(img_nutri, "시안_영양성분표")
            add_item(img_extra, "시안_기타면")
            add_item(report_docs, "근거_시험성적서")
            add_item(recipe_docs, "근거_배합비레시피")
            add_item(legal_docs, "근거_원료법적서류")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            final_prompt = f"""
            [현재 검토 제품유형]: {product_type}
            
            [🚨형식 고정 절대 명령🚨]
            당신은 창의성을 발휘하지 마십시오. 아래 제공된 [결과 리포트 출력 템플릿]의 1번부터 6번까지의 구조와 명칭을 100% 동일하게 복사하십시오. 
            내용이 없는 칸이라도 목차를 생략하지 말고 '해당 사항 없음'으로 표기하십시오.
            
            [결과 리포트 출력 템플릿 시작]
            ## 1️⃣ [주표시면 및 기타면 검토]
            ## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
            ## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
            ## 4️⃣ [영양표시 검토 및 % 기준치 검증]
            | 영양성분 | 시안 표시량 | 시안 기재 % | 총내용량 환산 실측값 | 허용오차 판정 | % 계산 검증 (일치여부) |
            ## 5️⃣ [기타 법적 의무사항]
            ## 6️⃣ [종합의견 및 즉시 수정 지시사항]
            [결과 리포트 출력 템플릿 끝]
            """

            try:
                # 🔥 창의성 제로 설정 유지
                generation_config = genai.types.GenerationConfig(
                    temperature=0.0
                )

                response = model.generate_content(
                    user_content + [final_prompt],
                    generation_config=generation_config
                )
                st.markdown(response.text)
            except Exception as e:
                st.error(f"🚨 오류 발생: {e}")
            finally:
                for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
