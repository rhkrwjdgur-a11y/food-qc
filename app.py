import streamlit as st
import google.generativeai as genai
from PIL import Image
import glob
import time
import os
import json
import re

# ==========================================
# 🔒 [보안] 시스템 접속 비밀번호 설정
# ==========================================
def check_password():
    """시스템 보안을 위한 비밀번호 체크 함수"""
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
# 🔑 1. API 키 및 모델 초기화
# ==========================================
# Canvas 환경의 API 키를 자동으로 가져오거나 환경 변수에서 참조합니다.
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = os.environ.get("GOOGLE_API_KEY", "")

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.5-flash" 

# ==========================================
# 🧮 [Phase 2] Python 식약처 규정 수학 엔진 (Absolute Rule Engine)
# ==========================================
# 1일 영양성분 기준치 (식약처 고시 기준 완벽 세팅)
DV_DICT = {
    "열량": 2000, "나트륨": 2000, "탄수화물": 324, "당류": 100,
    "지방": 54, "트랜스지방": 0, "포화지방": 15, "콜레스테롤": 300,
    "단백질": 55, "칼슘": 700, "아연": 8.5, "철분": 12,
    "비타민A": 700, "비타민B1": 1.2, "비타민B2": 1.4, "비타민B6": 1.5,
    "비타민B12": 2.4, "비타민C": 100, "비타민D": 10, "비타민E": 11,
    "엽산": 400, "나이아신": 15, "판토텐산": 5, "바이오틴": 30
}

# 120% 미만 그룹 (제한 영양소)
BAD_NUTRIENTS = ["열량", "나트륨", "당류", "지방", "트랜스지방", "포화지방", "콜레스테롤"]

def build_nutrition_table(nutrition_data):
    """AI가 추출한 원시 데이터를 파이썬이 수학적으로 검증하여 9칸 테이블 생성"""
    if not nutrition_data:
        return "🚨 영양성분 데이터를 추출하지 못했습니다.", False

    table_md = "| 영양성분명 | 성적서 실측값 | 환산 실측값 | 시안 표시량 | 법적 허용오차 기준선 (계산식) | 1일 기준치 | 시안 % | % 검증 (계산식) | 판정 및 수정안 |\n"
    table_md += "|---|---|---|---|---|---|---|---|---|\n"
    
    all_pass = True
    for nut, values in nutrition_data.items():
        try:
            # AI가 추출한 문자열 데이터를 숫자로 변환
            report_val = float(str(values.get("report_val", 0)).replace(',', ''))
            converted_val = values.get("converted_val", "-")
            label_val = float(str(values.get("label_val", 0)).replace(',', ''))
            label_pct_str = str(values.get("label_pct", "0%"))
            
            # 1. 허용오차 기준선 계산 (파이썬이 직접 수행)
            if nut in BAD_NUTRIENTS:
                margin = round(label_val * 1.2, 2)
                margin_str = f"{label_val} * 1.2 = {margin} 미만"
                is_pass = report_val <= margin
            else:
                margin = round(label_val * 0.8, 2)
                margin_str = f"{label_val} * 0.8 = {margin} 이상"
                is_pass = report_val >= margin

            # 2. 1일 기준치 % 계산 (환각 차단)
            dv_val = DV_DICT.get(nut)
            calc_pct_str = "-"
            dv_str = f"{dv_val}" if dv_val else "N/A"
            
            if dv_val and dv_val > 0:
                calc_pct = round((label_val / dv_val) * 100)
                calc_pct_str = f"({label_val} / {dv_val}) * 100 = {calc_pct}%"
                
                # 시안의 %와 계산된 % 대조
                label_pct_num = int(re.sub(r'[^0-9]', '', label_pct_str)) if re.sub(r'[^0-9]', '', label_pct_str) else 0
                if calc_pct != label_pct_num:
                    is_pass = False
                    calc_pct_str = f"🚨 수치 오류 (정답: {calc_pct}%)"
            
            # 3. 판정
            judgment = "✅ 적합" if is_pass else "🚨 부적합 (수정요망)"
            if not is_pass: all_pass = False
            
            table_md += f"| **{nut}** | {report_val} | {converted_val} | {label_val} | {margin_str} | {dv_str} | {label_pct_str} | {calc_pct_str} | {judgment} |\n"
        except:
            table_md += f"| **{nut}** | 데이터 오류 | - | - | - | - | - | - | 확인필요 |\n"
            all_pass = False
            
    return table_md, all_pass

