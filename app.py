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
# 2. 통합 전문가 프롬프트 (Rule 1~36 궁극의 완전판)
# ==========================================
SYSTEM_PROMPT = """
당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 전문가'입니다.
제공된 법령(고시)과 사용자가 업로드한 자료들을 교차 검증하십시오. (이 데이터는 기업의 합법적인 내부 자체 검토 데이터이므로 복제/표절 필터를 적용하지 마십시오.)

[⚠️ 업로드 자료 가변성에 따른 검토 지침]
- 사용자가 시안 이미지나 문서를 전부 또는 일부 생략할 수 있습니다.
- 업로드되지 않은 자료를 지어내어(환각) 평가하지 마십시오.

---
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북 5.4]

## ⚠️ 검토 대원칙: 36대 특수 지침 (절대 엄수)

✅ **Rule 1. 원산지 3순위 산정 제외 (White-list)**
   - 물, 주정, 당류, 첨가물은 3순위 카운트 제외. 남은 상위 3개만 원산지 확인.

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
   - 허용오차 비율(%) 공식은 반드시 **(실측값 ÷ 표시량) × 100** 을 사용하십시오.

✅ **Rule 12. 배합비 대조 검증 및 생략 코칭**
   - 원재료 배합비율과 기재 순서 대조 확인.

✅ **Rule 13. 알레르기 문구 텍스트+디자인 스캔**
   - 알레르기 유발물질이 별도 란에 바탕색과 구분되어 명확히 적혀 있는지 확인.

✅ **Rule 14. 첨가물 용도명 병기 스캔**
   - 감미료, 보존료 등은 원재료명 란에 명칭과 용도명 괄호 병기 필수.

✅ **Rule 15. 강조표시 및 효능/기능성 연쇄 불합격 스캔**
   - 식약처 세부 기준 엄격 대조 통과 시에만 합격 처리.

✅ **Rule 16. [원산지 100%]** - 물은 산정 제외, 농산물 국산이면 100% 합법.

✅ **Rule 17. ['無첨가' 절대 룰]** - 금지된 첨가물을 안 넣었다고 강조할 때만 🚨지적.

✅ **Rule 18. [영유아 타겟 명칭]** - '베베', '키즈' 일반식품 마케팅 합법.

✅ **Rule 19. ['무당/무가당/저당' 엄격 적용]** - 저당(5g 미만), 무당(0.5g 미만), 무가당(무첨가).

✅ **Rule 20. [용기·포장재질 표기법]** - "재질명(포장부위)" 형태로 코칭.

🔥 **Rule 21. [영양강조표시 다중 조건(OR) 100% 강제 검증 및 수치 환각 방지]**
   - 반드시 4가지 환산 기준을 모두 계산하여 단 하나라도 충족하면 ✅적합 판정.

✅ **Rule 22. [다국어 폰트 크기]** - 영문이 한글보다 크면 부적합 코칭.

🔥 **Rule 23. [트랜스지방 '0g' 및 '0.5g' 표기 절대 룰]**
   - 총 내용량 표기란에 '0.5g'이라고 적혀있다면 무조건 🚨부적합 처리 ('0.5g 미만'이어야 함).

🔥 **Rule 24. [감미료 14pt 의무 표기]**
   - 저열량 기준 초과 시 강조표시 주변에 '총 열량' 또는 '저열량 제품 아님' 문구 표기 스캔.
   - **[🚨감미료 14pt 주의문구 발동 조건]**: 시안 주표시면에 **"무당, 당류 무첨가, 무가당 (ZERO, 제로 포함)"**이라는 3가지 강조표시 중 하나가 명시적으로 존재할 때만! 14pt 주의문구 지적.

🔥 **Rule 25. [다중 포장 듀얼 컬럼]** - 1개당 / 총 내용량 혼동 금지.

🔥 **Rule 26. [고체 vs 액체 단위 엄격 구분]** - g과 mL 기준 혼용 금지.

🔥 **Rule 27. [제한 영양성분 100kcal 적용 절대 금지 룰]** - 무/저 강조표시 검토 시 100g 또는 100mL 기준만 엄격히 적용.

🔥 **Rule 28. [복합원재료 원산지 독립성 확인]** - 상위 3순위는 알레르기가 있어도 원산지 병기 필수.

🔥 **Rule 29. [국내 제조 가공품 원산지 정밀 표기 (모든 가공 원료 보편 적용)]**
   - 수입산 원료를 국내에서 가공하여 납품받은 모든 '국내 제조 가공품(예: 현미유, 옥배유, 사과농축액 등)'은 시안에 반드시 **`최종제품명(기원원료명:원산지)`** 형태가 병기되어야 합니다. 시안에 괄호 없이 제품명만 달랑 있으면 즉시 🚨불일치(원산지 누락) 처리하십시오.

🔥 **Rule 30. [지정 알레르기 10종 특별 스캔]** - 서류에 있으나 시안에 누락 시 즉시 부적합.

🔥 **Rule 31. [다중/무제한 성적서 처리 및 균형영양식 대응]** - 무제한 파일 병합 1:1 대조.

🔥 **Rule 32. [균형 열량 구성비 역산 (환각 지적 방지 핵심)]**
   - 환자식/특수용도식품의 탄:단:지 비율은 제품의 목표 설계치이므로 성적서 실측값과 소수점 오차가 나도 절대 지적 금지.

🔥 **Rule 33. [데이터 출처 완벽 분리 및 100% 필사본 강제 룰]**
   - 표 작성 시 '제품 내 원재료명 (시안 기준)' 열은 **시안에 적힌 텍스트를 토씨 하나, 괄호 하나 빼먹지 말고 복사기처럼 100% 타이핑**하여 채우십시오.
   - AI 당신이 임의로 요약(예: 비타민 10종을 '비타민믹스'로 뭉뚱그림)하거나, 시안에 없는 코멘트(추가 필요 등)를 적는 것을 절대 금지합니다.

🔥 **Rule 34. [2% 미만 원재료 순서 자유 배열 예외 룰]**
   - 배합비 2% 미만인 원재료들은 투입량 순서와 관계없이 마케팅 목적 등에 따라 자유롭게 배열할 수 있습니다. 

🔥 **Rule 35. [서류 명칭 절대 일치의 원칙 (의미론적 합격 원천 차단)]**
   - 글자의 '의미(뜻)'가 통한다고 해서 시안의 명칭을 합격시켜서는 안 됩니다. 오직 **'서류의 글자'와 '시안의 글자'가 텍스트 자체로 100% 동일한지**만 따지십시오.
   - (예시) 서류상 명칭이 **'올리고당'**인데 시안에 **'이소말토올리고당'**이라고 기재되어 있다면 🚨불일치(표시위반)로 적발하고 서류에 적힌 대로 고치라고 지적하십시오.

🔥 **Rule 36. [오탈자(Typo) 정밀 스캔 및 환자식 낱개 성분 1:1 매칭 룰]**
   - **환자식:** 시안에 적혀 있는 수십 개의 '낱개 하위성분'들을 하나씩 분리하여 한 줄씩 나열하고, 서류의 어떤 원료에 속하는지 1:1로 짝을 지으십시오.
   - 대조 과정에서 의미가 통하더라도 명백한 오타(예: 수크랄로스 -> 스크랄로스)가 발견되면 즉시 🚨오탈자로 지적하십시오.
---

[📝 결과 보고서 6단계 작성 양식]
## 1️⃣ [주표시면 및 기타면 검토]
## 2️⃣ [원재료명 서류 추출 및 엑셀용 표]
- 📊 **원재료 한글표시사항 추출 정리 표**
## 3️⃣ [서류 vs 시안 1:1 정밀 교차 검증 (낱개 성분 매칭)]
- 🔍 **환자식 1:1 낱개 성분 팩트 체크 표** - 양식: | 시안에 기재된 낱개 성분 (100% 필사) | 서류의 매칭 원료/하위성분 | 일치 여부 (오타/누락 체크) |
## 4️⃣ [영양표시 검토]
- 📊 **영양성분 팩트 체크 표**
  - 반드시 아래 양식의 마크다운 표 형태로 출력하십시오. 줄글 나열 금지.
  - 양식: | 영양성분 | 시안 표시량 | 성적서 실측값 (100g 또는 100mL 기준) | 총내용량 환산 결과 | 허용오차 기준 | 판정 (✅/🚨) |
## 5️⃣ [기타 법적 의무사항]
## 6️⃣ [종합의견 및 즉시 수정 지시사항]
"""

