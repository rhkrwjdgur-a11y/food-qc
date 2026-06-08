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
import json

# 👇 [네트워크 방어] 파이썬 전체 대기 시간을 10분(600초)으로 연장
socket.setdefaulttimeout(600)

# ==========================================
# 🔠 [Google Cloud Vision API 설정] (스트림릿 클라우드 호환 버전)
# ==========================================
try:
    from google.cloud import vision
    from google.oauth2 import service_account
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

def extract_text_with_vision(file_path):
    """Google Cloud Vision API를 사용하여 이미지에서 순수 텍스트를 추출하는 함수"""
    if not VISION_AVAILABLE:
        return "🚨 [시스템 알림]: google-cloud-vision 라이브러리가 설치되지 않았습니다."
    
    try:
        if "GOOGLE_VISION_KEY" in st.secrets:
            key_dict = json.loads(st.secrets["GOOGLE_VISION_KEY"])
            credentials = service_account.Credentials.from_service_account_info(key_dict)
            client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
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
# 📚 3. 77대 룰북 원문 (기존 룰 100% 보존 + V310.0 신설 룰 추가)
# ==========================================
RULE_BOOK_FULL = """
# [식품 패키지 표시사항 QC 자동화 검수 시스템 룰북]

## ⭐ [⚖️ 1일 영양성분 기준치 (식약처 고시 별표5 완벽 마스터)] ⭐
오직 아래 명시된 한국 식약처 기준치만 대입하여 %를 산출해야 합니다.
- [다량영양소]: 열량 2000kcal, 탄수화물 324g, 당류 100g, 단백질 55g, 지방 54g, 포화지방 15g, 트랜스지방(기준치 없음), 콜레스테롤 300mg, 나트륨 2000mg
- [비타민류]: 비타민A 700ugRE, 비타민B1 1.2mg, 비타민B2 1.4mg, 나이아신 15mgNE, 판토텐산 5mg, 비타민B6 1.5mg, 비오틴 30ug, 엽산 400ugDFE, 비타민B12 2.4ug, 비타민C 100mg, 비타민D 10ug, 비타민E 11mga-TE, 비타민K 70ug
- [필수지방산]: 알파-리놀렌산 1.3g, 리놀레산 10g, EPA와 DHA의 합 330mg
- [무기질(미네랄)]: 칼슘 700mg, 인 700mg, 칼륨 3500mg, 철(철분) 12mg, 마그네슘 315mg, 아연 8.5mg, 요오드 150ug, 구리 0.8mg, 망간 3mg, 셀레늄 55ug, 몰리브덴 25ug, 크롬 30ug

## ⚠️ 검토 대원칙: 77대 품질관리 지침

🔥 **Rule 1. [원산지 3순위 산정 제외 및 임의 분류(환각) 금지]**
   - 정제수(물), 주정, 당류, 그리고 모든 식품첨가물은 배합비율이 아무리 높아도 원산지 표시 대상 3순위 산정에서 100% 제외됩니다.
   - **[🚨 AI 임의 분류 금지]**: '나한과추출분말', '진득찰추출분말' 등 추출물이나 분말 류를 이름만 보고 임의로 '식품첨가물'로 오판하지 마십시오! 

✅ **Rule 2. 향료 및 첨가물 명칭 유연화 (통합 표기 합법성)**
   - 배합비 서류에 구체적인 개별 향료명이 명시되어 있더라도, 시안 원재료명에 단순히 '향료'라고 묶어서 표기한 것은 완벽 적합입니다.

🔥 **Rule 3. [주표시면 vs 영양성분표 수치 100% 일치 및 총열량/식이섬유 열량 계산 강제 룰]**
   - 주표시면(앞면)에 특정 영양소 함량(예: 칼슘 200mg)이 강조되어 있다면, 뒷면 영양성분표의 수치와 단 1의 오차도 없이 100% 일치해야 합니다.
   - 박스/세트 포장의 주표시면에는 반드시 '총 내용량'과 '총 열량(kcal)'이 모두 기재되어야 합니다.

✅ **Rule 4. 영양성분 실측값 허용**
   - 식약처 허용 오차 범위를 고려하여 시험성적서 실측값을 그대로 반영한 경우 합법(적합)입니다.

🔥 **Rule 5. [복합원재료 5% 룰 및 첨가물 생략 허용]**
   - 배합비 5% 미만인 복합원재료는 하위 성분을 전개할 의무가 없습니다.

✅ **Rule 6. 당류/시럽 필터링**
   - 원재료에 당류가 있음에도 당류가 0g으로 표기되었다면 실제 함량이 0.5g 미만인지 검증하십시오.

🔥 **Rule 7. [당알코올 주의문구 개정 (10% 컷오프 룰)]**
   - 자일리톨, 에리스리톨 등 당알코올류가 최종 제품에 **10% 미만**으로 사용된 경우 주의문구 생략은 100% 합법(✅)입니다.

✅ **Rule 8. 수입 원료 원산지 유연성 보호**
   - 수입 원료의 특정 국가명 대신 '외국산' 표기는 적합합니다.

✅ **Rule 9. 식품유형 vs 제품명 구분**
   - 소비자가 제품명과 식품유형을 혼동하지 않도록 명확히 구분되어야 합니다.

✅ **Rule 10. 영양성분 강조표시 (액체/고체 분리)**
   - 제형에 따라 100g 또는 100mL 당 기준을 분리하여 심사하십시오.

🔥 **Rule 11. [영양정보 단방향 허용오차 법칙 (수학적 역산 절대 금지!)]**
   - **[하한선 그룹(비타민,미네랄,단백질 등)]**: `(용량 환산 실측값) >= (시안 표시량 × 0.8)` 이면 무조건 합법(✅). 거꾸로 나누어 부적합 내는 환각 금지.
   - **[상한선 그룹(열량,나트륨,당류 등)]**: `(용량 환산 실측값) <= (시안 표시량 × 1.2)` 이면 합법(✅).

✅ **Rule 12. [원재료명 3단 교차 검증 및 임의 추론 금지]**
   - 배합비 서류 없이 레시피를 상상하지 마십시오.

🔥 **Rule 13. [알레르기 정밀 추적 및 위치 표기 절대 규칙]**
   - 알레르기 정보는 바탕색과 구분되는 '별도 란(박스)'에 한 번만 기재되어 있으면 100% 합법입니다.

🔥 **Rule 14. [첨가물 표 4, 표 5, 표 6 교차 검증 및 용도명 완벽 스나이퍼]**
   - 표 4: 명칭+용도명 병기 의무.
   - 표 5: 간략명 표기 허용 (용도명 대체 금지).
   - 표 6: 유화제, 산도조절제 등은 용도명만 적어도 합법(✅).

✅ **Rule 15. [기능성 오인 문구 스캔]**
   - 건강기능식품 오인 문구를 적발하십시오.

✅ **Rule 16. [원산지 100% 단일 원료 표기 룰]**
   - 단일 국가 100% 수입 원료만 '국가명 100%' 강조 가능.

✅ **Rule 17. ['無첨가' 마케팅 검증]**
   - 금지된 첨가물을 배제했다고 강조한 경우 부적합(🚨).

✅ **Rule 18. [타겟 오인 명칭 금지]**
   - 일반 식품에 영유아 타겟 명칭 사용 적발.

✅ **Rule 19. ['무당(Zero)' vs '무가당' 분리 검증]**
   - 무당은 당류 0.5g 미만, 무가당은 인위적 당류 첨가 없을 때.

🔥 **Rule 20. [포장재질 표시]**
   - 종이나 유리는 텍스트 재질 표시 의무가 없으므로 생략해도 합법입니다.

🔥 **Rule 21. [영양강조표시 '고/풍부' 4대 조건 교차 연산 룰]**
   - '고/풍부' 강조 시 100g당, 100mL당, 100kcal당, 1회섭취량당 4조건 중 하나라도 충족해야 합법.

✅ **Rule 22. [다국어 폰트 크기 예외]**
   - 외국어는 한글보다 작거나 같아야 합니다. (상표 로고 예외)

🔥 **Rule 23. [식약처 영양성분 '0' 표시 예외 규정]**
   - 트랜스지방 0.2g 미만은 무조건 "0g", 포화지방 0.5g 미만은 "0g" 표시 시 적합.

🔥 **Rule 24. [당류 강조표시 연계 의무 표기 룰]**
   - 무당/저당 등 강조 시 열량 병기 의무, 감미료 함유 문구 기재 여부 스캔.

✅ **Rule 25. [다중 포장 분리 검증]**
   - 1단위 포장과 총 내용량 수치를 분리하여 검증.

✅ **Rule 26. [고체/액체 단위 구분]**
   - 고체는 중량(g), 액체는 용량(mL).

✅ **Rule 27. [제한 영양성분 100kcal 적용 금지]**
   - 열량, 당류 등은 100kcal 당 조건을 적용 금지.

🔥 **Rule 28. [원산지 3순위 완벽 필터링 및 강제 재정렬 룰]**
   - 정제수, 당류, 첨가물은 물론이고 **유산균, 효모, 미생물류 역시 원산지 산정에서 100% 강제 삭제**하십시오.
   - 남은 '진짜 농수산물' 원료만 모아 1, 2, 3순위를 재정렬하십시오. 4순위 이하 첨가물의 원산지가 시안에 없다고 부적합 처리하지 마십시오.

🔥 **Rule 29. [국내 가공 복합원재료 원산지 역추적 합법성]**
   - 국내 가공 복합원재료라도 하위 원물의 원산지를 역추적해 표기했다면 합법(✅)입니다.

🔥 **Rule 30. [알레르기 오판 차단 룰]**
   - 호밀, 귀리, 보리는 '밀' 알레르기 대상이 절대 아닙니다.

✅ **Rule 31. [다중 성적서 데이터 병합]**
   - 여러 시험성적서를 누락 없이 병합 대조.

✅ **Rule 32. [단순 역산에 의한 부적합 판정 금지]**
   - 반올림 오차에 의한 단순 계산 차이는 합법(✅).

✅ **Rule 33. [데이터 출처 분리 명시]**
   - 서류 수치와 시안 수치를 명확히 구분.

✅ **Rule 34. [2% 미만 원재료 순서 유연성]**
   - 투입량 2% 미만 원료는 순서가 달라도 합법.

🔥 **Rule 35. [🌟 범용 간략명/동의어 허용 및 N종 묶음 절대 금지]**
   - 식약처 공식 이명(구연산나트륨=구연산삼나트륨)이나 표 5 간략명(비타민C) 표기는 100% 합법입니다.
   - 내부 코드 생략 완벽 합법.
   - 단, 일반 원료를 숨기기 위해 '비타민 3종' 등으로 숫자로 묶는 것은 🚨부적합 처리.

✅ **Rule 36. [주의사항 오탈자 스캔]**
   - 오탈자 정밀 검수.

✅ **Rule 37. [법적 서류 우선 원칙]**
   - Rule 35(간략명) 예외를 항상 먼저 고려.

🔥 **Rule 38. [알레르기 교차오염 완벽 검증 (수학적 차집합 강제)]**
   - ⭐ **[강제 수식]**: 무조건 화면에 `[교차오염 정답지] = [공장 취급 마스터] - [직접 투입 알레르기 물질]` 수식을 도출하여 증명하십시오. 

🔥 **Rule 39. [동명 원료 및 식품유형 종속성 분리 룰 (병합 절대 금지)]**
   - 서류상 명칭이 같아도 [식품유형]이 다르면(향료 vs 혼합제제) 병합하지 마십시오. 분리 표기가 합법.

🔥 **Rule 40. [열량 표기 및 반올림 원칙]**
   - 세트 총 열량은 실측 소수점을 합산하여 5kcal 단위로 반올림.

🔥 **Rule 41. [% 영양소 기준치 정밀 검증]**
   - 열량(kcal)과 트랜스지방은 %를 표기하지 않습니다.

✅ **Rule 42. [완제품 서류 혼동 방지]**
   - 최종 완제품 기준 성적서 데이터만 사용.

✅ **Rule 43. [시각적 한계 명시]**
   - 육안 판독 어려우면 임의 판정 금지.

🔥 **Rule 44. [혼합제제 전개 및 해체 병합 완벽 허용 룰]**
   - 혼합제제는 괄호를 깨고 내림차순으로 흩어지게 적든 모두 완벽한 합법(✅).

✅ **Rule 45. [선택적 누락 허용]**
   - 마케팅적 선택 누락은 지적 금지.

🔥 **Rule 46. [제품명 숫자 강조 시 전개 확인]**
   - 제품명에 숫자 포함 시 하위 내역 스캔.

🔥 **Rule 47. [디자인적/물리적 차이 예외 인정]**
   - 영문 제품명과 뒷면 한글 제품명이 불일치해도 합법(✅).

🔥 **Rule 48. [서류 역할 분리 대조]**
   - 배합비(순서)와 한글라벨(최종 명칭) 분리.

🔥 **Rule 50. [원액/추출물 고형분 의무 표시 강제 룰]**
   - 앞면에 '농축액', '추출물' 함량(%) 강조 시 반드시 '고형분 함량(%)' 병기 강제!

🔥 **Rule 51. [고형분(Brix) 보수적 표기 예외]**
   - 시안 수치가 서류 스펙보다 낮으면 보수 표기이므로 합법(✅).

🔥 **Rule 52. [영양성분 단순 명칭 강조 컷오프 완벽 검증 룰 (4가지 조건 수학 증명 강제)]**
   - '고/풍부/무/저' 등 강조 시 아래 4조건(100g, 100mL, 100kcal, 1회섭취량) 중 **단 하나라도 충족**하면 합법(✅).
   - ⭐ **[부적합 시 수학적 증명 족쇄]**: 1회 제공량 하나만 대충 계산하고 🚨부적합을 때리지 마십시오. 4가지 조건의 수식을 모조리 텍스트로 나열하고 증명해야 합니다.

🔥 **Rule 53. [제품명 연동 원료 함량 및 원산지 강제 추적 룰]**
   - 제품명에 농수산물이 쓰이면 정보표시면에 원물 원산지 기재.

🔥 **Rule 54. [복수 원산지 혼합 비율 생략 합법성]**
   - 단일 원료 2개국 병기 시 비율 생략 확인 요망.

🔥 **Rule 55. [영양성분 소수점 및 반올림 강제 규정]**
   - 포화지방 5g 이상은 소수점 없이 정수로 표시.

🔥 **Rule 56. [HACCP 인증 마크 공식 텍스트 검증]**
   - "안전관리인증", "식품안전관리인증" 합법. 기타 명칭은 부적합.

🔥 **Rule 57. [세트포장 수량 강제 룰]**
   - 박스 번호에 "수량(예: X 16입)"이 기재되어야 합법(✅).

🔥 **Rule 58. [함량 생략 합법성]**
   - 앞면에 함량(%)이 적혀있다면 뒷면 원재료명에는 생략해도 합법(✅).

🔥 **Rule 59. [CS 및 1399 신고 의무표시 3종 강제 스캔 룰 (Global Scan)]**
   - 상담번호, 반품처, "국번없이 1399" 문구가 현재 탭(예: 측면)의 이미지에 없더라도, **전체 텍스트(주표시면, 정보표시면 등) 어디에든 하나라도 존재하면 무조건 합법(✅) 처리하십시오.** 🔥 **Rule 60. [복합원재료 원물 함량 기재 면제 룰]**
   - 농축액 괄호 안에 '고형분(%)'이 명시되어 있다면 배합함량 추가 기재를 강요하지 마십시오. 합법(✅).

🔥 **Rule 61. [국산 가공 예외 룰]**
   - 국내 가공 복합원재료는 괄호 없이 곧바로 (국산) 표기 시 합법.

🔥 **Rule 62. [축산물 보관상태 의무 표시]**
   - 축산물 냉장/냉동 제품은 앞면에 상태 명시.

🔥 **Rule 63. [미드팩 질소충전 확인]**
   - 190mL 팩은 "질소충전" 문구 기재 확인.

🔥 **Rule 64. [원물 기만표시 스나이퍼]**
   - 앞면 강조 비율이 원물이 아닌 추출액 비율이면 🚨부적합(기만).

🔥 **Rule 65. [내부 식별 코드 생략 합법성]**
   - 원료명 뒤의 `-2` 등 내부 코드는 생략해도 100% 합법.

🔥 **Rule 68. [다포장/세트포장 낱개 영양표시 복붙 스나이퍼]**
   - 박스 시안 내용량이 낱팩 용량만 적혀있거나 영양표시가 '1개당' 기준이 아니면 복붙 에러(🚨).

🔥 **Rule 70. [내/외포장 원재료명 100% 일치 강제 범용 스나이퍼]**
   - 내포장(팩)과 외포장(박스) 텍스트 대조 시 다르면 🚨부적합 처리.

🔥 **Rule 71. [강조 폰트 크기 규정 (육안 검수 알림)]**
   - 원료 함량 14pt, 셀링문구 12pt ⚠️육안 확인 알림.

🔥 **Rule 72. ['조리예/이미지 사진' 필수 텍스트 점검]**
   - 연출 사진이 있으면 해당 텍스트 스캔.

🔥 **Rule 73. [세부 재질 스나이퍼]**
   - 뚜껑 있는 종이팩은 `뚜껑: HDPE`, `개봉부: PP` 세부 재질 확인.

🔥 **Rule 74. [액상 음료 개봉 후 주의문구 강제 스캔]**
   - 과채음료, 우유 등은 "개봉 후 냉장보관하거나 빨리 드시기 바랍니다" 스캔.

🔥 **Rule 75. [CS 클레임 방어용 필수 주의문구 세트]**
   - 침전물, 용기 팽창 등 CS 방어 문구 스캔.

🔥 **Rule 76. [OEM 업소명 타이틀 강제 스캔 (유통전문판매원)]**
   - 제조원이 타사면 자사 상호명 앞에 반드시 **'유통전문판매원:'** 또는 **'판매원:'** 등의 타이틀이 기재되어야 합니다. 

🔥 **Rule 77. [범용 식품유형 필수 주의문구 강제 스캔]**
   - 1) **냉동식품:** "이미 냉동되었으니 해동 후 다시 냉동하지 마십시오."
   - 2) **고카페인:** "어린이, 임산부 및 카페인 민감자는 섭취에 주의..."
   - 3) **고체 젤리/과채류:** "섭취 시 목에 걸릴 우려가 있으니 주의..." (🚨 액체류는 목걸림 문구 지적 불가)
   - 4) **아스파탐 첨가:** "페닐알라닌 함유"

🔥 **Rule 80. [세트포장(박스) 영양정보 레이아웃 강제 (V310.0 신설)]**
   - 세트 포장(박스) 시안일 경우, 영양정보표 상단에는 반드시 **`총 내용량 OOO mL (OOO mL X O개입)`** 및 **`1개(OOO mL)당`** 이라는 포맷이 정확히 존재해야 합법(✅)입니다.

🔥 **Rule 81. [영양표시 하단 면책 문구 토시 대조 (V310.0 신설)]**
   - 영양표시 하단에는 **`"1일 영양성분 기준치에 대한 비율(%)은 2,000 kcal 기준이므로 개인의 필요 열량에 따라 다를 수 있습니다."`** 라는 문구가 토씨 하나 틀리지 않고 100% 일치하게 기재되어야 합법(✅)입니다.

🔥 **Rule 82. [영양소 법정 단위 엄격 검증 (V310.0 신설)]**
   - 비타민A: `μg RE` / 비타민D, B12, 비오틴, 엽산, 요오드, 셀레늄, 몰리브덴, 크롬: `μg`
   - 비타민E: `mg α-TE`
   - 비타민C, B1, B2, B6, 철, 아연, 구리, 망간: `mg`
   - 대소문자나 특수기호가 다르면 무조건 🚨부적합입니다. 비타민 명칭에 숫자가 잘 적혀있는지도 봅니다.
"""

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