# ==========================================
# 👀 [Phase 1] AI Prompt (7단계 포맷용 데이터 스캐너)
# ==========================================
SYSTEM_PROMPT = """당신은 대한민국 최고의 '식품 표시사항 법규 및 품질관리(QC) 데이터 추출 전문가'입니다.
당신은 계산을 하지 않습니다. 대신 아래의 실무 지침에 따라 데이터를 스캔하고 JSON으로만 응답하십시오.

[51대 룰 핵심 지침]
1. [특허/원액]: 제조방법 특허를 '특허물질'로 표기했는지, 혼합물 원료에서 '혼합물' 단어를 누락하여 100% 순수물질처럼 기만했는지 스캔하십시오.
2. [원재료명]: '영양강화제 2종' 등 숫자 묶음 표기는 합법입니다. 향료 뒤 괄호 지적을 금지합니다. 2% 미만 원료 순서 자유를 인정하십시오.
3. [알레르기]: 호밀/보리는 밀 알레르기가 아닙니다. '~함유' 텍스트를 정밀 추적하십시오.
4. [내/외포장]: 내포장(팩)과 외포장(박스)의 소비기한 위치 차이는 합법입니다. 단, 텍스트 란에 '직접 접촉 재질(예: 폴리에틸렌)' 기재 여부를 양쪽 다 확인하십시오.

[출력 형식: 반드시 JSON 백틱 안에 아래 구조로만 응답하십시오]
{
  "step1": {"decision": "✅ 적합/🚨 부적합", "detail": "주표시면/마케팅 뱃지 기만광고 여부 요약"},
  "step2_ingredients": [
    {"no": 1, "draft_ing": "시안명", "label_ing": "서류명", "order_check": "일치/불일치", "decision": "✅ 적합/🚨 부적합"}
  ],
  "step3": {"raw_materials_full": "전체원재료텍스트", "allergens_full": "알레르기문구"},
  "step4_nutrition": {
    "영양소명": {"report_val": 0.0, "converted_val": "환산값", "label_val": 0.0, "label_pct": "0%"}
  },
  "step5": {"decision": "✅/🚨", "detail": "오탈자/의무사항 요약"},
  "step6": {"decision": "✅/🚨", "detail": "내/외포장 일치성 및 접촉면 재질 확인 요약"},
  "step7": {"detail": "종합 수정 지시사항 요약"}
}
"""

def parse_ai_json(text):
    """AI 출력에서 JSON만 추출"""
    try:
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        json_str = match.group(1) if match else text
        return json.loads(json_str)
    except:
        return None

