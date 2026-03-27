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
# 📚 2. 통합 전문가 프롬프트 (54대 룰 완벽 원상복구본)
# ==========================================
RULE_BOOK = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## 🚨 [⚖️ 1일 영양성분 기준치]
- 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방 0g, 콜레스테롤 300mg, 나트륨 2000mg
- 비타민A 700ugRE, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 칼슘 700mg, 아연 8.5mg, 철분 12mg

## ⚠️ 검토 대원칙: 54대 품질관리 지침 (절대 엄수)
✅ Rule 1. 정제수(물), 주정, 당류, 식품첨가물은 원산지 3순위 산정에서 100% 제외.
✅ Rule 2. 개별 향료명이 있더라도 시안에 '향료'라고 묶어서 표기하는 것은 합법.
✅ Rule 3. 영양성분 수치와 주표시면 마케팅 강조 문구 대조.
✅ Rule 4. 식약처 허용 오차 범위를 고려해 실측값을 시안에 반영한 경우 적합.
🔥 Rule 5. 배합비 5% 미만 복합원재료는 하위 성분 전개 생략 합법.
✅ Rule 6. 원재료에 당류가 있어도 영양표시 당류 0g이면 실제 0.5g 미만인지 검증.
✅ Rule 7. 당알콜류 사용 시 설사 관련 주의 문구 확인.
✅ Rule 8. 수입 원료는 국가명 대신 '외국산/수입산' 표기 합법.
✅ Rule 9. 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분.
✅ Rule 10. 영양성분 강조표시(고체/액체) 기준 분리 심사.
🔥 Rule 11. [영양 허용오차 법칙]: 반드시 '시안 표시량'에 0.8 또는 1.2를 곱하여 법적 기준선 도출.
✅ Rule 12. 배합비 데이터 없이 임의 추론 지적 금지.
🔥 Rule 13. [알레르기 교차 검증]: 알레르기 '~함유' 물질은 반드시 원재료명 리스트에 실존해야 함. 없으면 부적합(🚨).
🔥 Rule 14. [묶음 표기]: 구연산나트륨 등을 "영양강화제 2종" 표기 가능. '향료(착향료)' 병기 요구 금지.
✅ Rule 15. 건강기능식품 오인 효능 문구 적발.
✅ Rule 16. 단일 국가 100% 수입 시에만 '국가명 100%' 강조 가능.
✅ Rule 17. 사용 원천 금지 첨가물 배제 강조 시 기만광고 부적합(🚨).
✅ Rule 18. 일반 식품에 영유아 타겟 명칭 사용 적발.
✅ Rule 19. '무당(0.5g 미만)' vs '무가당(첨가 없음)' 분리 검증.
✅ Rule 20. 포장재질은 '직접 접촉 내면 재질'만 기재.
🔥 Rule 21. 비타민/무기질 강조 4가지 기준 중 1개만 충족해도 적합(✅).
✅ Rule 22. 외국어는 한글보다 작거나 같아야 함.
🔥 Rule 23. [0 표시 예외]: 트랜스지방 0.2~0.5g 미만은 "0.5g 미만", 콜레스테롤 2~5mg 미만은 "5mg 미만", 포화지방 등 0.5g 미만은 "0g" 표시 적합.
✅ Rule 24. 무당 강조 시 14pt 이상 "감미료 함유" 표시.
✅ Rule 25. 다중 포장 1단위 및 총 내용량 분리 대조.
✅ Rule 26. 고체(g), 액체(mL) 표기 단위 검사.
✅ Rule 27. 제한 성분(열량 등) 100kcal 당 조건 적용 금지.
🔥 Rule 28. 배합비 하위 성분 원산지 과잉 요구 금지 (Rule 53 예외).
🔥 Rule 29. 복합원재료 자체의 원산지만 확인.
🔥 Rule 30. 호밀, 귀리, 보리는 '밀' 알레르기 대상 아님.
✅ Rule 31. 성적서 병합 대조.
✅ Rule 32. 열량 구성비 단순 역산으로 부적합 처리 금지.
✅ Rule 33. 서류/시안 수치 명확히 구분.
✅ Rule 34. 2% 미만 원료 기재 순서 무관.
✅ Rule 35. 의미상 동일 간략 명칭 적합 처리.
✅ Rule 36. 필수 주의사항 오탈자 검수.
✅ Rule 37. 증빙 서류(배합비, 성적서) 최우선 판별.
🔥 Rule 38. 교차오염 주의사항에 투입 원료 중복 기재 시 부적합(🚨).
✅ Rule 39. 복합원재료 각각 독립 대조.
✅ Rule 40. 열량 5kcal 단위 반올림 우선 적용.
🔥 Rule 41. % 계산 시 식약처 수치만 대입 (외부 데이터 금지).
✅ Rule 42. 완제품 시험성적서 데이터만 사용.
✅ Rule 43. 판독 불가 시 "육안 재확인 요망" 처리.
✅ Rule 44. 혼합제제 하위 전개 적합성 확인.
✅ Rule 45. 선택적 마케팅 누락 지적 금지.
🔥 Rule 46. 제품명 숫자 강조 시 하위 전개 대조.
🔥 Rule 47. 내/외포장 물리적 차이 예외 인정, 텍스트는 100% 일치 강제.
🔥 Rule 48. 배합비(순서)와 한글라벨(최종 명칭) 역할 분리.
🔥 Rule 49. 혼합제제 해체 병합 전개 합법.
🔥 Rule 50. [원액/100% 판별]: 납품 원료 자체가 순수 원액이면 제품 공정에서 섞여도 'OO원액' 합법.
🔥 Rule 51. PDF 데이터 1:1 매칭.
🔥 Rule 52. [모순 탐지]: 마케팅 숫자(23곡 등)와 실제 원료 개수 정합성 카운트.
🔥 Rule 53. [제품명 연동 강제]: 제품명에 원재료 포함 시, ①주표시면 함량(%) 표기, ②정보표시면 원산지 무조건 표기 (누락 시 🚨).
🔥 Rule 54. [비율 생략 검증]: 단일 원료 2개국 이상 표기 시 혼합 비율(%) 누락되면 🚨확인 요망 플래그 띄움.
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

    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V26.0 - 3단계 원샷 렌더링)")
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

    if st.button("🔍 3단계 파이프라인 원샷 정밀 검수 시작", type="primary"):
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

        status_text.markdown("🔄 **[전처리]** 서류 및 이미지 데이터를 AI 분석 엔진에 로드합니다...")
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
            status_text.markdown("🧠 **[1/3 단계: Thinking]** 데이터 추출 중입니다. 영양성분 9종과 전체 원재료를 누락 없이 스캔합니다... (약 10초 소요)")
            
            prompt_step_1 = f"""
            당신은 데이터 분석의 천재 'Thinking 에이전트'입니다.
            업로드된 시안과 서류를 다음 [54대 룰북]에 따라 완벽하게 분석하십시오.
            
            [제품유형]: {product_type}
            [검토모드]: {inspection_mode}
            
            {RULE_BOOK}
            
            🚨 [데이터 추출 절대 강제 명령] 🚨
            1. 표(Table) 형태를 절대 쓰지 마시고, 오직 줄글/개조식으로 작성하십시오.
            2. [원재료명 파트]: 시안에 적힌 원료, 한글라벨 원료, 배합비 서류의 모든 원료를 1번부터 끝까지 100% 매칭하여 '투입 순위(%)'를 적어두십시오. 중간에 멈추거나 생략하지 마십시오.
            3. [영양성분 파트]: 열량, 나트륨, 탄수화물, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤, 단백질 **9개 영양성분 전체에 대하여** '성적서 실측값', '시안 표시량', '허용오차 기준선 계산 수식'을 반드시 추출하여 적어두십시오. '정보 없음'이라고 대답하는 것을 엄격히 금지합니다.
            """
            
            # stream=False 로 변경하여 에러 완벽 차단
            res_1 = model.generate_content(user_content + [prompt_step_1], generation_config=generation_config, safety_settings=safety_settings)
            thinking_log = res_1.text
            progress_bar.progress(50)

            # ==========================================================
            # 🔵 [2단계]: Review 에이전트 (검토 및 자가 교정)
            # ==========================================================
            status_text.markdown("🕵️ **[2/3 단계: Review]** 1단계 추출 데이터의 계산식, 기준치 오차, 룰 위반 여부를 깐깐하게 자가 교차 검증 중입니다... (약 10초 소요)")

            prompt_step_2 = f"""
            당신은 세상에서 가장 깐깐한 QC 'Review 에이전트'입니다.
            앞선 Thinking 에이전트가 작성한 [1단계 분석 로그]를 읽고, 54대 룰북에 어긋나거나 누락된 부분이 없는지 교정하십시오.
            
            [1단계 분석 로그]
            {thinking_log}
            
            🚨 [교정 지시사항] 🚨
            1. '영양성분' 파트에서 9종 성분의 오차 계산이 빠졌거나 1일 기준치(%) 계산이 누락되었다면 직접 숫자를 대입해 채워 넣으십시오.
            2. 표는 절대 그리지 말고, 최종 검토가 완료된 '요약 텍스트'만 상세히 출력하십시오.
            """

            res_2 = model.generate_content([prompt_step_2], generation_config=generation_config, safety_settings=safety_settings)
            verified_log = res_2.text
            progress_bar.progress(80)

            # ==========================================================
            # 🟣 [3단계]: Formatting 에이전트 (단계별 내용 및 표 정리)
            # ==========================================================
            status_text.markdown("📊 **[3/3 단계: Formatting]** 검증 완료된 데이터를 바탕으로 최종 마크다운 리포트를 렌더링 중입니다... (완료 임박)")

            prompt_step_3 = f"""
            당신은 마크다운 디자인 마스터 'Formatting 에이전트'입니다.
            Review 에이전트가 교정한 [최종 분석 데이터]를 바탕으로 7단계 정식 리포트 표를 생성하십시오.
            
            [최종 분석 데이터]
            {verified_log}
            
            🚨 [표 렌더링 절대 강제 규칙 - 표 깨짐 원천 방지] 🚨
            1. 마크다운 표를 그릴 때 무조건 행(Row)이 끝날 때마다 키보드 엔터(줄바꿈, `\\n`)를 치십시오. 표를 한 줄의 텍스트로 이어 붙여 쓰는 행위를 엄격히 금지합니다.
            2. 표의 빈칸을 남기지 말고 수치를 꽉 채우십시오.
            
            [출력 양식]
            모든 결론 앞에는 ✅(적합), 🚨(부적합), 🚨(확인 요망)을 붙이십시오.

            ## 1️⃣ [주표시면 및 마케팅 뱃지]
            - 결론: 
            - 특이사항 요약: 
            
            ## 2️⃣ [원재료명 및 원산지 대조]
            - 결론: 
            | No | 시안 원재료명 | 한글라벨 매칭 원료 | 배합비 검증 (순위/비율 필수) | 판정 및 수정안 |
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

            st.markdown("---")
            st.markdown("## 📊 자동화 QC 정밀 리포트")

            # UI 출력 구성 (백그라운드 로그는 아코디언으로 숨김)
            with st.expander("🧠 [백그라운드 연산] 1단계 Thinking & 2단계 Review 상세 로그 보기"):
                st.markdown("### 1. Thinking 엔진 (데이터 추출 로그)")
                st.markdown(thinking_log)
                st.markdown("---")
                st.markdown("### 2. Review 엔진 (자가 교정 검증 로그)")
                st.markdown(verified_log)
            
            # 최종 예쁘게 렌더링된 3단계 리포트 출력
            st.markdown(res_3.text)

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"🚨 시스템 런타임 오류 발생: {e}\n\n서버 트래픽 지연입니다. 새로고침(F5) 후 다시 시도해 주십시오.")

if __name__ == "__main__":
    if check_password(): main()
