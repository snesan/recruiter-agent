import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from PyPDF2 import PdfReader


class AgentConfigurationError(RuntimeError):
    pass


class MatchEvaluation(BaseModel):
    match_score: int = Field(ge=0, le=100)
    key_strengths: list[str]
    missing_skills: list[str]
    fairness_audit_passed: bool
    rationale: str


class RecruiterAgent:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._llm: ChatOpenAI | None = None

    def validate_configuration(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise AgentConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to .env locally or AWS Secrets Manager in ECS."
            )

    def extract_text_from_pdf(self, pdf_path: str | Path) -> str:
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise ValueError("The PDF does not contain extractable text.")
        return text

    def match_single_resume(self, jd_text: str, resume_path: str | Path) -> dict:
        self.validate_configuration()
        resume_text = self.extract_text_from_pdf(resume_path)
        response = self._get_llm().invoke(
            [
                (
                    "system",
                    "You are an objective technical recruiter. Ignore candidate name, age, gender, ethnicity, "
                    "and institutional prestige. Evaluate only relevant skills, experience, project impact, and "
                    "the evidence present in the resume. Return one valid JSON object and no markdown.",
                ),
                (
                    "human",
                    f"""Compare this resume with the job description.

Job description:
{jd_text}

Resume:
{resume_text}

Return exactly these JSON fields:
- match_score: integer from 0 to 100
- key_strengths: array of strings
- missing_skills: array of strings
- fairness_audit_passed: boolean
- rationale: string
""",
                ),
            ]
        )
        content = response.content if isinstance(response.content, str) else json.dumps(response.content)
        return MatchEvaluation.model_validate_json(content).model_dump()

    def shortlist_resumes(self, jd_text: str, resume_paths: list[str]) -> list[dict]:
        self.validate_configuration()
        results = []
        for resume_path in resume_paths:
            if not resume_path.lower().endswith(".pdf"):
                continue
            try:
                evaluation = self.match_single_resume(jd_text, resume_path)
                results.append(
                    {
                        "filename": Path(resume_path).name,
                        "score": evaluation["match_score"],
                        "details": evaluation,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "filename": Path(resume_path).name,
                        "score": 0,
                        "error": str(exc),
                    }
                )
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self.model,
                temperature=0.0,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        return self._llm

