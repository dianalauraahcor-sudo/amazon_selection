import os
import uuid
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from .schemas import AnalyzeRequest, JobStatus
from . import jobs

app = FastAPI(title="Amazon Selection AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/health")
def health():
    return {"service": "amazon-selection", "status": "ok"}


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    """Upload one or more Excel files. Returns list of saved filenames."""
    saved = []
    for f in files:
        if not f.filename or not f.filename.endswith(".xlsx"):
            continue
        # Prefix with uuid to avoid collisions
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        path = os.path.join(UPLOAD_DIR, safe_name)
        content = await f.read()
        with open(path, "wb") as fp:
            fp.write(content)
        saved.append(safe_name)
    if not saved:
        raise HTTPException(400, "No valid .xlsx files uploaded")
    return {"filenames": saved}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if not req.asins:
        raise HTTPException(400, "asins is required")
    if not req.excel_filenames:
        raise HTTPException(400, "excel_filenames is required — please upload Excel files first")
    # Validate files exist
    for fn in req.excel_filenames:
        if not os.path.exists(os.path.join(UPLOAD_DIR, fn)):
            raise HTTPException(400, f"File not found: {fn}")
    job_id = jobs.submit(req)
    return {"job_id": job_id}


@app.get("/status/{job_id}", response_model=JobStatus)
def status(job_id: str):
    js = jobs.get(job_id)
    if not js:
        raise HTTPException(404, "job not found")
    return js


@app.get("/result/{job_id}")
def result(job_id: str):
    js = jobs.get(job_id)
    if not js:
        raise HTTPException(404, "job not found")
    if js.status != "done":
        return {"status": js.status, "progress": js.progress, "current_node": js.current_node}
    return {"status": "done", **(jobs.RESULTS.get(job_id) or {})}


@app.get("/report/{job_id}")
def report(job_id: str):
    js = jobs.get(job_id)
    if not js or not js.report_filename or not os.path.exists(js.report_filename):
        raise HTTPException(404, "report not ready")
    return FileResponse(
        js.report_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(js.report_filename),
    )


# Static frontend (mount last so API routes win)
_WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.isdir(_WEB_DIR):
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
