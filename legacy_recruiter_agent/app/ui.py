import os

import streamlit as st
import requests

st.set_page_config(page_title="Recruiter Assistant Agent", layout="wide")

st.title("🤖 Recruiter Assistant Agent")
st.markdown("Automated, unbiased resume screening, semantic RAG matching, and Google Drive integration.")

api_url = os.getenv("API_BASE_URL", "http://localhost:8000/api").rstrip("/")

def post_to_api(endpoint, payload):
    try:
        return requests.post(f"{api_url}/{endpoint}", json=payload, timeout=120)
    except requests.ConnectionError:
        st.error("Cannot connect to the recruiter API. Please verify that the API service is running.")
    except requests.Timeout:
        st.error("The recruiter API took too long to respond. Please try again.")
    except requests.RequestException as exc:
        st.error(f"The recruiter API request failed: {exc}")
    return None

def show_api_error(response):
    try:
        detail = response.json().get("detail")
    except (requests.JSONDecodeError, AttributeError):
        detail = response.text
    st.error(detail or "The recruiter API request failed.")

tab1, tab2 = st.tabs(["📋 Single Resume Match", "📁 Google Drive Shortlist"])

with tab1:
    st.header("Match Single Resume with JD")
    jd_input_1 = st.text_area("Job Description", height=200, key="jd_1")
    resume_path_input = st.text_input("Local Resume PDF Absolute Path")
    
    if st.button("Evaluate Match"):
        if jd_input_1 and resume_path_input:
            with st.spinner("Analyzing candidate competencies objectively..."):
                resp = post_to_api("match", {"jd_text": jd_input_1, "resume_path": resume_path_input})
                if resp is not None and resp.status_code == 200:
                    data = resp.json()
                    st.metric(label="Match Score", value=f"{data.get('match_score')}%")
                    st.json(data)
                elif resp is not None:
                    show_api_error(resp)
        else:
            st.warning("Please provide both JD text and resume file path.")

with tab2:
    st.header("Batch Shortlist from Google Drive Folder")
    jd_input_2 = st.text_area("Job Description", height=200, key="jd_2")
    drive_folder_id = st.text_input("Google Drive Folder ID (extracted from folder URL)")
    
    if st.button("Run Batch Shortlisting"):
        if jd_input_2 and drive_folder_id:
            with st.spinner("Fetching resumes from Google Drive and running semantic evaluation..."):
                resp = post_to_api("shortlist", {"jd_text": jd_input_2, "drive_folder_id": drive_folder_id})
                if resp is not None and resp.status_code == 200:
                    data = resp.json()
                    st.success(f"Successfully evaluated {data.get('total_evaluated')} candidates!")
                    for idx, candidate in enumerate(data.get("shortlist", [])):
                        with st.expander(f"Rank #{idx+1}: {candidate['filename']} — Score: {candidate['score']}%"):
                            st.json(candidate['details'])
                elif resp is not None:
                    show_api_error(resp)
        else:
            st.warning("Please provide JD text and Google Drive Folder ID.")
