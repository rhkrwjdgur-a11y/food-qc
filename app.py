# ==========================================
# 5. 메인 화면 구성
# ==========================================
def main():
    st.set_page_config(page_title="식품 QC 통합 마스터 (Final)", page_icon="🏭", layout="wide")
    st.title("🏭 식품 표시사항 정밀 검토 (현장 실무형 통합버전)")
    st.markdown("---")
    
    with st.spinner("법령 데이터베이스를 연결 중입니다..."):
        references, file_names = upload_reference_files_to_gemini()
    
    if file_names:
        st.success(f"✅ 법령 파일 {len(file_names)}개가 준비되었습니다.")
        with st.expander("📂 학습된 법령 파일 목록 보기"):
            for name in file_names:
                st.write(f"- 📄 {name}")
    else:
        st.error("⚠️ 폴더에 PDF 법령 파일이 없습니다. (같은 폴더에 넣어주세요)")
    
    # 👇 수정된 부분: xlsx, csv (엑셀) 확장자 추가
    uploaded_files = st.file_uploader("파일 업로드 (시안, 시험성적서, 배합비 등)", type=["jpg", "png", "jpeg", "pdf", "xlsx", "csv"], accept_multiple_files=True)

    if uploaded_files:
        user_content = []
        st.write(f"📂 총 {len(uploaded_files)}개의 파일이 인식되었습니다. (한글 .hwp 파일은 PDF로 변환 후 올려주세요)")
        
        for uploaded_file in uploaded_files:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            
            # 👇 수정된 부분: 이미지와 문서(PDF, 엑셀)를 나누어서 처리
            if file_ext in ['jpg', 'jpeg', 'png']:
                image = Image.open(uploaded_file)
                st.image(image, caption=f"{uploaded_file.name}", width=200)
                user_content.append(image)
                
            else:
                # PDF, 엑셀(XLSX, CSV) 등 문서 파일 처리
                temp_filename = f"temp_{uploaded_file.name}"
                with open(temp_filename, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                user_doc = genai.upload_file(temp_filename)
                while user_doc.state.name == "PROCESSING":
                    time.sleep(1)
                    user_doc = genai.get_file(user_doc.name)
                user_content.append(user_doc)

        if st.button("🔍 QC 전문가 모드 진단 시작", type="primary"):
            try:
                model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
                
                with st.spinner("Rule 1~12 (액체/고체 구분, 배합비 2/5% 룰, 성적서 환산 등)을 모두 적용하여 정밀 분석 중입니다..."):
                    prompt = """
                    업로드된 파일들을 종합적으로 검토해줘. 
                    특히 [Rule 11, Rule 12]에 집중하여, 업로드된 자료 중에 '배합비'나 '시험성적서'가 있다면 시안과 교차 검증을 철저하게 수행해.
                    2% 미만 원료 순서와 5% 미만 복합원재료 하위성분 생략 규정을 정확히 적용해서 불필요한 지적을 하지 마.
                    현장에서 제조사가 안전하고 유연하게 생산할 수 있는 방향으로 판단해.
                    """
                    
                    full_input = references + user_content + [prompt]
                    response = model.generate_content(full_input)
                    
                    st.success("분석 완료")
                    st.markdown("### 📋 상세 법적 검토 리포트")
                    st.markdown("---")
                    st.markdown(response.text)
                    
                    # 👇 수정된 부분: PDF뿐만 아니라 임시 엑셀 파일도 확실하게 삭제하도록 변경
                    for f in glob.glob("temp_*"):
                        try: os.remove(f)
                        except: pass

            except Exception as e:
                st.error("오류가 발생했습니다.")
                st.error(f"에러 내용: {e}")