COMMON_RULES = [36, 37, 42, 43, 45, 47, 70]
RULES_TAB1 = "[탭1 주표시면 관련 핵심 룰]\n" + get_sliced_rules([3, 9, 10, 15, 16, 17, 18, 19, 21, 24, 28, 40, 46, 47, 50, 51, 52, 53, 57, 58, 59, 60, 62, 63, 64, 68, 71, 72] + COMMON_RULES)
RULES_TAB2 = "[탭2 정보표시면/원재료명 관련 핵심 룰]\n" + get_sliced_rules([1, 2, 5, 6, 7, 8, 12, 13, 14, 20, 25, 28, 29, 30, 34, 35, 38, 39, 44, 48, 52, 54, 57, 58, 59, 60, 61, 65, 68, 70, 73, 74, 75, 76, 77] + COMMON_RULES)
RULES_TAB3 = "[탭3 영양성분표 관련 핵심 룰]\n" + get_sliced_rules([3, 4, 6, 10, 11, 21, 23, 25, 26, 27, 31, 32, 33, 40, 41, 52, 55, 59, 68, 80, 81, 82] + COMMON_RULES)
RULES_TAB4 = "[탭4 기타면/측면 관련 핵심 룰]\n" + get_sliced_rules([7, 15, 17, 18, 20, 22, 24, 38, 52, 56, 57, 59, 63, 64, 73, 74, 75, 77] + COMMON_RULES)

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
    st.title("🏭 식품 표시사항 정밀 검토 시스템 (V310.0 - 실무 최적화 마스터)")
    st.markdown("<hr class='hide-on-print'>", unsafe_allow_html=True)

    with st.sidebar:
        st.header("📄 검토 설정 및 파일 업로드")
        
        with st.expander("⚙️ 고급 설정 (수동 텍스트 입력)", expanded=False):
            st.info("💡 텍스트가 너무 빽빽해서 AI가 글자를 빼먹는다면, 디자이너 원본 텍스트를 복붙해 주세요.")
            st.session_state["manual_target"] = st.text_area("📦 타겟(박스) 원재료명 직접 입력", height=100)
            st.session_state["manual_compare"] = st.text_area("🧃 비교용(팩) 원재료명 직접 입력", height=100)

        st.markdown("#### 📌 기본 검토 조건")
        product_type = st.radio("1. 식품유형", ("일반식품 (두유류 등 - 냉장표시 의무 없음)", "특수의료용도식품 / 환자식", "냉장 축산물 (우유/가공유 등)"))
        inspection_mode = st.radio("2. 검토 모드", ("단품(팩/단일포장) 기본 검토", "선물세트 박스(외포장) 교차 검토"))
        doc_type = st.radio("3. 증빙 서류 형태", ("통합 엑셀/PDF 자료 (마스터표 생략)", "개별 원료 한글라벨 무더기 (마스터표 생성)"))
        
        st.markdown("---")
        st.markdown("#### 🏭 공장 알레르기 마스터 설정")
        factory_allergens = st.text_area("우리 공장 취급 알레르기 물질 (쉼표로 구분)", "대두, 땅콩, 호두, 잣, 우유, 밀, 복숭아, 토마토, 메밀, 아황산류, 알류")
        
        st.markdown("---")
        if inspection_mode == "선물세트 박스(외포장) 교차 검토":
            st.markdown("#### 📦 [타겟] 박스(외포장) 시안")
            img_main = st.file_uploader("1️⃣ 박스 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 박스 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 박스 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 박스 기타면/측면", type=["jpg", "png", "jpeg"])
            st.markdown("#### 🔍 [비교용] 팩(내포장) 시안")
            box_main = st.file_uploader("🔍 팩(내포장) 주표시면", type=["jpg", "png", "jpeg"])
            box_info = st.file_uploader("🔍 팩(내포장) 정보표시면", type=["jpg", "png", "jpeg"])
            box_nutri = st.file_uploader("🔍 팩(내포장) 영양성분표", type=["jpg", "png", "jpeg"])
            box_extra = st.file_uploader("🔍 팩(내포장) 기타면/측면", type=["jpg", "png", "jpeg"])
        else:
            st.markdown("#### 🔹 시안 업로드")
            img_main = st.file_uploader("1️⃣ 시안 주표시면", type=["jpg", "png", "jpeg"])
            img_info = st.file_uploader("2️⃣ 시안 정보표시면", type=["jpg", "png", "jpeg"])
            img_nutri = st.file_uploader("3️⃣ 시안 영양성분표", type=["jpg", "png", "jpeg"])
            img_extra = st.file_uploader("4️⃣ 시안 기타면/측면", type=["jpg", "png", "jpeg"])
            box_main = box_info = box_nutri = box_extra = None

        st.markdown("---")
        st.markdown("#### 📑 추가 증빙 서류 (선택사항)")
        report_docs = st.file_uploader("1️⃣ 시험성적서 (영양성분 검증용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        label_docs = st.file_uploader("2️⃣ 원료 한글라벨/스펙 (원재료 대조용)", type=["pdf", "jpg", "png"], accept_multiple_files=True)
        recipe_docs = st.file_uploader("3️⃣ 배합비/레시피 데이터", type=["pdf", "jpg", "png"], accept_multiple_files=True)

        def get_uploaded_content():
            user_content = []
            local_paths = []
            DEFAULT_DOCS_DIR = "./default_docs"

            def robust_upload(file_path, label):
                user_content.append(f"### [{label}] ###")
                
                # ⭐ [Vision API 100% 강제 가동]
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
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

            if os.path.exists(DEFAULT_DOCS_DIR):
                auto_files = glob.glob(os.path.join(DEFAULT_DOCS_DIR, "*.pdf"))
                for file_path in auto_files:
                    robust_upload(file_path, f"자동로드_기본서류: {os.path.basename(file_path)}")

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
        if st.button("🚀 전체 시스템 파일 연동 (Vision API 자동 가동)"):
            with st.spinner("파일을 AI 시스템에 연동 중입니다..."):
                content, paths = get_uploaded_content()
                st.session_state["uploaded_content"] = content
                st.session_state["local_file_paths"] = paths
                st.success("✅ 파일 등록 완료! 이제 우측 탭에서 검토를 시작하세요.")

    # ==========================================
    # 🔥 3-Pass 파이프라인
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
            extracted_results = []
            for i, mission in enumerate(extract_missions_list):
                st.toast(f"🕵️‍♂️ 분할 미션 {i+1}/{len(extract_missions_list)} 추출 중...")
                pass1_prompt = f"""
[PASS 1 - 텍스트 단일 추출 미션 (Divide & Conquer)]
⭐ 이 단계에서는 판정을 금지합니다. 오직 '아래의 특정 미션'에만 시야를 좁혀 텍스트를 추출하십시오.
🔥 [절대 금지사항]: "등", "등 다수", "중략" 이라는 표현을 절대 쓰지 마십시오. 리스트에 항목이 100개면 100개를 모두 타이핑해야 합니다.

[사용자 수동 입력 원재료명 데이터]
- 타겟(박스): {manual_target if manual_target else '없음'}
- 비교용(팩): {manual_compare if manual_compare else '없음'}

🎯 [현재 타겟 미션]:
{mission}
"""
                try:
                    pass1_response = model.generate_content(content + [pass1_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                    extracted_results.append(f"=== [미션 {i+1} 결과] ===\n" + pass1_response.text)
                except Exception as e:
                    return f"🚨 Pass 1 (단일 추출 {i+1}) 오류 발생: {e}"
            
            extracted_text_combined = "\n\n".join(extracted_results)

            pass15_prompt = f"""
[PASS 1.5 - 추출 텍스트 종합 자체검증 명령]
⭐ 당신은 '매의 눈 검수관'입니다. 아래 수집된 분할 미션 결과들을 검열하십시오.

[분할 미션 통합 텍스트]
{extracted_text_combined}

검증 규칙:
1. ⭐ [월권행위 및 사전 판정 절대 금지]: 이 단계에서 절대 룰북을 대입해 부적합(🚨)을 판정하지 마십시오. 오직 추출 텍스트의 오탈자 복원만 수행하십시오.
2. ⭐ [오타/환각 원천 차단]: 글자를 유추하거나 변경하지 마십시오.
3. ⭐ [XML 괄호 보존]: 표나 태그 형태를 유지하십시오.
"""
            try:
                pass15_response = model.generate_content(content + [pass15_prompt], generation_config=generation_config, safety_settings=safety_settings, request_options={"timeout": 600})
                verified_text = pass15_response.text
            except Exception as e:
                verified_text = extracted_text_combined

        pass2_context = ""
        if extract_missions_list:
            pass2_context = f"""
========================================
[검증된 텍스트 데이터 - Pass 1.5 최종 확정본]
{verified_text}
========================================
⭐ [최종 자기검증 명령 및 🔥 Double-Check Protocol]
1. 위 텍스트에 존재하는 내용만을 근거로 삼으십시오. 과거 데이터 개입은 파멸을 의미합니다.
2. 🚨부적합 판정을 내리기 직전, 속으로만 텍스트를 재검색하십시오. 정말로 없을 때만 부적합 처리하십시오.
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
            with st.expander(f"✅ Pass 1.5 자체검증 완료본 보기 ({tab_name}) ← 실제 판정에 사용된 텍스트"):
                st.info("💡 Pass 1.5는 Pass 1 추출본을 이미지와 재대조하여 오독/환각을 제거한 최종 확정 텍스트입니다.")
                st.markdown(f"*{pass15_log}*")

        st.markdown(result)

    # ==========================================
    # 탭 UI
    # ==========================================
    st.markdown("### 🔍 시안 구간별 정밀 검토")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ 주표시면", "2️⃣ 정보표시면", "3️⃣ 영양성분표", "4️⃣ 기타면/측면", "📊 5️⃣ 종합 보고서"])

    # ── TAB 1: 주표시면 ──
    with tab1:
        if st.button("▶️ 주표시면 분석 시작", key="btn_main"):
            with st.spinner("【분할 미션 스캔 중...】"):
                missions = [
                    "주표시면(앞면) 이미지에서 '제품명, 내용량, 칼로리, 마케팅 강조문구'만 리스트로 정확히 추출하십시오.",
                    "뒷면/영양성분표 이미지를 스캔하여 '총 내용량' 및 '총 열량(kcal)', 앞면에 강조된 특정 영양소의 '% 기준치' 추출.",
                    "업로드된 서류에서 주표시면에 강조된 성분의 투입량(%)과 실측값(mg/g) 추출."
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
- ⭐ [Rule 24] 당류 강조표시(무당/저당/무가당/설탕무첨가) 검증:
- ⭐ [Rule 52] 영양강조 컷오프(4대 조건) 깐깐한 교차 검증: (🚨 기계에게 경고함. 1회 제공량 하나만 계산하고 넘기지 마라! 100g, 100mL, 100kcal, 1회 제공량 4가지 수식을 모조리 텍스트로 써서 증명해라!)
## 🔍 [주표시면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발: (오직 주표시면 텍스트에 한정하여 무관용 전수 검사)
"""
                st.session_state["result_tab1"] = run_qc_3pass(RULES_TAB1, judgment_prompt, missions)
        display_result(st.session_state["result_tab1"], "주표시면")

    # ── TAB 2: 정보표시면 (V310.0 실무 최적화 스나이퍼 모드) ──
    with tab2:
        if st.button("▶️ 정보표시면 원재료 기계적 1:1 맵핑 시작", key="btn_info"):
            with st.spinner("【분할 미션 스캔 중... (시간이 다소 소요됩니다)】"):
                missions = [
                    "오직 '타겟(박스) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "오직 '비교용(팩) 시안'의 원재료명 리스트만 100% 나열하십시오. 중략 절대 금지.",
                    "정보표시면의 '알레르기 유발물질', '교차오염 주의문구', 'CS 주의문구' 추출.",
                    "정보표시면의 행정 정보(제조원, 유통전문판매원, 포장재질 등) 추출.",
                    "증빙 서류의 모든 원료명, 하위 성분, 원산지를 표로 추출하되, 반드시 원료명 앞에 [식품유형] 꼬리표를 강제로 붙이십시오! (예: [향료] 복숭아향)",
                    "배합비 서류가 있다면 원료명과 배합비율(%) 추출."
                ]
                
                base_tab2_warning = """
⭐ [1:1 대조 예외 절대 원칙 (Rule 2, 34, 35, 65 우선 적용)] ⭐
🔥 [시스템 절대 족쇄: 영양정보 연산 개입 절대 금지] 🔥
이 탭(정보표시면)에서는 나트륨, 당류 등 영양수치를 검토하는 월권행위를 절대 금지합니다.
"""
                
                if inspection_mode == "단품(팩/단일포장) 기본 검토":
                    common_tab2_prompts = """
## 1️⃣ [마스터 서류 vs 시안 법적 대조 매트릭스]
⭐ [강제 지시 1: 시안 기준 Left Join]: 표의 뼈대는 무조건 '시안'에 적힌 원재료명 순서 그대로 100% 나열하십시오. 서류가 없다고 행을 삭제하면 시스템 파괴로 간주합니다.
⭐ [원산지 순위 도출 규칙]: Rule 28에 따라 물/첨가물/미생물 소거 후 1,2,3순위를 도출하십시오.
| 시안 표기 원재료명 (100% 나열) | 매칭된 서류 원료명 (없으면 '제출 안 됨') | 대조 검증 결과 (원산지 순위 포함) | 최종 판정 |
|---|---|---|---|

### 🚨 [서류 기준 최종 누락 스나이퍼 검증 (Anti-Join)]
⭐ [강제 지시 2: 누락 역추적]: 서류(한글라벨, 배합비)에는 명백히 존재하지만, 디자이너가 시안에 아예 빼먹어서 위 표(1번 매트릭스)에 등장조차 하지 않은 원료가 있는지 샅샅이 뒤져 적발하십시오. 
- (단, Rule 5에 따른 5% 미만 하위성분 생략, 단순 부형제 생략은 합법이므로 지적 제외)
- 적발 양식: "🚨 [누락]: 서류의 'OOO' 원료가 시안에서 완전히 누락되었습니다."
- 이상 없을 시: "✅ 서류상 누락된 원료 없음."

## ⚖️ 2️⃣ [배합비 기반 2% 룰 및 전개 순서 정밀 검증 (Rule 34)]
## 3️⃣ [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38 적용)]
⭐ [강제 지시]: 반드시 아래의 '수학적 차집합 수식' 풀이 과정을 텍스트로 써서 증명하십시오.
- [공장 마스터 목록]: 
- [직접 투입된 알레르기]: 
- [도출된 교차오염 정답지]: 
- [시안 표기 문구]: 
- [최종 판정 및 사유]: 
## 🏛️ 4️⃣ [행정 정보 교차 검증]
- ⭐ [Rule 76] 유통전문판매원/판매원 타이틀 강제 확인:
## 🔍 [정보표시면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발: (오직 정보표시면 텍스트에 한정하여 무관용 전수 검사.)
"""
                else: # 선물세트 박스 모드
                    common_tab2_prompts = """
## 1️⃣ [통합 마스터 대조 매트릭스]
⭐ [강제 지시 1: 박스 기준 Left Join]: 표의 뼈대는 무조건 '📦 타겟(박스) 시안'에 적힌 원재료명 순서 그대로 100% 나열하십시오. 서류가 없다고 행을 삭제하면 시스템 파괴로 간주합니다.
⭐ [원산지 순위 도출 규칙]: Rule 28에 따라 물/첨가물/미생물 소거 후 1,2,3순위를 도출하십시오.
| 📦 타겟(박스) 시안 표기 (100% 나열) | 🧃 비교용(팩) 시안 표기 | 매칭된 증빙 서류 (없으면 '제출 안 됨') | 대조 검증 결과 및 사유 (원산지 순위, 일치 여부 포함) | 최종 판정 |
|---|---|---|---|---|

### 🚨 [서류 기준 최종 누락 스나이퍼 검증 (Anti-Join)]
⭐ [강제 지시 2: 누락 역추적]: 서류(한글라벨, 배합비)에는 명백히 존재하지만, 디자이너가 시안에 아예 빼먹어서 위 표(1번 매트릭스)에 등장조차 하지 않은 원료가 있는지 샅샅이 뒤져 적발하십시오. 
- (단, Rule 5에 따른 5% 미만 하위성분 생략, 단순 부형제 생략은 합법이므로 지적 제외)
- 적발 양식: "🚨 [누락]: 서류의 'OOO' 원료가 시안에서 완전히 누락되었습니다."
- 이상 없을 시: "✅ 서류상 누락된 원료 없음."

## ⚖️ 2️⃣ [배합비 기반 2% 룰 및 전개 순서 정밀 검증 (Rule 34)]
## 3️⃣ [알레르기 및 교차오염 수학적 정밀 검증 (Rule 38 적용)]
⭐ [강제 지시]: 반드시 아래의 '수학적 차집합 수식' 풀이 과정을 텍스트로 써서 증명하십시오.
- [공장 마스터 목록]: 
- [직접 투입된 알레르기]: 
- [도출된 교차오염 정답지]: 
- [시안 표기 문구]: 
- [최종 판정 및 사유]: 
## 🏛️ 4️⃣ [행정 정보 교차 검증]
- ⭐ [Rule 76] 유통전문판매원/판매원 타이틀 강제 확인:
## 🔍 [정보표시면 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발: (오직 정보표시면 텍스트에 한정하여 무관용 전수 검사.)
"""
                judgment_prompt = base_tab2_warning + common_tab2_prompts

                st.session_state["result_tab2"] = run_qc_3pass(RULES_TAB2, judgment_prompt, missions)
        display_result(st.session_state["result_tab2"], "정보표시면")

    # ── TAB 3: 영양성분표 ──
    with tab3:
        if st.button("▶️ 영양성분표 오차 정밀 연산 시작", key="btn_nutri"):
            with st.spinner("【분할 미션 스캔 중... (잠시만 기다려주세요)】"):
                missions = [
                    "타겟(박스) 시안의 영양정보표 내부 수치와 표 바깥의 총 내용량, 칼로리, '1일 영양성분 기준치' 문구 전부 추출.",
                    "비교용(팩) 시안이 있다면 영양정보표 내부 수치와 바깥 문구 전부 추출.",
                    "시험성적서 서류에서 각 영양성분의 실측값 데이터 추출."
                ]
                
                if inspection_mode == "단품(팩/단일포장) 기본 검토":
                    judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 % 기준치 확인]
- 결론: (✅ 적합 또는 🚨 부적합)
⭐ [계산 규칙]: 성적서 실측값을 시안의 내용량에 맞게 환산한 뒤 비교하십시오. 부적합 판정 시 부등호 수식 기재 필수!
| 영양성분 | 성적서 환산값(A) | 시안 표시량(B) | 법적 기준선 (B의 80% 또는 120%) | 🎯 % 계산 검증 | 판정 및 상세 사유 (수식 증명 필수) |
|---|---|---|---|---|---|

## 🔍 [영양성분표 치명적 레이아웃 및 뼈대 스나이퍼]
- ⭐ [Rule 80] 박스 포장 상단 레이아웃 확인 (`총 내용량... (X개입)` 및 `1개당` 기재 여부): 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
## 🔍 [영양성분표 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                else:
                    judgment_prompt = """
## 4️⃣ [영양표시 오차 검증 및 팩/박스 교차 대조]
- 결론: (✅ 적합 또는 🚨 부적합)
⭐ [계산 규칙]: 성적서 실측값을 시안의 내용량에 맞게 환산한 뒤 비교하십시오. 부적합 판정 시 부등호 수식 기재 필수!
| 영양성분 | 성적서 환산값(A) | 비교용(팩) 시안(B) | 타겟(박스) 시안(C) | 팩/박스 일치 여부 | 법적 기준선 (B의 80% 또는 120%) | 🎯 % 계산 검증 | 판정 및 상세 사유 (수식 증명 필수) |
|---|---|---|---|---|---|---|---|

## 🔍 [영양성분표 치명적 레이아웃 및 뼈대 스나이퍼]
- ⭐ [Rule 80] 박스 포장 상단 레이아웃 확인 (`총 내용량... (X개입)` 및 `1개당` 기재 여부): 
- ⭐ [Rule 81] 하단 2000kcal 면책 문구 토씨 100% 대조: 
- ⭐ [Rule 82] 영양소 법정 특수 단위/아래첨자 정밀 검증 (μg, α-TE 등): 
- ⭐ [Rule 68] 영양성분표 복붙 스나이퍼: 
## 🔍 [영양성분표 전용: 오탈자 검증]
- ⭐ 띄어쓰기 및 오탈자 적발:
"""
                st.session_state["result_tab3"] = run_qc_3pass(RULES_TAB3, judgment_prompt, missions)
        display_result(st.session_state["result_tab3"], "영양성분표")

    # ── TAB 4: 기타면/측면 ──
    with tab4:
        if st.button("▶️ 기타면/측면 분석 시작", key="btn_extra"):
            with st.spinner("【분할 미션 스캔 중... (잠시만 기다려주세요)】"):
                missions = [
                    "전 구역 이미지를 스캔하여 필수 의무표시 3종(상담번호, 교환처, 1399 문구)과 HACCP 인증 마크 추출.",
                    "알레르기 직접 함유 표시(바탕색 별도 박스) 및 분리배출 마크 추출.",
                    "포장재질 표기(세부 재질 포함) 및 CS 방어/기타 주의문구 추출."
                ]
                judgment_prompt = """
## 5️⃣ [기타면/측면 표시사항 및 마케팅 뱃지 (HACCP 포함)]
- ⭐ [Rule 59] CS번호 및 1399 등 의무표시 3종 Global Scan: (현재 측면에 없더라도, 전체 캐시 텍스트를 다 뒤져서 패키지 어디든 있으면 합법 처리하십시오!)
- ⭐ [Rule 38] 알레르기 교차오염 수학적 차집합 검증: (수식 풀이과정 기재 필수)
- ⭐ [Rule 56] HACCP 마크 공식 명칭 적합성:
- ⭐ [Rule 73] 용기 세부 재질 스나이퍼:
- ⭐ [Rule 74] 액상 음료 개봉 후 주의문구:
- ⭐ [Rule 75] CS 클레임 방어용 문구 점검:
- ⭐ [Rule 77] 범용 식품유형 필수 주의문구 점검 (냉동/고카페인/고체 젤리류 등):
- ⭐ [Rule 24, 52] 영양강조 및 당류 컷오프 교차 확인: ('고/무/풍부' 발견 시 반드시 4가지 조건의 수학적 증명을 나열할 것!)
## 🔍 [기타면/측면 전용: 오탈자 검증]
- ⭐ 오탈자 및 띄어쓰기 적발: (오직 기타면/측면 텍스트에 한정하여 무관용 전수 검사 수행.)
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
[지시]: 지금까지 사용자가 각 탭에서 검토한 내용들을 모았습니다. 실무자가 한눈에 보고 패키지를 수정할 수 있도록 종합 결론을 내려주십시오.

[기존 분석 데이터]
{combined_results}

## 📋 [최종 종합 검토 리포트]
- **최종 판정:** (✅ 수정 없이 진행 가능 또는 🚨 즉시 수정 필요)

### 📌 [핵심 지적 사항 및 수정 지시]
(위 분석 데이터에서 '부적합(🚨)' 또는 '확인요망'이 나온 내용들만 뽑아서 번호 순 불릿 포인트로 요약하십시오. 법적 사유가 적혀있다면 그 사유도 반드시 요약하여 포함하십시오.)

### 🔍 [기타 주의사항]
(실무자가 참고해야 할 관련 룰북 코멘트를 덧붙이십시오.)
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
                    <p style='font-size: 12px; color: gray; margin-top: 8px;'>※ 단축키(Ctrl+P 또는 Cmd+P)를 누르셔도 스크롤 잘림 없이 전체 페이지가 인쇄됩니다.</p>
                </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    if check_password():
        main()
