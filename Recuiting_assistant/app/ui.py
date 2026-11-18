import os

import requests
import streamlit as st


st.set_page_config(page_title="Recruiting Assistant", page_icon="🤖", layout="wide")

api_url = os.getenv("API_BASE_URL", "http://localhost:8000/api").rstrip("/")


def post_to_api(endpoint: str, **kwargs):
    try:
        return requests.post(f"{api_url}/{endpoint}", timeout=180, **kwargs)
    except requests.ConnectionError:
        st.error("Cannot connect to the recruiting API. Verify that the API service is running.")
    except requests.Timeout:
        st.error("The recruiting API took too long to respond. Please try again.")
    except requests.RequestException as exc:
        st.error(f"The recruiting API request failed: {exc}")
    return None


def show_api_error(response):
    try:
        detail = response.json().get("detail")
    except (requests.JSONDecodeError, AttributeError):
        detail = response.text
    st.error(detail or "The recruiting API request failed.")


st.title("🤖 Recruiting Assistant")
st.markdown("Competency-focused resume matching and Google Drive shortlisting.")

single_tab, drive_tab = st.tabs(["📋 Single Resume Match", "📁 Google Drive Shortlist"])

with single_tab:
    st.header("Match a Resume with a Job Description")
    job_description = st.text_area("Job Description", height=220, key="single_jd")
    resume_file = st.file_uploader("Resume PDF", type=["pdf"], accept_multiple_files=False)
    st.caption("The PDF is uploaded securely to the API for this request and is not retained.")

    if st.button("Evaluate Match", type="primary"):
        if not job_description or resume_file is None:
            st.warning("Provide both a job description and a PDF resume.")
        else:
            with st.spinner("Evaluating the resume..."):
                response = post_to_api(
                    "match",
                    data={"jd_text": job_description},
                    files={
                        "resume": (
                            resume_file.name,
                            resume_file.getvalue(),
                            "application/pdf",
                        )
                    },
                )
            if response is not None and response.status_code == 200:
                result = response.json()
                st.metric("Match Score", f"{result['match_score']}%")
                st.json(result)
            elif response is not None:
                show_api_error(response)

with drive_tab:
    st.header("Shortlist PDFs from Google Drive")
    drive_job_description = st.text_area("Job Description", height=220, key="drive_jd")
    drive_folder_id = st.text_input("Google Drive Folder ID or URL")
    st.caption("Paste the folder link or ID. Your authenticated Google account must have access.")

    if st.button("Run Batch Shortlisting"):
        if not drive_job_description or not drive_folder_id:
            st.warning("Provide both a job description and a Google Drive folder ID.")
        else:
            with st.spinner("Downloading and evaluating resumes..."):
                response = post_to_api(
                    "shortlist",
                    json={
                        "jd_text": drive_job_description,
                        "drive_folder_id": drive_folder_id,
                    },
                )
            if response is not None and response.status_code == 200:
                result = response.json()
                st.success(f"Evaluated {result['total_evaluated']} candidates.")
                for index, candidate in enumerate(result["shortlist"], start=1):
                    label = f"Rank #{index}: {candidate['filename']} — {candidate['score']}%"
                    with st.expander(label):
                        if "error" in candidate:
                            st.error(candidate["error"])
                        else:
                            st.json(candidate["details"])
            elif response is not None:
                show_api_error(response)


