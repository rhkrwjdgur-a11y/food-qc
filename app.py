import streamlit as st

# ==========================================
# 🚨 [UI 레이아웃 픽스] 반드시 최상단에 위치해야 넓은 화면이 유지됩니다!
# ==========================================
st.set_page_config(page_title="식품 QC 마스터", page_icon="🏭", layout="wide")

import google.generativeai as genai
import glob
import time
import os
import re
import tempfile
import socket
import io

# 👇 [네트워크 방어] 파이썬 전체 대기 시간을 10분(600초)으로 연장
socket.setdefaulttimeout(600)

# ==========================================
# 🔠 [Google Cloud Vision API 설정] (순수 OCR)
# ==========================================
# GCP 서비스 계정 키(JSON)가 st.secrets나 환경변수에 세팅되어야 정상 작동합니다.
try:
    from google.cloud import vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

def extract_text_with_vision(file_path):
    """Google Cloud Vision API를 사용하여 이미지에서 순수 텍스트를 추출하는 함수"""
    if not VISION_AVAILABLE:
        return "🚨 [시스템 알림]: google-cloud-vision 라이브러리가 설치되지 않았습니다."
    
    try:
        client = vision.ImageAnnotatorClient()
        with io.open(file_path, 'rb') as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        response = client.document_text_detection(image=image)
        if response.error.message:
            return f"🚨 [Vision API 에러]: {response.error.message}"
        return response.full_text_annotation.text
    except Exception as e:
        return f"🚨 [Vision API 실행 오류]: {e}"

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
    else:
        return True

# ==========================================
# 🔑 1. API 키 및 모델 설정
# ==========================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-pro"

# ==========================================
# 🛡️ AI 표 깨짐 강제 복구 함수
# ==========================================
def fix_markdown_table(text):
    text = re.sub(r'([^\n])\s*(\|\s*No\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*시안 원재료명\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*팩\(내포장\)\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*서류 매칭 원료\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\s*(\|\s*영양성분명\s*\|)', r'\1\n\n\2', text)
    text = re.sub(r'\|\s+\|', '|\n|', text)
    text = re.sub(r'([^\n])\n(\|)', r'\1\n\n\2', text)
    text = re.sub(r'\|\n\n\|', '|\n|', text)
    return text

