import os

# 🚨 서버 멈춤 방지용 방어막
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '1'

import streamlit as st
import glob
import tempfile
import pandas as pd
from pypdf import PdfReader

from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 💡 구글 429/503 에러 우회용 로컬 임베딩 및 자동 재시도 장착
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import (
    ChatGoogleGenerativeAI, 
    HarmCategory, 
    HarmBlockThreshold
)

# --- 1. 웹페이지 기본 설정 ---
st.set_page_config(page_title="AI BCP 위해요소 자동 분석 시스템", page_icon="🔬", layout="wide")
st.title("🔬 연세유업 BCP 위해요소 정밀 분석 및 교차검증 시스템")
st.markdown("**[사용 가이드]** 깃허브에 업로드된 <식품공전> 및 <자사기준> DB를 바탕으로 원료 서류를 교차 검증합니다.")

# --- 2. API Key 보안 설정 ---
try:
    google_api_key = st.secrets["GOOGLE_API_KEY"].strip()
except KeyError:
    st.error("⚠️ 설정(Secrets)에 GOOGLE_API_KEY가 등록되지 않았습니다.")
    st.stop()

safety_settings = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}

# --- 3. 기본 뇌(식품공전 DB) 세팅 ---
DB_PATH = "faiss_index_haccp_base"
base_files = glob.glob("*.pdf") + glob.glob("*.txt")

@st.cache_resource(show_spinner=False)
def load_base_knowledge(_file_list):
    embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
    
    if os.path.exists(DB_PATH):
        return FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)

    documents = []
    for file_path in _file_list:
        try:
            if file_path.lower().endswith('.pdf'):
                documents.extend(PyPDFLoader(file_path).load())
            elif file_path.lower().endswith('.txt'):
                documents.extend(TextLoader(file_path, encoding='utf-8').load())
        except Exception:
            pass

    if not documents: 
        return None

    splits = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200).split_documents(documents)
    
    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
    vectorstore.save_local(DB_PATH)
    return vectorstore

def extract_text_from_upload(uploaded_file):
    if not uploaded_file: return ""
    text = ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        if tmp_path.endswith('.pdf'):
            reader = PdfReader(tmp_path)
            pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
            text = "\n".join(pages_text)
        elif tmp_path.endswith(('.xls', '.xlsx')):
            text = pd.read_excel(tmp_path).to_string()
        elif tmp_path.endswith('.txt'):
            with open(tmp_path, 'r', encoding='utf-8') as f:
                text = f.read()
    finally:
        os.remove(tmp_path)
    return text

# --- 4. BCP 특화 AI 프롬프트 (최종 완성: 본질적 위해요소 도출 + 이원화 로직) ---
TEMPLATE = """
당신은 연세유업의 최고 권위 HACCP 및 품질안전 AI 심사관입니다. 
당신의 목표는 실무자가 다시 검증할 필요가 없을 정도로, [제출된 서류]와 [원료의 본질적 위해요소 개념]을 결합하여 완벽한 위해요소 분석 보고서를 작성하는 것입니다.

🚨 [심사관 절대 수칙: 화이트리스트 강제 및 본질적 위해요소 도출] 🚨

1. [위해요소명 화이트리스트 (가장 중요. 이외 단어 도출 절대 불가)]:
   - [화학적(C)]: 납, 비소, 중금속, 카드뮴, 수은, 잔류농약, 총 아플라톡신, 파튤린, 멜라민, 타르색소, 알레르기(명확히 '포함'으로 명시된 경우만)
   - [물리적(P)]: 이물, 금속이물
   - [생물학적(B)]: 대장균군, 살모넬라, 세균수 등 위생지표균

2. [가장 중요한 원칙: 원재료 본질 기반의 위해요소 강제 도출 (서류 의존 탈피)]:
   - 납품업체의 COA(성적서)에 없더라도, 해당 원료 특성상 식품공전에서 강제하는 필수 위해요소라면 4번 BCP 표에 무조건(C/P/B) 도출하십시오.
   - 예: '사과' 베이스면 서류에 없어도 파튤린, 잔류농약 필수 도출. / '콩' 베이스면 아플라톡신, 잔류농약 필수 도출.
   - 단, 향료/화학합성물 베이스인 경우에는 농산물 유래 위해요소(농약, 곰팡이독소 등)를 절대 도출하지 마십시오 (소설 금지).

3. [휴먼 에러 정밀 교차 검증 및 환각(Hallucination) 완벽 통제]:
   - **필수 성적서 누락 지적:** 2번 원칙에 의해 표에 도출한 필수 위해요소(예: 파튤린)가 실제 COA(성적서)에는 검사 항목으로 빠져 있다면, 3번 목차에 "원료 특성상 [해당 위해요소] 검사가 필수이나 성적서에 누락되어 있으므로 추가 징구가 필요하다"고 강력히 지적하십시오.
   - **보관 조건 및 배합비 교차검증:** 라벨/성적서의 보관 조건(예: 냉동)과 규격서의 보관 조건(예: 실온)이 다르면 3번 목차에 '서류 간 불일치 오타'로 지적하십시오.
   - **서류 백지 환각 금지 & 체크리스트 오독 금지:** 성적서가 있는데 없다고 하거나, 숫자 '0(무)'을 알파벳 'O(있음)'로 잘못 읽지 마십시오.
   - **알레르기 문구 오독 금지:** 라벨의 "이 제품은 ~과 같은 제조시설에서..."는 단순 [교차오염 주의문구]입니다. 이를 원료 배합 성분으로 착각하여 알레르기 C로 도출하지 마십시오.

4. [TMI(일반론 복붙) 절대 금지]:
   - '제조영업등록' 등 원료 스펙과 무관한 식품위생법 일반론 나열 금지.

[분석 대상 원료명]: {material_name}

[식품공전 및 자사 기준 (Context)]:
{context}

[업로드된 서류 내용]:
{target_documents}

💡 **[최종 출력 포맷 - 아래 4단계 목차 순서대로 작성]** 💡
### 1. 원료 물리화학적 특성 사전 검토
- **주요 배합 성분:** (원료명과 비율만 추출)
- **미생물(B) 생존 가능성 판정:** (원물 특성, 수분, pH, 보관온도 등 팩트 기반 논리 작성)

### 2. 식품공전 필수 규격 및 관리 포인트 (법적 기준 팩트 보고)
**[공통 규격 (제2. 식품일반에 대한 공통기준 및 규격)]** - (🚨 필수 문장 구조: "본 원료는 [주요 특성] 특성이 있으므로, 공통 규격에 따라 [잔류농약, 중금속, 파튤린 등 원물 유래 위해요소 또는 면제 사유]에 대한 검사 및 관리가 [필수적으로 이루어져야 합니다 / 면제됩니다].")
  
**[해당 식품유형 개별 규격 (제5. 식품별 기준 및 규격)]** - (🚨 필수 문장 구조: "본 원료는 식품유형이 [서류상 식품유형]이므로, 개별 규격에 따라 [대장균군, 타르색소 등 유형 특화 위해요소 또는 면제 사유]에 대한 검사 및 관리가 [이루어져야 합니다 / 면제됩니다].")
- **[서류상 명시된 세부 규격]**: (성상, 비중, 이물, 대장균군 등 서류에 기재된 수치화된 규격을 리스트업 하십시오.)

### 3. 원자재규격서 보완 권고사항
- **[추가/확인 필요 항목]**: [이유] (보관조건 오타, 체크리스트 누락, **성적서에 누락된 필수 위해요소 성적 요구** 등 명백한 팩트 오류 및 실무적 요구사항 지적)

### 4. 최종 BCP 위해요소 분석표 (과학적 필터링 결과)
| 구분 | 원부재료명 | 분류 (B/C/P) | 위해요소명 | 예방 및 제어조치 방법 |
|---|---|:---:|---|---|
"""

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# --- 5. UI 및 실행부 ---
with st.sidebar:
    st.header("📂 분석 대상 파일 업로드")
    input_material_name = st.text_input("1. 원료명 (선택):", placeholder="미입력시 자동 추출")
    spec_file = st.file_uploader("2. 원자재규격서 업로드", type=['pdf', 'xlsx', 'txt'])
    coa_file = st.file_uploader("3. 성적서(COA) 업로드", type=['pdf', 'xlsx', 'txt'])
    run_btn = st.button("🚀 BCP 정밀 분석 실행", type="primary", use_container_width=True)