# ==========================================
# 🖥️ [Phase 3] 7단계 리포트 UI 렌더링
# ==========================================
def render_report(data):
    """JSON 데이터를 7단계 정밀 리포트로 출력"""
    st.markdown("## 1️⃣ [주표시면 및 마케팅 뱃지 판별]")
    s1 = data.get("step1", {})
    st.write(f"- 결론: {s1.get('decision', 'N/A')}")
    st.write(f"- 의견: {s1.get('detail', '-')}")

    st.markdown("## 2️⃣ [원재료명 및 원산지 대조]")
    ing_list = data.get("step2_ingredients", [])
    if ing_list:
        table = "| No | 시안 원재료명 (개별 전개) | 한글라벨 매칭 원료 | 배합비 순서 | 판정 |\n|---|---|---|---|---|\n"
        for i in ing_list:
            table += f"| {i.get('no','')} | {i.get('draft_ing','')} | {i.get('label_ing','')} | {i.get('order_check','')} | {i.get('decision','')} |\n"
        st.markdown(table)

    st.markdown("## 3️⃣ [알레르기 교차 검증]")
    s3 = data.get("step3", {})
    raw = s3.get("raw_materials_full", "")
    alg = s3.get("allergens_full", "없음")
    st.write(f"- **추출 문구:** {alg}")
    if "호밀" in raw or "보리" in raw:
        st.success("✅ [Python 검증] 원재료에 호밀/보리가 있으나 식약처 규정에 따라 '밀'이 아니므로 정상입니다.")

    st.markdown("## 4️⃣ [영양표시 및 % 기준치 정밀 검증 (Python Engine)]")
    nut_table, is_pass = build_nutrition_table(data.get("step4_nutrition", {}))
    st.write(f"- **종합 결론:** {'✅ 적합' if is_pass else '🚨 부적합 (표 확인 요망)'}")
    st.markdown(nut_table)

    st.markdown("## 5️⃣ [기타 법적 의무사항]")
    s5 = data.get("step5", {})
    st.write(f"- 결론: {s5.get('decision', 'N/A')}")
    st.write(f"- 의견: {s5.get('detail', '-')}")

    st.markdown("## 6️⃣ [외포장(박스) vs 내포장(팩) 1:1 대조]")
    s6 = data.get("step6", {})
    st.write(f"- 결론: {s6.get('decision', 'N/A')}")
    st.write(f"- 의견: {s6.get('detail', '-')}")

    st.markdown("## 7️⃣ [종합 의견 및 수정 지시]")
    st.info(data.get("step7", {}).get("detail", "검토 완료"))

# ==========================================
# 🚀 메인 앱 로직
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 마스터 V8.02", layout="wide")
    
    st.title("🏭 식품 표시사항 정밀 검토 (V8.02 - 하이브리드)")
    st.markdown("⚡ AI 데이터 스캔 + Python 수학 엔진 결합")
    st.markdown("<hr>", unsafe_allow_html=True)

    c_type, c_mode = st.columns(2)
    with c_type:
        p_type = st.radio("📌 식품유형", ("일반식품", "특수의료용도식품 / 환자식"))
    with c_mode:
        i_mode = st.radio("📌 검토 모드", ("단품 검토", "선물세트 내/외포장 대조"))

    st.markdown("### 🎨 파일 업로드")
    u1, u2, u3 = st.columns(3)
    with u1: imgs = st.file_uploader("시안 이미지", type=["jpg","png","jpeg"], accept_multiple_files=True)
    with u2: reps = st.file_uploader("시험성적서", type=["pdf","jpg","png"], accept_multiple_files=True)
    with u3: legals = st.file_uploader("한글라벨/배합비", type=["pdf","jpg","png"], accept_multiple_files=True)

    if st.button("🔍 전수 룰 하이브리드 QC 시작", type="primary"):
        if not (imgs or reps or legals):
            st.warning("🚨 파일을 업로드해주세요.")
            st.stop()
            
        content = []
        with st.spinner("AI 추출 및 Python 계산 엔진 가동 중..."):
            for f_list in [imgs, reps, legals]:
                if f_list:
                    for f in f_list:
                        if f.type.startswith("image"): content.append(Image.open(f))
                        else:
                            tmp = f"temp_{f.name}"
                            with open(tmp, "wb") as file: file.write(f.getbuffer())
                            up = genai.upload_file(tmp)
                            while up.state.name == "PROCESSING": time.sleep(1)
                            content.append(up)
            
            model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            cmd = f"[유형: {p_type}, 모드: {i_mode}] 시안과 서류를 대조하여 7단계 JSON 형식으로 응답해."
            resp = model.generate_content(content + [cmd], generation_config=genai.types.GenerationConfig(temperature=0.0))
            
            res_json = parse_ai_json(resp.text)
            if res_json:
                render_report(res_json)
            else:
                st.error("데이터 파싱 실패. 원본 로그를 확인하세요.")
                st.code(resp.text)
            
            for f in glob.glob("temp_*"): os.remove(f)

if __name__ == "__main__":
    if check_password(): main()