# ==========================================
# 📚 2. 시스템 지시어
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 시스템'입니다.
당신에게는 창의성, 추론 능력, 융통성이 전혀 없습니다. 오직 화면에 보이는 픽셀 단위의 글자(Text)만 있는 그대로 읽고 기계적으로 1:1 대조하는 봇(Bot)입니다.
이전 대화의 다른 제품 시안 데이터를 현재 검토에 절대 개입시키지 마십시오. 오직 현재 사용자가 업로드한 문서만을 팩트로 사용하십시오.
기본적으로 철자, 띄어쓰기, 기호가 다르면 '불일치(부적합)'로 판정하되, **제공된 룰북(Rule)에 명시된 예외 조항(예: 당알코올 10% 컷오프, 향료 통합, 간략명/동의어 허용, 내부 코드 생략, 2% 미만 순서 유연성 등)은 이 1:1 기계적 대조 원칙보다 무조건 최우선으로 적용하여 합법(✅) 처리하십시오.**
🔥 [오탈자 무관용 및 환각 차단 원칙]: 단어의 의미가 통하더라도 글자(자음/모음)가 단 하나라도 다르면 무조건 부적합 처리하십시오. 특히 '염화콜린'을 '염화칼륨'으로 잘못 읽는 등 기계의 배경지식으로 글자를 유추하여 소설을 쓰는(환각) 행위를 엄격히 금지합니다.
부적합을 지적할 때는 단순히 "다릅니다"라고만 하지 말고, 제공된 룰북(Rule)에 근거하여 "왜 이것이 법적으로 잘못되었는지, 어떻게 수정해야 하는지" 명확하고 구체적인 사유를 반드시 설명하십시오.
모든 검토 결과의 결론 앞에는 반드시 ✅(적합) 또는 🚨(부적합) 또는 🚨(확인 요망) 또는 ⚠️(실무 검토 권장) 이모지를 붙이십시오."""

# ==========================================
# 📚 3. 75대 룰북 원문 
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

**[⭐ 비율(%) 표기 절대 규칙]:** 소수점 첫째 자리에서 반올림하여 정수(1% 단위)로 표시합니다.
**[⭐ 1% 미만 예외 규칙]:** 비율이 1% 미만인 경우 반드시 "1% 미만"이라고 표기하십시오. (함량이 0g인 경우에만 0%로 표기)

## ⚠️ 검토 대원칙: 75대 품질관리 지침

🔥 **Rule 1. [원산지 3순위 산정 제외 및 임의 분류(환각) 금지]**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.
   - **[🚨 AI 임의 분류 금지]**: '나한과추출분말', '진득찰추출분말' 등 추출물이나 분말 류를 이름만 보고 임의로 '식품첨가물'로 오판하지 마십시오! 서류상 명백히 '식품첨가물'로 분류되지 일반 원료는 무조건 원산지 표시 대상 순위에 포함시켜야 합니다.

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 식약처 고시상 완벽 적합입니다.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 및 총열량/식이섬유 열량 계산 강제 룰]**
   - 주표시면(앞면)에 열량(kcal)이나 특정 영양소 함량(예: 칼슘 200mg)이 강조되어 있다면, 반드시 뒷면 영양성분표의 수치와 단 1의 오차도 없이 100% 일치하는지 교차 대조하십시오.
   - **[⭐ 함량 수치 보수적 표기 핑계 금지]**: 앞면은 200mg인데 뒷면 영양성분표는 220mg인 경우, 다르면 무조건 표시 불일치(🚨부적합)입니다.
   - **[⭐ 세트포장(박스) 총내용량 및 총열량 누락 스나이퍼]**: 박스/세트 포장의 주표시면에는 반드시 '총 내용량(또는 단품용량 x 수량)'과 그에 상응하는 '총 열량(kcal)'이 모두 기재되어야 합니다. 누락 시 즉시 🚨부적합 처리하십시오.
   - **[⭐ 열량 계산 시 식이섬유 및 당알콜 분리 필수 적용]**: 영양성분표에 **식이섬유**나 **당알콜**이 표기되어 있다면 반드시 총 탄수화물에서 그 양을 분리하여 계산하십시오. *(적용 공식 ➔ 식이섬유: 2kcal/g, 에리스리톨: 0kcal/g, 자일리톨 등: 2.4kcal/g, 나머지 당질(탄수화물): 4kcal/g)*

✅ **Rule 4. 영양성분 실측값 허용**
   - 영양성분은 식약처 허용 오차 범위를 고려하여 시험성적서의 실측값을 시안에 그대로 반영한 경우 합법(적합)으로 인정하십시오.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 법적으로 하위 성분을 전개할 의무가 없습니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 영양표시 당류가 0g으로 표기되었다면, 실제 함량이 0.5g 미만인지 검증하십시오.

🔥 **Rule 7. [당알코올 주의문구 개정 (10% 컷오프 룰)]**
   - 2026년 시행 개정법 완벽 반영: 자일리톨, 에리스리톨 등 당알코올류가 최종 제품에 **10% 미만**으로 사용된 경우, "과량 섭취 시 설사를 일으킬 수 있습니다" 등의 주의문구 생략은 100% 합법(✅)입니다. 억지 부적합 지적을 절대 금지합니다.
   - 단, 당알코올 함량이 10% 이상일 때만 해당 문구 누락 시 🚨부적합 처리하십시오.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 경우 특정 국가명 대신 '외국산' 또는 '수입산'으로 표기해도 적합합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되었는지 확인하십시오.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 기준 강제 분리)**
   - 제품의 제형에 따라 100g 또는 100mL 당 기준을 엄격히 분리하여 영양 강조 심사를 하십시오.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 및 과다검출 이상치 경고 룰]**
   - **[⭐ 역산 금지]**: 무조건 '시안 표시량'을 기준으로 법적 기준선을 도출하십시오.
   - **[하한선만 검사하는 80% 이상 합법 그룹]**: 탄수화물, 단백질, 비타민, 미네랄 등. ➔ (실측값) >= (표시량 * 0.8) 이면 **제조사의 의도된 보수적(안전빵) 표기이므로 무조건 적합(✅)**입니다.
   - **[⭐ 과다 검출 이상치 경고]**: 실측값이 표시량의 3배(300%)를 초과할 경우 `✅ 적합` + `⚠️ [실무 검토 권장]` 경고 추가.
   - **[상한선만 검사하는 120% 미만 합법 그룹]**: 열량, 나트륨, 당류, 지방, 트랜스지방, 포화지방, 콜레스테롤 등. ➔ (실측값) <= (표시량 * 1.2) 이면 무조건 적합(✅).

✅ **Rule 12. [원재료명 3단 교차 검증 및 임의 추론 금지]**
   - 배합비 데이터 서류 없이 레시피를 상상하거나 임의로 지적하지 마십시오.

🔥 **Rule 13. [알레르기 정밀 추적 및 파생 원료 예외 허용]**
   - 시안의 "~함유" 박스에 적힌 모든 알레르기 유발물질은 반드시 '원재료명' 리스트 내에 실존해야 합니다.
   - **[⭐ 알레르기 위치 표기 절대 규칙]**: 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 한 번만 기재되어 있으면 100% 합법입니다.
   - **[⭐ 기계적 대조 예외]**: 파생 원료가 존재한다면 절대 불일치로 오판하지 말고 무조건 적합(✅) 처리하십시오.

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 완벽 스나이퍼]**
   - **[⭐ 표 4 (명칭+용도명 병기 의무)]**: 감미료, 보존료, 산화방지제 등 표 4에 속하는 첨가물은 반드시 "명칭+용도명"으로 기재.
   - **[⭐ 표 5 (간략명 표기 허용 및 용도명 대체 금지)]**: 표 5에 속하는 첨가물은 용도명으로 뭉뚱그려 쓸 수 없으며 반드시 정해진 명칭이나 허용된 간략명으로 기재.
   - **[⭐ 표 6 (용도명 대체 100% 합법)]**: 유화제, 산도조절제, 증점제, 팽창제, 영양강화제 등 표 6에 해당하는 첨가물은 용도명만 표기해도 완벽한 합법(✅).

✅ **Rule 15. [기능성 오인 문구 스캔]**
   - 건강기능식품으로 오인할 수 있는 마케팅 문구를 스캔하여 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가에서 100% 수입된 원료인 경우에만 '국가명 100%' 강조가 가능합니다.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지된 첨가물을 배제했다고 강조한 경우 기만광고로 부적합(🚨) 처리하십시오.

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 일반 식품에 영유아를 타겟으로 하는 명칭 사용을 적발하십시오.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 분리 검증]**
   - '무당'은 당류 0.5g 미만일 때, '무가당'은 인위적 당류 첨가가 없을 때 적합합니다.

🔥 **Rule 20. [포장재질 표시 (식약처 vs 환경부 분리 스나이퍼)]**
   - **[텍스트 표시 (식약처)]**: '포장재질' 텍스트 블록에는 식품과 직접 접촉하여 용출 우려가 있는 재질(예: 폴리에틸렌 등 합성수지)만 기재하는 것이 원칙입니다. **종이나 유리는 텍스트 표시 의무가 없으므로 생략하는 것이 완벽한 합법**입니다. 다포장/세트(박스/트레이)의 경우에도 내포장의 직접 접촉 재질인 '폴리에틸렌(내면)'을 표기하는 것이 올바른 정답이므로, 이를 "박스와 재질 표기가 다르다"거나 "복붙 에러다"라며 오판(🚨)하지 마십시오. 무조건 ✅적합 처리하십시오.
   - **[분리배출 마크 (환경부)]**: '종이단상자' 등 종이 재질의 외포장재(트레이/박스)는 환경부 규정상 **분리배출표시 의무 대상이 아닙니다.** 따라서 박스 시안에 종이 분리배출 마크가 누락되어 있더라도 이를 🚨부적합으로 지적해서는 절대 안 되며, 100% 합법(✅) 처리하십시오. 단, 내포장(팩)의 멸균팩 마크 등은 필수입니다.

🔥 **Rule 21. [영양강조표시 '고/풍부' 4대 조건 교차 연산 룰]**
   - '고단백', '고식이섬유', '비타민 풍부' 등 '고(High)/풍부'를 강조할 경우, 영양소별로 아래 4대 조건 중 **단 하나라도 충족**해야 합법(✅)입니다.
   - **[고단백]**: 100g당 11g 이상 / 100mL당 5.5g 이상 / 100kcal당 5.5g 이상 / 1회섭취량당 11g 이상
   - **[고식이섬유]**: 100g당 6g 이상 / 100kcal당 3g 이상 / 1회섭취량당 5g 이상
   - **[비타민/무기질(고/풍부)]**: 100g당 1일 기준치의 30% 이상 / 100mL당 15% 이상 / 100kcal당 10% 이상 / 1회섭취량당 30% 이상
   - **[저당]**: 100g당 5g 미만 / 100mL당 2.5g 미만 (이 중 하나 충족)

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. 단, 상표 로고는 예외입니다.

🔥 **Rule 23. [식약처 영양성분 '0' 표시 예외 규정 (법적 사유 지적 강제)]**
   - **트랜스지방:** 0.2~0.5g 미만은 "0.5g 미만" 표시. 0.2g 미만은 무조건 "0g" 표시.
   - **콜레스테롤:** 2~5mg 미만은 "5mg 미만" 표시.
   - **포화지방 등:** 0.5g 미만은 "0g" 표시 시 적합.

🔥 **Rule 24. [당류 강조표시(무당/저당/무가당/설탕무첨가) 연계 의무 표기 룰]**
   - '무당', '저당', '무가당', '설탕 무첨가' 등 당류 관련 강조표시가 패키지에 적혀있을 때 발동합니다.
   - 1) **[열량 병기 위치 강제 (모두 공통 적용)]**: 위 강조표시 중 하나라도 존재하고 제품이 '저열량' 기준(액체 기준 100mL당 20kcal 미만 등)을 충족하지 못하면, 반드시 강조표시 바로 옆이나 아래에 '총 열량'을 병기해야 합니다.
   - 2) **[당류 컷오프 확인 강제 (모두 공통 적용)]**: 강조표시가 있다면 영양성분표의 '당류' 수치가 법적 컷오프(저당: 액체 100mL당 2.5g 미만 / 무당: 0.5g 미만)를 통과하는지 강제로 교차 검증하십시오.
   - 3) **[감미료 위치 검증 (무당/무가당/설탕무첨가에만 한정 적용)]**: '저당'을 제외한 무당/무가당 류를 표기하면서 감미료가 들어갔다면 "감미료 함유" 문구를 강조표시 주변에 적어야 합니다. **(주의: '저당' 단독 강조 시에는 감미료 함유 문구가 법적 필수가 아니므로 무조건 ✅해당없음 처리할 것.)**

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 수치를 명확히 분리하여 영양성분을 대조 검증하십시오.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 중량(g), 액체는 용량(mL)으로 적절히 표기되었는지 검사하십시오.

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등 제한 성분은 100kcal 당 조건을 적용하지 마십시오.

🔥 **Rule 28. [원산지 3순위 완벽 필터링 및 과잉 표기 경고 룰]**
   - 1) **[3순위 강제 도출]**: 정제수, 주정, 당류, 식품첨가물을 원산지 산정 순위에서 강제로 제외하십시오. 남은 진짜 원료 중 상위 1위, 2위, 3위 원료를 정확히 도출하고, 누락되었다면 🚨부적합 처리하십시오.
   - 2) **[과잉 도출 경고]**: 의무 대상이 아닌 하위 부원료에 원산지가 적혀 있다면 무조건 🚨**[확인 요망]**을 띄워 경고하십시오.

🔥 **Rule 29. [국내 가공 복합원재료 원산지 역추적 합법성 (환각/오판 절대 금지)]**
   - 서류상 복합원재료(예: 난소화성말토덱스트린)의 원산지(제조국)가 '대한민국(국내)'이더라도, 디자이너가 시안에 **그 하위 원물의 원산지(예: 옥수수(외국산:러시아 등))를 역추적하여 전개 표기했다면 이는 농수산물 원산지표시법을 완벽히 준수한 합법(✅)**입니다. 기계는 절대로 이를 "과잉 표기"나 "서류 불일치"로 억지 오판하여 지적하지 마십시오!

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 식약처 규정상 **호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.**

✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 여러 시험성적서가 제공된 경우 모든 영양성분을 누락 없이 병합하여 종합 대조하십시오.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 영양성분표 수치 반올림 오차에 의한 단순 계산 차이는 적합(✅)으로 인정.

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치를 명확히 구분하여 리포트를 작성하십시오.

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 배합비 기준 투입량 2% 미만 원료는 기재 순서가 달라도 적합으로 판정하십시오.

🔥 **Rule 35. [🌟 범용 간략명/동의어 허용 및 N종 묶음 절대 금지 (강력 예외 룰)]**
   - ⭐ **[식약처 공식 이명/동의어 범용 허용]**: 글자(픽셀)가 다르더라도, 식품첨가물공전 및 식약처 기준상 완벽하게 동일한 화학적 이명/동의어(예: 결정셀룰로오스 = 결정섬유소, 구연산나트륨 = 구연산삼나트륨)인 경우에는 절대 부적합 처리하지 마십시오. 이는 완벽한 합법이므로 ✅적합으로 판정하되, 반드시 판정 사유에 "🌟[공식 이명/동의어 알림]: 서류는 OO이나 시안은 OO로 표기됨. 식약처 인정 공식 동의어이므로 합법."이라고 명시하십시오.
   - **[🌟 고도 정제 원료 기원 생략]**: 포도당, 물엿, 과당 등 단일 당류는 서류에 옥수수전분 등 기원이 적혀있어도, 시안에서 이를 생략하고 '포도당'이라 적는 것이 100% 합법입니다.
   - **[🌟 첨가물 부형제 생략]**: 펙틴 등 혼합제제 서류에 포함된 부형제/희석제(자당, 덱스트린, 포도당 등)가 시안에서 생략되고 '펙틴'처럼 주원료만 적힌 것은 완벽한 합법입니다.
   - **[🌟 수치 그대로 표시 허용]**: 영양표시 시 5.6g 등 소수점이 포함된 실측값을 그대로 적는 것은 합법(✅)입니다. 억지로 반올림을 강요하지 마십시오.
   - **[🌟 간략화 치환]**: 서류의 복잡한 명칭을 시안에서 통용명(예: `비타민 B1 염산염` -> `비타민B1`)으로 간략화한 경우 합법입니다. 🌟 [표5/6 치환 알림]을 띄우십시오.
   - **[🌟 괄호 상세명칭 생략]**: 서류에 `유성비타민A지방산에스테르(비타민A아세테이트)` 처럼 괄호로 이명이나 구체적 명칭이 부연 설명된 경우, 시안에서 괄호를 통째로 날리고 `유성비타민A지방산에스테르`라고만 적는 것은 완벽한 합법(✅)입니다.
   - **[🌟 화학식/기호/영문 약어 범용 예외]**: 식약처 공전에 등재된 공식 이명(예: 카복시메틸셀룰로스나트륨 = CMC-Na, CMC, 셀룰로스검)은 100% 합법입니다. 🚨부적합 처리 절대 금지. α = ALPHA 등도 모두 일치 처리.
   - **[🚨 'N종' 묶음 간략화 절대 금지]**: 말토덱스트린 2종, 비타민 3종, 야채농축액 5종 등 **일반 원료나 하위 성분을 '숨길 목적'으로 숫자로 묶는 것은 명백한 법규 위반이며 무조건 🚨부적합 처리**하십시오. 기계가 제멋대로 일반 원료에 면죄부를 주지 마십시오. (※ 예외 허용: '향료 2종'처럼 향료이거나, '영양강화제 2종'처럼 표 6 항목이거나, 괄호로 100% 전개된 경우에만 합법)

✅ **Rule 36. [주의사항 오탈자 스캔]**
   - 필수 주의사항 문구의 오탈자를 정밀 검수하십시오.

✅ **Rule 37. [법적 서류 우선 원칙]**
   - 증빙 서류 데이터를 최우선으로 하되, Rule 35(간략명) 예외를 항상 먼저 고려하십시오.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 룰 (수학적 차집합 연산)]**
   - **[⭐ 수학적 차집합 검증 로직]**: [교차오염 정답지] = [공장 취급 마스터 목록] - [직접 투입 알레르기 물질]. 우유 등 특정 물질에만 얽매이지 말고, 범용적으로 모든 추출된 알레르기 물질을 대입하여 연산하십시오. 중복이나 누락 시 부적합(🚨).

✅ **Rule 39. [동명 원료 종속성 원칙]**
   - 동명의 복합원재료가 있더라도 각각을 별도로 독립 대조 검증하십시오.

🔥 **Rule 40. [열량 표기 및 반올림 원칙]**
   - 단품 열량이 '0 kcal'로 적법하게 표기되었더라도, 세트(박스) 총 열량은 실측 소수점을 합산하여 5kcal 단위로 반올림하므로 모순 지적을 금지합니다.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증 및 수식 노출 강제]**
   - 열량(kcal)과 트랜스지방은 비율(%)을 표기하는 항목이 아닙니다. `(시안 표시량 ÷ 1일 기준치) × 100` 수식을 명시하십시오.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 완제품 기준의 최종 시험성적서 데이터만 사용하십시오.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독이 어려우면 임의 판정 금지.

🔥 **Rule 44. [혼합제제 전개 및 해체 병합(Merge) 완벽 허용 룰]**
   - 혼합제제는 2가지 합법적인 표기 방식이 있으며, 둘 중 하나만 만족하면 무조건 ✅적합 처리하십시오.
   - [방식 A (괄호 전개)]: `비타민혼합제제(비타민C, 포도당, 전분)` 처럼 괄호 안에 내림차순으로 전개한 경우 (합법)
   - [방식 B (완전 해체 병합)]: 혼합제제의 괄호를 완전히 없애고, 하위 성분들을 다른 원료들과 섞어 내림차순으로 뿔뿔이 흩어지게 기재하는 것도 완벽한 합법입니다. "괄호가 없다"며 부적합(🚨)을 지적하는 것을 절대 금지합니다.

✅ **Rule 45. [선택적 누락 허용]**
   - 마케팅적 선택 누락은 지적하지 마십시오.

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자가 포함된 경우 하위 전개 내역 스캔.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정 및 뼈대 정보 교차 검증]**
   - **[🌟 영문 제품명 예외 허용]**: 앞면의 영문 브랜드명(예: MH Milk House)과 뒷면의 법적 한글 제품명이 불일치해도 디자인 요소로 완벽히 합법(✅)입니다.

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(투입 순서)와 한글라벨(최종 명칭) 역할 분리.

🔥 **Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 주표시면에 '원액', '추출물', '농축액' 함량(%)을 강조한 경우, 반드시 그 주변에 '고형분 함량(%)' 또는 '배합함량(%)' 기재 강제.

🔥 **Rule 51. [고형분(Brix) 보수적 표기 예외]**
   - 고형분 함량 시안 수치가 서류 스펙보다 낮게 표기된 경우 보수 표기이므로 무조건 적합(✅).

🔥 **Rule 52. [영양성분 단순 명칭 강조 및 '함유' 컷오프 완벽 검증 룰]**
   - 패키지 전 구역(측면, 주표시면 등 위치 불문)에 '단백질 4g', '칼슘 함유' 등 영양소 명칭을 단독으로 기재하거나 아이콘/뱃지로 강조한 경우, 반드시 영양소별로 아래 **[함유/급원 4대 조건]** 중 **단 하나라도 충족**해야 합법(✅)입니다.
   - **[단백질]**: 100g당 1일 기준치(55g)의 10%(5.5g) 이상 / 100mL당 5%(2.75g) 이상 / 100kcal당 5%(2.75g) 이상 / 1회섭취량당 10%(5.5g) 이상
   - **[비타민/무기질]**: 100g당 1일 기준치의 15% 이상 / 100mL당 7.5% 이상 / 100kcal당 5% 이상 / 1회섭취량당 15% 이상
   - **[식이섬유]**: 100g당 3g 이상 / 100kcal당 1.5g 이상 / 1회섭취량당 1일 기준치(25g)의 10%(2.5g) 이상

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 농수산물 원물인 경우 가공품으로 투입되었더라도 정보표시면에 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성 검증 룰]**
   - 단일 원료에 대해 2개 이상 국가 병기 시 비율(%) 누락 여부 확인 요망 플래그.

🔥 **Rule 55. [영양성분 소수점 및 반올림 강제 규정]**
   - 포화지방 5g 이상은 소수점 없이 정수로, 트랜스지방 0.2g 미만은 소수점 없이 0g 표시.

🔥 **Rule 56. [HACCP 인증 마크 공식 텍스트 검증]**
   - "안전관리인증", "식품안전관리인증", "축산물안전관리인증" 합법. "위해요소중점관리우수식품" 등은 부적합.

🔥 **Rule 57. [세트포장 식품이력추적관리번호 수량 강제 룰]**
   - 박스 번호에 "수량(예: X 16입)"이 기재되어야 완벽한 합법(✅). 삭제 지적 절대 금지.

🔥 **Rule 58. [주표시면 함량 기재 시 원재료명 함량 생략 합법성]**
   - 앞면에 함량(%)이 적혀있다면 뒷면 원재료명에는 %를 생략해도 100% 합법(✅).

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰]**
   - 1) 소비자 상담 번호 2) 반품/교환 장소(구입처 등) 3) "부정·불량식품 신고는 국번없이 1399" 문구. 
   - 4장(전 구역) 중 단 한 곳에라도 적혀 있다면 합법(✅) 처리하십시오. 

🔥 **Rule 60. [복합원재료 원물 함량 강제 환산 및 타겟 원물 스나이퍼 룰]**
   - 제품명에 강조된 원물이 '페이스트, 농축액' 등 복합원재료 형태면 반드시 괄호로 진짜 원물 배합함량(%)을 기재해야 합법. 단, 농축액 괄호 안에 **'고형분(%)'이 이미 명시되어 있다면 배합함량 기재 의무를 완벽히 다한 것이므로, 추가로 (원물명 100%) 표기를 요구하는 과잉 지적(오버킬)을 엄격히 금지**합니다. (예: `검은콩농축액(고형분60%)` 표기는 완벽한 합법(✅)임)

🔥 **Rule 61. [가공국 vs 원물국 분리 및 국산 예외 실무 룰 (QA 고도화)]**
   - 명칭이 '페이스트, 농축액, 분말' 등으로 끝나는 복합원재료의 경우, 원물이 국산이고 국내에서 가공했다면 괄호 안에 원물명을 쓰지 단고 곧바로 (국산)이라고 써도 완벽한 합법(✅)입니다.

🔥 **Rule 62. [축산물 주표시면 냉동/냉장 의무 표시 및 자체 추론 룰]**
   - 축산물 가공품이 냉장/냉동 제품인 경우 주표시면(앞면)에 상태를 명시해야 함.

🔥 **Rule 63. [미드팩 190mL 질소충전 표기 확인 룰]**
   - (1번 탭에서 용량이 190mL로 판별된 경우에 한함) 기타면/주의사항 구역에 "질소충전" 단어가 기재되어야 함. (4번 탭에서 최종 검사)

🔥 **Rule 64. [원물 기만표시(99.9% 등) 스나이퍼 룰]**
   - 패키지 앞면에 강조된 비율(예: 100%)이 실제 순수 '원물' 투입량이 아니라 '추출액'의 비율이라면 🚨**무조건 부적합(기만표시)** 처리.

🔥 **Rule 65. [원료명 내부 식별 코드(버전) 생략 합법성]**
   - 서류상 원료명 뒤에 붙은 내부 식별용 숫자/기호(예: `-2`, `(A)`)는 시안에서 생략해도 100% 합법(✅)입니다.

🔥 **Rule 66. [영양성분 법정 단위 하드코딩 매칭 룰 (단위 스나이퍼)]**
   - 영양정보표의 각 영양소 단위는 반드시 아래의 **[법정 단위 정답지]**와 일치해야 합니다. (g vs mg 오타 적발 시 🚨부적합)
   - **[kcal]**: 열량
   - **[g]**: 탄수화물, 당류, 식이섬유, 단백질, 지방, 포화지방, 트랜스지방
   - **[mg]**: 나트륨, 콜레스테롤, 비타민B1, 비타민B2, 비타민B6, 비타민C, 판토텐산, 칼슘, 인, 칼륨, 철(철분), 마그네슘, 아연, 구리, 망간
   - **[µg]**: 비타민D, 비타민B12, 비타민K, 비오틴, 요오드, 셀레늄, 몰리브덴, 크롬
   - **[특수 복합]**: 비타민A (`µg RE` 또는 `µg RAE`), 비타민E (`mg α-TE`), 나이아신 (`mg NE`), 엽산 (`µg DFE`)

🔥 **Rule 67. [영양정보표 하단 법정 안내문구 토시 검증 룰]**
   - 영양정보표 하단에는 반드시 **"1일 영양성분 기준치에 대한 비율(%)은 2,000kcal 기준이므로 개인의 필요 열량에 따라 다를 수 있습니다."** 가 적혀 있어야 합니다. "1일 영양소 기준"처럼 법적 용어를 임의로 축약하면 무조건 🚨부적합.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 및 내용량 복붙(Copy&Paste) 스나이퍼 룰]**
   - 검토 모드가 '선물세트 박스(외포장)'일 경우, 디자이너가 낱팩 시안의 텍스트를 그대로 복붙했는지 아래 사항들을 강제 스캔하여 하나라도 어긋나면 🚨부적합 처리하십시오.
   - 1) **[정보표시면 내용량]**: 내용량이 낱팩 용량(예: 125mL)으로만 적혀있다면 복붙 에러. 반드시 `낱팩용량 x 수량` 형태여야 함.
   - 2) **[영양성분표 맨 윗줄]**: 반드시 `총 내용량 [전체용량] (낱개용량 x 개수)` 형태여야 함.
   - 3) **[영양성분표 칼로리 줄]**: 총 내용량 바로 아래 칼로리 표기는 단순히 `15 kcal`가 아니라, 반드시 `1개(또는 1팩)당 15 kcal` 형태로 기재되어야 함.
   - 4) **[영양성분표 안쪽 열 제목]**: 표 내부의 영양성분 기준 수치 열 제목은 `총 내용량당`이 아니라, 반드시 `1개당` 또는 `1개(OO mL)당` 이어야 함.

🔥 **Rule 69. [비타민 아래첨자(Subscript) 타이포그래피 스나이퍼 룰]**
   - 원재료명, 영양성분표, 주표시면 등 패키지 전 구역에서 비타민(B1, B2, B6, B12, D3 등) 표기 시, 일반 숫자(예: B6)가 사용되었다면 반드시 ⚠️**[타이포 교정 권장]** 플래그를 띄우십시오.
   - 법적인 위반(부적합)은 아니지만, 브랜드의 전문성과 품질(QC) 관리를 위해 반드시 **아래첨자(예: B₁, B₂, B₆, B₁₂, D₃)** 폰트로 통일하여 수정할 것을 지적해야 합니다.

🔥 **Rule 70. [내/외포장 원재료명 100% 일치 강제 범용 스나이퍼 룰 (의미 해석 절대 금지)]**
   - 세트포장(박스/트레이) 검토 시, 내포장(낱팩)의 원재료명과 외포장(박스)의 원재료명은 토시 하나 틀리지 않고 100% 똑같아야 합니다. 
   - **[⭐ AI 의미 해석 및 동의어 적용 강제 비활성화(Disable)]**: 서류와의 대조 시에는 Rule 35(동의어 허용)가 적용되어 합법일지라도, **내포장 시안과 외포장 시안 텍스트끼리 대조할 때는 당신의 '의미 해석 능력'과 'Rule 35'를 완전히 꺼버리십시오.** 구연산나트륨과 구연산삼나트륨처럼 화학적으로 완벽히 동일한 동의어이더라도 눈에 보이는 글자(픽셀)가 다르면 무조건 🚨부적합(내외포장 불일치) 처리하고, 차이점을 명시하십시오. 당신은 의미를 모르는 기계적 글자 판독기입니다.

🔥 **Rule 71. [타이포그래피 및 강조 폰트 크기 규정 (육안 검수 알림)]**
   - 기계는 폰트 크기를 정확히 잴 수 없으므로, 주표시면 등에 제품명 원재료 함량이나 셀링문구가 있는 경우 무조건 ⚠️플래그를 띄워 "원료 함량은 14pt 이상, 셀링문구는 12pt 이상, 장평 90%, 자간 -6% 규정에 맞게 디자인되었는지 디자이너 원본을 통해 육안 점검하십시오."라고 알림을 주십시오.

🔥 **Rule 72. ['조리예/이미지 사진' 필수 텍스트 점검]**
   - 주표시면에 과일, 채소, 요리 등 연출된 이미지 사진이 있다면 "조리예" 또는 "이미지 사진"이라는 문구가 표기되어야 합니다. 이미지가 있다면 해당 텍스트를 스캔하고, 10pt 이상인지 육안 확인하라는 알림을 띄우십시오.

🔥 **Rule 73. [테트라팩/프리즈마 용기 세부 재질 스나이퍼]**
   - 뚜껑이 있는 종이팩(콤비스마일, 프리즈마 등) 제품일 경우, 정보표시면이나 기타면의 포장재질 란에 본체 재질뿐만 아니라 `뚜껑: HDPE`, `개봉부: PP` 등 세부 재질이 누락 없이 적혀있는지 스캔하십시오.

🔥 **Rule 74. [식품유형별 '개봉 후 주의문구' 강제 스캔]**
   - 과채음료, 우유류 등 액상 음료 제품의 주의사항에는 "개봉 후 냉장보관하거나 빨리 드시기 바랍니다" 등 부패 방지용 주의문구가 필수적으로 기재되어야 합니다. 누락 시 🚨확인 요망을 띄우십시오.

🔥 **Rule 75. [CS 클레임 방어용 필수 주의문구 세트]**
   - 제품 특성에 따라 "원료 성분에 의해 침전물이 생길 수 있으나...", "용기가 변형, 팽창, 손상되었거나 내용물이 변질되었을 경우 드시지 마십시오" 등의 실무 방어용 CS 문구가 존재하는지 스캔하고, 누락되었다면 실무 검토를 권장하십시오.
"""