if run_btn:
    if not spec_file and not coa_file:
        st.warning("⚠️ 분석할 서류를 최소 1개 이상 업로드해주세요.")
    else:
        # 🚨 서버 과부하(503/429) 방어: max_retries=5 장착
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            api_key=google_api_key, 
            temperature=0, 
            safety_settings=safety_settings,
            max_retries=5
        )
        
        with st.status("🔍 원재료 본질 기반 정밀 분석 중...", expanded=True) as status:
            spec_text = extract_text_from_upload(spec_file) if spec_file else "규격서 미제공"
            coa_text = extract_text_from_upload(coa_file) if coa_file else "성적서 미제공"
            target_documents = f"[규격서]\n{spec_text}\n\n[성적서]\n{coa_text}"
            
            final_material_name = input_material_name.strip()
            if not final_material_name:
                try:
                    final_material_name = (PromptTemplate.from_template("다음 서류 내용에서 핵심 원료명(제품명) 1개만 추출해 (예: 유청단백분말).\n\n{text}") | llm | StrOutputParser()).invoke({"text": target_documents[:1000]}).strip()
                except:
                    final_material_name = "분석원료"
            
            st.write("1. 🧠 무제한 로컬 임베딩 엔진 로딩 중...")
            vector_db = load_base_knowledge(base_files)
            status.update(label="✅ 준비 완료! 리포트를 생성합니다.", state="complete")

        if vector_db:
            st.markdown("---")
            st.markdown(f"## 📊 [{final_material_name}] BCP 교차검증 리포트")
            
            retriever = vector_db.as_retriever(search_kwargs={"k": 8})
            
            def get_enhanced_context(_):
                return format_docs(retriever.invoke(f"{final_material_name} 식품공전 규격 필수검사항목 기준"))

            # 🚨 메인 보고서 생성기에도 max_retries=5 장착
            rag_chain = (
                {"context": get_enhanced_context, "material_name": lambda x: final_material_name, "target_documents": lambda x: target_documents}
                | PromptTemplate.from_template(TEMPLATE) 
                | ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash", 
                    api_key=google_api_key, 
                    temperature=0, 
                    streaming=True, 
                    safety_settings=safety_settings,
                    max_retries=5
                ) 
                | StrOutputParser()
            )

            try:
                st.write_stream(rag_chain.stream(final_material_name))
            except Exception as e:
                st.error(f"🚨 에러 발생: {e}\n\n(※ 429 에러 발생 시, 1분당 무료 제공 횟수를 초과한 것입니다. 약 30~60초 대기 후 다시 버튼을 눌러주세요!)")
