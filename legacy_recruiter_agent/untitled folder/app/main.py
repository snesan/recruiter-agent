import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.agent import RecruiterAgent
from app.drive_utils import download_folder_from_drive

app = FastAPI(title="Recruiter Assistant Agent API", version="1.0")
agent = RecruiterAgent()

class MatchRequest(BaseModel):
    jd_text: str
    resume_path: str

class ShortlistRequest(BaseModel):
    jd_text: str
    drive_folder_id: str

@app.post("/api/match")
def match_resume(req: MatchRequest):
    if not os.path.exists(req.resume_path):
        raise HTTPException(status_code=404, detail="Resume file not found.")
    result = agent.match_single_resume(req.jd_text, req.resume_path)
    return result

@app.post("/api/shortlist")
def shortlist_resumes(req: ShortlistRequest):
    temp_dir = "./data/temp_resumes"
    try:
        downloaded_files = download_folder_from_drive(req.drive_folder_id, temp_dir)
        results = agent.shortlist_resumes(req.jd_text, downloaded_files)
        return {"total_evaluated": len(results), "shortlist": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))