# ==========================================
# 📚 4. 탭별 핵심 룰 슬라이싱 
# ==========================================
def get_sliced_rules(rule_numbers):
    rules = []
    lines = RULE_BOOK_FULL.split("\n")
    current_rule = []
    is_capturing = False
    for line in lines:
        if line.startswith("✅ **Rule") or line.startswith("🔥 **Rule"):
            match = re.search(r'Rule (\d+)', line)
            if match and int(match.group(1)) in rule_numbers:
                is_capturing = True
                if current_rule:
                    rules.append("\n".join(current_rule))
                    current_rule = []
                current_rule.append(line)
            else:
                if current_rule:
                    rules.append("\n".join(current_rule))
                    current_rule = []
                is_capturing = False
        elif is_capturing:
            current_rule.append(line)
    if current_rule:
        rules.append("\n".join(current_rule))
    return "\n\n".join(rules)

COMMON_RULES = [36, 37, 42, 43, 45, 47]
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 9, 10, 15, 16, 17, 18, 19, 21, 24, 28, 40, 46, 47, 50, 51, 52, 53, 57, 58, 59, 60, 62, 63, 64, 68, 69, 71, 72] + COMMON_RULES)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 6, 7, 8, 12, 13, 14, 20, 25, 28, 29, 30, 34, 35, 38, 39, 44, 48, 52, 54, 57, 58, 59, 60, 61, 65, 68, 69, 70, 73, 74, 75] + COMMON_RULES)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 6, 10, 11, 21, 23, 25, 26, 27, 31, 32, 33, 40, 41, 55, 59, 66, 67, 68, 69] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([7, 15, 17, 18, 20, 22, 24, 38, 56, 57, 59, 63, 64, 69, 73, 74, 75] + COMMON_RULES)

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    for key in ["result_tab1", "result_tab2", "result_tab3", "result_tab4", "result_summary", "uploaded_content", "local_file_paths"]:
        if key not in st.session_state:
            st.session_state[key] = None if key != "local_file_paths" else []

    print_css = """
    <style>
    @media print {
        [data-testid="stSidebar"], header, footer, [data-testid="stHeader"], [data-testid="stToolbar"],
        .stFileUploader, .stButton, .stRadio, .stTextInput, button { display: none !important; }
        [role="tablist"], [data-baseweb="tab-list"] { display: none !important; }
        html, body, .stApp, main, .block-container, 
        [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"] {
            height: auto !important; min-height: 100% !important; max-height: none !important;
            overflow: visible !important; position: static !important; width: 100% !important; max-width: 100% !important;
            padding: 0 !important; margin: 0 !important; display: block !important;
        }
        table { page-break-inside: auto !important; width: 100% !important; border-collapse: collapse !important; }
        tr { page-break-inside: avoid !important; page-break-after: auto !important; }
        th, td { page-break-inside: avoid !important; border: 1px solid black !important; padding: 8px !important; }
    }
    </style>
    """
    st.markdown(print_css, unsafe_allow_html=True)
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V300.0 - 미션 쪼개기 & 하이브리드 OCR)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        st.markdown("#### ⚙️ [옵션] 초정밀 OCR 모드 전환")
        use_vision_api = st.checkbox("🔠 Google Cloud Vision API 병행 사용 (강력한 환각 억제)", value=False, help="이 기능은 GCP 서비스 계정 키가 설정되어 있어야 작동합니다.")
        
        st.markdown("#### 🛠️ [옵션] 텍스트 수동 복붙 (OCR 환각 차단용)")
        st.session_state["manual_target"] = st.text_area("📦 타겟(박스) 원재료명 직접 입력", height=100)
        st.session_state["manual_compare"] = st.text_area("🧃 비교용(팩) 원재료명 직접 입력", height=100)

        st.markdown("---")
        st.markdown("#### 🏭 공장 알레르기 마스터 설정")
        factory_allergens = st.text_area("우리 공장 취급 알레르기 물질 (쉼표로 구분)", "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류")
        
        st.markdown("---")
        product_type = st.radio("📌 1. 식품유형", ("일반식품 (두유류 등 - 냉장표시 의무 없음)", "특수의료용도식품 / 환자식", "냉장 축산물 (우유/가공유 등)"))
        inspection_mode = st.radio("📌 2. 검토 모드", ("단품(팩/단일포장) 기본 검토", "선물세트 박스(외포장) 교차 검토"))
        doc_type = st.radio("📌 3. 증빙 서류 형태", ("통합 엑셀/PDF 자료 (마스터표 생략)", "개별 원료 한글라벨 무더기 (마스터표 생성)"))

        st.markdown("---")
        if inspection_mode == "선물세트 박스(외포장) 교차 검토":
            img_main = st.file_uploader("1️⃣ 박스 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 박스 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 박스 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 박스 기타면/측면", type=["jpg", "png", "jpeg"])
            box_main = st.file_uploader("🔍 팩(내포장) 주표시면", type=["jpg", "png", "jpeg"])
            box_info = st.file_uploader("🔍 팩(내포장) 정보표시면", type=["jpg", "png", "jpeg"])
            box_nutri = st.file_uploader("🔍 팩(내포장) 영양성분표", type=["jpg", "png", "jpeg"])
            box_extra = st.file_uploader("🔍 팩(내포장) 기타면/측면", type=["jpg", "png", "jpeg"])
        else:
            img_main = st.file_uploader("1️⃣ 시안 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 시안 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 시안 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 시안 기타면/측면", type=["jpg", "png", "jpeg"])
            box_main = box_info = box_nutri = box_extra = None

        report_docs = st.file_uploader("1️⃣ 시험성적서 (영양성분 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        label_docs = st.file_uploader("2️⃣ 원료 한글라벨/스펙 (원재료 1:1 대조용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("3️⃣ 배합비/레시피 (🔥2% 순서 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            local_paths = [] # Vision API용 로컬 파일 추적
            DEFAULT_DOCS_DIR = "./default_docs"

            def robust_upload(file_path, label):
                user_content.append(f"### [{label}] ###")
                if use_vision_api and file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    vision_text = extract_text_with_vision(file_path)
                    user_content.append(f"[Vision API 순수 OCR 추출 텍스트 (참조용)]\n{vision_text}\n---")
                
                max_retries = 5 
                for attempt in range(max_retries):
                    try:
                        up = genai.upload_file(file_path)
                        while up.state.name == "PROCESSING":
                            time.sleep(3)
                            up = genai.get_file(up.name) 
                        if up.state.name == "FAILED": raise Exception("구글 서버 처리 실패")
                        user_content.append(up)
                        return
                    except Exception as e:
                        if attempt == max_retries - 1: raise e
                        time.sleep(3 * (attempt + 1)) 

            def process(f, label):
                ext = os.path.splitext(f.name)[1] or ".png"
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(f.getbuffer())
                    safe_temp_path = tmp.name
                local_paths.append(safe_temp_path)
                robust_upload(safe_temp_path, label)

            if img_main: process(img_main, "타겟_시안_주표시면")
            if img_info: process(img_info, "타겟_시안_정보표시면")
            if img_nutri: process(img_nutri, "타겟_시안_영양성분표")
            if img_extra: process(img_extra, "타겟_시안_기타면_측면")
            if box_main: process(box_main, "비교용_정답지_시안_주표시면")
            if box_info: process(box_info, "비교용_정답지_시안_정보표시면")
            if box_nutri: process(box_nutri, "비교용_정답지_시안_영양성분표")
            if box_extra: process(box_extra, "비교용_정답지_시안_기타면_측면")
            
            if report_docs:
                for f in report_docs: process(f, "수동추가_근거_시험성적서")
            if label_docs:
                for f in label_docs: process(f, "수동추가_원료_한글라벨_및_스펙")
            if recipe_docs:
                for f in recipe_docs: process(f, "수동추가_배합비_레시피_데이터")
                
            return user_content, local_paths

        st.markdown("---")
        if st.button("🚀 전체 시스템 파일 연동 (하이브리드 모드 지원)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다..."):
                content, paths = get_uploaded_content()
                st.session_state["uploaded_content"] = content
                st.session_state["local_file_paths"] = paths
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    # ==========================================
    # 🔥 3-Pass 파이프라인 (Divide & Conquer 미션 쪼개기 적용)
    # ==========================================
    def run_qc_3pass(tab_rules: str, judgment_prompt: str, extract_missions_list: list = None):
        if not st.session_state["uploaded_content"]:
            st.warning("🚨 좌측 사이드바 하단의 [🚀 전체 시스템 파일 연동] 버튼을 먼저 눌러주세요.")
            return None

        content = st.session_state["uploaded_content"]
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]

        manual_target = st.session_state.get("manual_target", "")
        manual_compare = st.session_state.get("manual_compare", "")
        
        extracted_text_combined = ""

        if extract_missions_list:
            # ── PASS 1: 미션 쪼개기 (Divide & Conquer) 반복 스캔 ──
            extracted_results = []
            for i, mission in enumerate(extract_missions_list):
                st.toast(f"🕵️‍♂️ 분할 미션 {i+1}/{len(extract_missions_list)} 추출 중...")
                pass1_prompt = f"""
[PASS 1 - 텍스트 단일 추출 미션 (Divide & Conquer)]
⭐ 이 단계에서는 판정을 금지합니다. 오직 '아래의 특정 미션'에만 시야를 좁혀 텍스트를 추출하십시오. 다른 정보는 무시하십시오.

[사용자 수동 입력 원재료명 데이터 (최우선 적용 정답지!!)]
- 타겟(박스) 수동 입력값: {manual_target if manual_target else '없음'}
- 비교용(팩) 수동 입력값: {manual_compare if manual_compare else '없음'}

🎯 [현재 타겟 미션]:
{mission}
"""
                try:
                    pass1_response = model.generate_content(content + [pass1_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                    extracted_results.append(f"=== [미션 {i+1} 결과] ===\n" + pass1_response.text)
                except Exception as e:
                    return f"🚨 Pass 1 (단일 추출 {i+1}) 오류 발생: {e}"
            
            extracted_text_combined = "\n\n".join(extracted_results)

            # ── PASS 1.5: 자체 검증 (환각 차단) ──
            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 종합 자체검증 명령]
⭐ 당신은 '매의 눈 검수관'입니다. 아래 수집된 분할 미션 결과들을 검열하십시오.
⭐ [무한 로딩 방지]: 생각 과정을 출력하지 말고, 검증/수정 완료된 텍스트만 출력하십시오.

[분할 미션 통합 텍스트]
{extracted_text_combined}

검증 규칙:
1. ⭐ [오타/환각 원천 차단]: '염화콜린'을 '염화칼륨'으로 잘못 읽는 등 자동완성을 엄격히 금지합니다.
2. ⭐ [없는 데이터 창조 금지]: 서류에 없는 원료를 창조하지 마십시오.
3. ⭐ [누락 및 요약 절대 금지]: "등", "..."을 써서 퉁치는 행위를 금지합니다. 100% 모조리 복원하십시오.
4. ⭐ [XML/JSON 괄호 보존]: 만약 태그나 표로 추출되었다면 그 형태를 훼손하지 마십시오.
"""
            try:
                pass15_response = model.generate_content(content + [pass15_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                verified_text = pass15_response.text
            except Exception as e:
                verified_text = extracted_text_combined

        # ── PASS 2: 판정 ──
        pass2_context = ""
        if extract_missions_list:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================
⭐ [최종 자기검증 명령 및 🔥 Double-Check Protocol]
1. 위 텍스트에 존재하는 내용만을 근거로 삼으십시오.
2. 🚨부적합 판정을 내리기 직전, 속으로만 텍스트를 재검색하십시오. 정말로 없을 때만 🚨부적합 처리하십시오.
"""
        pass2_prompt = f"""
[PASS 2 - 룰 판정 전용 명령]
⭐ 이미지를 직접 다시 참조하는 것을 엄격히 금지합니다. 제공된 문서와 아래 텍스트만 참조하십시오.

[제품유형]: {product_type}
[검토모드]: {inspection_mode}
[우리 공장 알레르기 마스터 목록]: {factory_allergens}

[이 탭에 적용되는 핵심 룰]
{tab_rules}

{pass2_context}

{judgment_prompt}
"""
        try:
            pass2_response = model.generate_content(content + [pass2_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
            if extract_missions_list:
                final_output = (
                    f"<pass1_log>\n{extracted_text_combined}\n</pass1_log>\n"
                    f"<pass15_log>\n{verified_text}\n</pass15_log>\n"
                    f"{pass2_response.text}"
                )
            else:
                final_output = pass2_response.text
            return fix_markdown_table(final_output)
        except Exception as e:
            return f"🚨 Pass 2 (룰 판정) 오류 발생: {e}"

    def run_qc_model(prompt_text):
        if not st.session_state["uploaded_content"]:
            return None
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        generation_config = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=65536)
        full_prompt = f"""
        [제품유형]: {product_type}\n[검토모드]: {inspection_mode}\n[우리 공장 알레르기 마스터 목록]: {factory_allergens}
        {RULE_BOOK_FULL}\n========================================\n당신은 지금 선택된 탭의 임무만 완벽하게 수행해야 합니다.\n{prompt_text}
        """
        try:
            response = model.generate_content(st.session_state["uploaded_content"] + [full_prompt], generation_config=generation_config)
            return fix_markdown_table(response.text)
        except Exception as e:
            return f"🚨 시스템 런타임 오류 발생: {e}"

    def display_result(result, tab_name=""):
        if not result: return
        pass1_match = re.search(r'<pass1_log>(.*?)</pass1_log>', result, re.DOTALL)
        pass15_match = re.search(r'<pass15_log>(.*?)</pass15_log>', result, re.DOTALL)

        if pass1_match:
            pass1_log = pass1_match.group(1).strip()
            result = result.replace(pass1_match.group(0), "").strip()
            with st.expander(f"📋 Pass 1 분할 미션 원본 로그 보기 ({tab_name})"): st.markdown(f"*{pass1_log}*")

        if pass15_match:
            pass15_log = pass15_match.group(1).strip()
            result = result.replace(pass15_match.group(0), "").strip()
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 보기 ({tab_name}) ← 실제 판정에 사용된 텍스트"): st.markdown(f"*{pass15_log}*")

        st.markdown(result)

    # ==========================================
    # 탭 UI (분할 미션 적용)
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "📊 5️⃣ 종합 보고서"])

    # ── TAB 1: 주표시면 ──
    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "주표시면(앞면) 이미지에서 '제품명, 내용량, 칼로리, 마케팅 강조문구'만 리스트로 정확히 추출하십시오. (박스/팩 분리)",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 그리고 앞면에 강조된 특정 영양소의 '% 기준치' 수치만 추출하십시오.",
                    "업로드된 서류(배합비, 성적서)에서 주표시면에 강조된 성분(예: 단백질 등)의 투입량(%)과 실측값(mg/g)을 추출하십시오."
                ]
                judgment_prompt = """
## 1️⃣ [주표시면 및 마케팅 뱃지]
- 결론: (✅ 적합 또는 🚨 부적합/확인요망)
- ⭐ [Rule 71] 강조 폰트 크기 점검 (알림 발생): 
- ⭐ [Rule 72] 조리예/이미지 사진 표기 점검:
- ⭐ [Rule 62] 축산물 보관상태(냉동/냉장) 주표시면 명시: 
- ⭐ [Rule 63] 미드팩 190mL 질소충전 점검: 
- ⭐ [Rule 3] 세트포장(박스) 앞면 총내용량 및 총열량 누락 검증: 
- ⭐ [Rule 68] 다포장 낱팩 복붙 스나이퍼: 
- ⭐ [Rule 60] 강조 원물 복합원재료 시 배합함량 기재 검증: 
- ⭐ [Rule 64] 원물 기만표시(99.9% 등) 스캔:
- ⭐ 마케팅 강조 수치(mg/g) 하이브리드 검증 (배합비+성적서): 
- ⭐ [Rule 47] 박스 vs 팩 뼈대 정보 교차 검증:
- ⭐ [Rule 50] 원액/추출물 고형분 병기:
- ⭐ [Rule 24] 당류 강조표시(무당/저당/무가당/설탕무첨가) 검증 (감미료 문구, 열량 병기, 컷오프):
- ⭐ [Rule 52] 영양강조 컷오프(4대 조건) 검증:
## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발: (100% 무관용 전수 검사)
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【분할 미션 스캔 중... (시간이 소요됩니다)】"):
                missions = [
                    "오직 '타겟(박스) 시안'의 원재료명 리스트만 추출하십시오. 쉼표(,)를 기준으로 XML 태그 `<item>원재료</item>` 형태로 감싸서 100% 모두 나열하십시오. 중략 절대 금지.",
                    "오직 '비교용(팩) 시안'이 있다면 해당 원재료명 리스트만 추출하십시오. XML 태그 `<item>원재료</item>` 형태로 감싸서 100% 모두 나열하십시오.",
                    "정보표시면에 있는 '알레르기 유발물질(OO 함유 등)', '교차오염 주의문구', '기타 CS 주의문구(침전물, 팽창 등)' 텍스트만 추출하십시오.",
                    "정보표시면의 행정 정보(제조원, 포장재질, 품목제조보고번호)만 추출하십시오.",
                    "증빙 서류(한글라벨, 성적서)의 모든 원료명, 하위 성분(100%), 원산지를 표로 추출하십시오.",
                    "배합비(레시피) 서류가 있다면 원료명과 배합비율(%)을 표로 추출하십시오. 없으면 '없음' 명시."
                ]
                
                base_tab2_warning = """
⭐ [1:1 대조 예외 절대 원칙 (Rule 2, 34, 35, 65 우선 적용)] ⭐
🔥 [시스템 절대 족쇄: 순서 검증 시 환각 및 얼렁뚱땅 금지 (2% 기준선 강제 분리)] 🔥
🔥 [마크다운 표 강제 규정 (No Truncation - 중략 시 시스템 붕괴)] 🔥
"""
                # 판정 프롬프트는 검토 모드에 따라 분기 (이전 코드와 동일한 로직 유지)
                if doc_type == "통합 엑셀/PDF 자료 (마스터표 생략)":
                    judgment_prompt = base_tab2_warning + "## 1️⃣ [Rule 70. 내포장 vs 외포장 1:1 대조]\n- 검증 결과:\n## 2️⃣ [마스터 서류 vs 시안 교차 검증]\n(여기에 1:1 대조 표 작성, 생략 금지)\n### 🚨 [누락 스나이퍼]\n## 3️⃣ [배합비 2% 순서 검증]\n## 4️⃣ [알레르기, 주의사항 교차 검증]\n## 5️⃣ [행정 정보 교차 검증]\n## 6️⃣ [오탈자 전수 검증]"
                else:
                    judgment_prompt = base_tab2_warning + "## 1️⃣ [원료 스펙 마스터 취합표]\n## 2️⃣ [Rule 70. 내포장 vs 외포장 1:1 대조]\n## 3️⃣ [마스터 서류 vs 시안 교차 검증]\n(여기에 1:1 대조 표 작성, 생략 금지)\n### 🚨 [누락 스나이퍼]\n## 4️⃣ [배합비 2% 순서 검증]\n## 5️⃣ [알레르기, 주의사항 교차 검증]\n## 6️⃣ [행정 정보 교차 검증]\n## 7️⃣ [오탈자 전수 검증]"

                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "타겟(박스) 시안의 영양정보표 내부 수치와 표 바깥의 총 내용량, 칼로리, '1일 영양성분 기준치' 문구를 모두 추출하십시오.",
                    "비교용(팩) 시안이 있다면 영양정보표 내부 수치와 바깥 문구를 모두 추출하십시오.",
                    "시험성적서 서류에서 각 영양성분의 실측값 데이터를 추출하여 표로 정리하십시오."
                ]
                judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
(환산값, 표시량, 80% 하한선 / 120% 상한선 검증 표 기재)
## 🔍 [치명적 오탈자 및 단위 스나이퍼 스캔]
- ⭐ [Rule 66] 단위 오기재 스나이퍼 (g, mg, µg 대조):
- ⭐ [Rule 67] 하단 법정 문구 스나이퍼:
- ⭐ [Rule 68] 영양성분표 복붙 스나이퍼 (총 내용량당 / 1개당 텍스트 강제 확인):
- ⭐ [Rule 69] 비타민 아래첨자 스나이퍼:
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "전 구역 이미지를 스캔하여 필수 의무표시 3종(상담번호, 교환처, 1399 문구)과 HACCP 인증 마크 텍스트를 추출하십시오. (박스/팩 분리)",
                    "알레르기 직접 함유 표시(바탕색 별도 박스) 및 분리배출 마크 텍스트를 추출하십시오.",
                    "포장재질 표기(뚜껑, 본체 등 세부 재질 포함) 및 CS 방어 주의문구를 모두 추출하십시오."
                ]
                judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 (HACCP 포함)]
- ⭐ [Rule 59] 필수 의무표시 3종 누락 검증:
- ⭐ [Rule 38] 알레르기 교차오염 수학적 차집합 검증:
- ⭐ [Rule 56] HACCP 마크 공식 명칭 적합성:
- ⭐ [Rule 63] 미드팩 190mL 질소충전 점검:
- ⭐ [Rule 73] 용기 세부 재질 스나이퍼:
- ⭐ [Rule 74] 액상 음료 개봉 후 주의문구:
- ⭐ [Rule 75] CS 클레임 방어용 문구 점검:
- ⭐ [Rule 24, 52] 영양강조 및 당류 컷오프 교차 확인:
## 🔍 [전 구간 공통: 수량 모순 및 오탈자 검증]
- ⭐ 오탈자 및 띄어쓰기 적발:
"""
                st.session_state["result_tab4"] = run_qc_3pass(RULES_TAB4, judgment_prompt, missions)
        display_result(st.session_state["result_tab4"], "기타면/측면")

    # ── TAB 5: 종합 보고서 ──
    with tab5:
        if st.button("▶️ 최종 종합 리포트 생성", key="btn_summary"):
            if not any([st.session_state["result_tab1"], st.session_state["result_tab2"], st.session_state["result_tab3"], st.session_state["result_tab4"]]):
                st.warning("🚨 앞의 1~4번 탭 중에서 최소 1개 이상을 먼저 분석해 주십시오!")
            else:
                with st.spinner("최종 수정 지시서를 작성 중입니다..."):
                    def strip_logs(result):
                        if not result: return "분석 안 함"
                        result = re.sub(r'<pass1_log>.*?</pass1_log>', '', result, flags=re.DOTALL)
                        result = re.sub(r'<pass15_log>.*?</pass15_log>', '', result, flags=re.DOTALL)
                        return result.strip()

                    combined_results = f"""
[1번 탭 결과]: {strip_logs(st.session_state.get('result_tab1'))}
[2번 탭 결과]: {strip_logs(st.session_state.get('result_tab2'))}
[3번 탭 결과]: {strip_logs(st.session_state.get('result_tab3'))}
[4번 탭 결과]: {strip_logs(st.session_state.get('result_tab4'))}
"""
                    summary_prompt = f"""
[지시]: 실무자가 한눈에 보고 패키지를 수정할 수 있도록 종합 결론을 내려주십시오.
[기존 분석 데이터]\n{combined_results}
## 📋 [최종 종합 검토 리포트]
- **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)
### 📌 [핵심 지적 사항 및 수정 지시]
(위 분석 데이터에서 '부적합(🚨)' 또는 '확인요망' 내용 요약)
### 🔍 [기타 주의사항]
"""
                    st.session_state["result_summary"] = run_qc_model(summary_prompt)

        if st.session_state["result_summary"]:
            st.markdown(st.session_state["result_summary"])
            st.markdown("""
                <hr class='hide-on-print'>
                <div class='hide-on-print' style='text-align: right; margin-top: 20px; margin-bottom: 20px;'>
                    <button onclick='setTimeout(function(){ window.print(); }, 100);' style='background-color: #FF4B4B; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; font-size: 16px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                        🖨️ 종합 보고서 전용 인쇄
                    </button>
                    <p style='font-size: 12px; color: gray; margin-top: 8px;'>※ 단축키(Ctrl+P)를 누르셔도 스크롤 잘림 없이 인쇄됩니다.</p>
                </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    if check_password():
        main()
