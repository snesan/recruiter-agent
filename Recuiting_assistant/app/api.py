import os
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from openai import AuthenticationError, OpenAIError
from pydantic import BaseModel
from PyPDF2.errors import PdfReadError

load_dotenv()

from app.google_drive import DriveConfigurationError, DriveFolderError, download_folder_from_drive
from app.recruiter import AgentConfigurationError, MatchEvaluation, RecruiterAgent


app = FastAPI(title="Recruiting Assistant API", version="2.0.0")
agent = RecruiterAgent()
max_resume_bytes = int(os.getenv("MAX_RESUME_MB", "10")) * 1024 * 1024


class ShortlistRequest(BaseModel):
    jd_text: str
    drive_folder_id: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/match", response_model=MatchEvaluation)
async def match_resume(
    jd_text: Annotated[str, Form(min_length=1)],
    resume: Annotated[UploadFile, File()],
):
    filename = resume.filename or "resume.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported.")

    contents = await resume.read(max_resume_bytes + 1)
    await resume.close()
    if len(contents) > max_resume_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Resume exceeds the {max_resume_bytes // (1024 * 1024)} MB upload limit.",
        )

    try:
        with NamedTemporaryFile(suffix=".pdf") as temporary_resume:
            temporary_resume.write(contents)
            temporary_resume.flush()
            return agent.match_single_resume(jd_text, temporary_resume.name)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=503,
            detail="The OpenAI API key is invalid or expired. Update the secret and redeploy the task.",
        ) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail="The OpenAI request failed. Please try again.") from exc
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/shortlist")
def shortlist_resumes(request: ShortlistRequest):
    try:
        agent.validate_configuration()
        with TemporaryDirectory(prefix="resumes-") as temporary_directory:
            files = download_folder_from_drive(request.drive_folder_id, temporary_directory)
            results = agent.shortlist_resumes(request.jd_text, files)
        return {"total_evaluated": len(results), "shortlist": results}
    except (AgentConfigurationError, DriveConfigurationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DriveFolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=503,
            detail="The OpenAI API key is invalid or expired. Update the secret and redeploy the task.",
        ) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail="The OpenAI request failed. Please try again.") from exc