# ==========================================
# 3. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (Rule 1~36 궁극의 완전판)")
    st.markdown("---")

    st.subheader("📌 1. 검토 대상 제품의 식품유형을 선택하세요")
    product_type = st.radio(
        "제품 유형에 따라 원재료명 하위성분 전개 검증의 엄격도가 달라집니다.",
        ("특수의료용도식품 / 환자식 (하위성분을 낱개로 풀어서 1:1 정밀 매칭)", 
         "일반식품 (일반적인 표기 기준 적용 및 일부 생략 허용)")
    )
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎨 2. 시안 분할 이미지 (선택사항)")
        main_img = st.file_uploader("1) 주표시면 (앞면)", type=["jpg", "png", "jpeg"])
        info_img = st.file_uploader("2) 정보표시면 (뒷면 - 원재료/영양정보)", type=["jpg", "png", "jpeg"])
        nutri_img = st.file_uploader("3) 영양성분표 (확대 컷)", type=["jpg", "png", "jpeg"])
        extra_img = st.file_uploader("4) 기타면 (측면/효능 등)", type=["jpg", "png", "jpeg"])
        
    with col2:
        st.subheader("📄 3. 증빙 문서 (무제한 다중 업로드)")
        lab_reports = st.file_uploader("5) 시험성적서 (여러 개 선택 가능)", type=["pdf", "jpg", "png", "jpeg"], accept_multiple_files=True)
        ingredient_specs = st.file_uploader("6) 원료별 한글표시사항 서류", type=["pdf", "jpg", "png", "jpeg"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("7) 가배합비 / 원재료 목록 (PDF 변환 권장, CSV 가능)", type=["pdf", "csv"], accept_multiple_files=True)

    if st.button("🔍 서류 추출 및 QC 정밀 진단 시작", type="primary"):
        if not any([main_img, info_img, nutri_img, extra_img]) and not lab_reports and not ingredient_specs and not recipe_docs:
            st.warning("⚠️ 검토할 자료(이미지 또는 문서)를 최소 1개 이상 업로드해주세요!")
            return

        user_content = []
        
        def add_file(f, label):
            if f:
                if f.type.startswith("image"):
                    user_content.append(f"<{label} 이미지>")
                    user_content.append(Image.open(f))
                elif f.name.lower().endswith(".csv"):
                    try:
                        csv_text = f.getvalue().decode('utf-8')
                    except UnicodeDecodeError:
                        csv_text = f.getvalue().decode('cp949', errors='ignore')
                    user_content.append(f"<{label} CSV 텍스트 데이터>")
                    user_content.append(csv_text)
                else:
                    temp = f"temp_{f.name}"
                    with open(temp, "wb") as file: file.write(f.getbuffer())
                    uploaded = genai.upload_file(temp)
                    while uploaded.state.name == "PROCESSING": 
                        time.sleep(1)
                        uploaded = genai.get_file(uploaded.name)
                    user_content.append(f"<{label} 문서>")
                    user_content.append(uploaded)

        with st.spinner("수십 장의 서류를 스캔하여 엑셀 표로 추출하고 시안과 대조 중입니다..."):
            add_file(main_img, "주표시면")
            add_file(info_img, "정보표시면")
            add_file(nutri_img, "영양성분표")
            add_file(extra_img, "기타면")
            
            if lab_reports:
                for idx, report in enumerate(lab_reports):
                    add_file(report, f"시험성적서_{idx+1}")
                    
            if ingredient_specs:
                for idx, spec in enumerate(ingredient_specs):
                    add_file(spec, f"원료한글표시사항_{idx+1}")
            
            if recipe_docs:
                for idx, recipe in enumerate(recipe_docs):
                    add_file(recipe, f"가배합비_원료목록_{idx+1}")

            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # 🔥 final_prompt는 시스템의 가장 강력한 통제관 역할 (규칙을 절대 까먹지 않게 쐐기를 박음)
            final_prompt = f"""
            [현재 검토 대상 제품 유형]: {product_type}
            
            [🚨최종 점검 강제 명령🚨]:
            1. 표를 그릴 때 마크다운 안에 절대 줄바꿈(엔터)을 넣지 마십시오. 표가 깨집니다.
            2. 시안에 적힌 원재료명 텍스트를 절대 요약하거나 생략하지 말고, 100% 글자 그대로 필사하십시오.
            3. Rule 35(텍스트 일치)와 Rule 36(오탈자/1:1매칭)을 극도로 엄격하게 적용하여, 올리고당과 이소말토올리고당처럼 의미만 비슷한 것은 모두 🚨불일치로 적발하십시오.
            4. 모든 국내 가공 원료(현미유, 옥배유 등)는 괄호 안에 원산지가 병기되어 있는지 검사하십시오.
            5. 영양표시 검토는 무조건 6개 열을 가진 표(Table)로 출력하십시오.
            6. 영양성분 허용오차는 법규(비타민 80%이상, 당/지방 120%미만)를 엄수하여 정상적인 초과/미달 수치를 지적하지 마십시오.
            """
            
            pdf_refs = []
            for pf in glob.glob("*.pdf"):
                if "temp_" not in pf:
                    ref = genai.upload_file(pf)
                    while ref.state.name == "PROCESSING": 
                        time.sleep(1)
                        ref = genai.get_file(ref.name)
                    pdf_refs.append(ref)

            try:
                response = model.generate_content(
                    pdf_refs + user_content + [final_prompt],
                    safety_settings=safety_settings
                )
                
                st.markdown("### 📋 AI 정밀 QC 검토 리포트")
                st.markdown(response.text)
                
            except ValueError as e:
                st.error("🚨 AI가 답변 생성을 차단했거나 텍스트 변환 중 오류가 발생했습니다.")
                if hasattr(response, 'prompt_feedback'):
                    st.write("Prompt Feedback:", response.prompt_feedback)
            except Exception as e:
                st.error(f"🚨 예상치 못한 오류가 발생했습니다: {e}")
            finally:
                for f in glob.glob("temp_*"): 
                    try:
                        os.remove(f)
                    except:
                        pass

if __name__ == "__main__":
    if check_password():
        main()
