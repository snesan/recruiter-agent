import json
import os

from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

class RecruiterAgent:
    def __init__(self, persist_directory="./data/chroma_db"):
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
        return text

    def match_single_resume(self, jd_text: str, resume_path: str) -> dict:
        """Task 1: Match a single JD with a resume and return a score + rationale."""
        resume_text = self.extract_text_from_pdf(resume_path)
        
        prompt_template = """
        You are an objective, unbiased expert technical recruiter. Your evaluation must be strictly 
        blind to candidate age, gender, ethnicity, name, or institutional background. Focus strictly on 
        technical skills, domain expertise, project impact, and professional experience match against the JD.

        Job Description:
        {jd}

        Resume Content:
        {resume}

        Provide your output strictly in the following JSON format:
        {{
            "match_score": <integer score from 0 to 100>,
            "key_strengths": ["strength 1", "strength 2"],
            "missing_skills": ["skill 1", "skill 2"],
            "fairness_audit_passed": true,
            "rationale": "Detailed justification of score based purely on competencies."
        }}
        """
        prompt = PromptTemplate(template=prompt_template, input_variables=["jd", "resume"])
        chain = prompt | self.llm
        response = chain.invoke({"jd": jd_text, "resume": resume_text})
        
        content = response.content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)

    def shortlist_resumes(self, jd_text: str, resume_paths: list[str]) -> list[dict]:
        """Task 2: Shortlist and rank a directory of resumes against a JD."""
        results = []
        for path in resume_paths:
            if path.endswith(".pdf"):
                try:
                    evaluation = self.match_single_resume(jd_text, path)
                    results.append({
                        "filename": os.path.basename(path),
                        "score": evaluation.get("match_score", 0),
                        "details": evaluation
                    })
                except Exception as e:
                    results.append({
                        "filename": os.path.basename(path),
                        "score": 0,
                        "error": str(e)
                    })
        # Sort descending by match score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results
