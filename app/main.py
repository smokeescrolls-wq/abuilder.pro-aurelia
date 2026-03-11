"""
AURELIA ENGINE — REST API
FastAPI server that wraps the Aurelia audio cloaking processor.
Designed to run in Docker on a VPS (Hostinger, etc.)
"""

import os
import uuid
import shutil
import tempfile
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Config ───
API_KEY = os.getenv("AURELIA_API_KEY", "change-me-in-production")
UPLOAD_DIR = Path(os.getenv("AURELIA_UPLOAD_DIR", "/tmp/aurelia/uploads"))
OUTPUT_DIR = Path(os.getenv("AURELIA_OUTPUT_DIR", "/tmp/aurelia/outputs"))
MAX_FILE_SIZE_MB = int(os.getenv("AURELIA_MAX_FILE_SIZE_MB", "200"))
MAX_DURATION_SECONDS = int(os.getenv("AURELIA_MAX_DURATION_SECONDS", "600"))
FILE_RETENTION_HOURS = int(os.getenv("AURELIA_FILE_RETENTION_HOURS", "24"))

ALLOWED_ORIGINS = os.getenv(
    "AURELIA_ALLOWED_ORIGINS",
    "https://audiobuilder.com.br,https://app.audiobuilder.com.br,http://localhost:3000"
).split(",")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── App ───
app = FastAPI(
    title="Aurelia Engine",
    description="Audio cloaking processing API for AudioBuilder",
    version="1.0.0",
    docs_url="/docs" if os.getenv("AURELIA_ENV", "development") == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── In-memory job tracker ───
jobs: dict[str, dict] = {}


# ─── Auth ───
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─── Models ───
class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | processing | completed | failed
    filename: Optional[str] = None
    download_url: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


# ─── Helpers ───
def cleanup_old_files():
    """Remove files older than retention period."""
    cutoff = datetime.now() - timedelta(hours=FILE_RETENTION_HOURS)
    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        for f in directory.iterdir():
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink(missing_ok=True)

    # Clean old jobs from memory
    expired = [
        jid for jid, j in jobs.items()
        if datetime.fromisoformat(j["created_at"]) < cutoff
    ]
    for jid in expired:
        jobs.pop(jid, None)


async def run_aurelia(job_id: str, input_path: str, output_path: str, category: str, strategy: str):
    """Run aurelia.py as a subprocess."""
    jobs[job_id]["status"] = "processing"

    cmd = [
        "python3", "/app/aurelia.py",
        input_path,
        "--output", output_path,
        "--category", category,
        "--strategy", strategy,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=MAX_DURATION_SECONDS + 60  # extra margin
        )

        if proc.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            jobs[job_id].update({
                "status": "completed",
                "output_path": output_path,
                "filename": os.path.basename(output_path),
                "file_size": file_size,
            })
        else:
            error_msg = stderr.decode("utf-8", errors="replace")[-500:]
            jobs[job_id].update({
                "status": "failed",
                "error": error_msg or "Processing failed with no output",
            })

    except asyncio.TimeoutError:
        jobs[job_id].update({
            "status": "failed",
            "error": "Processing timed out",
        })
    except Exception as e:
        jobs[job_id].update({
            "status": "failed",
            "error": str(e),
        })


# ─── Routes ───

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring / load balancers."""
    return {
        "status": "ok",
        "service": "aurelia-engine",
        "version": "1.0.0",
        "active_jobs": sum(1 for j in jobs.values() if j["status"] == "processing"),
    }


@app.post("/api/v1/process", response_model=JobResponse)
async def process_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form("general"),
    strategy: str = Form("dual"),
    x_api_key: Optional[str] = Header(None),
):
    """
    Upload a video and start audio cloaking processing.
    Returns a job_id to poll for status.
    """
    verify_api_key(x_api_key)

    # Validate file extension
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a"}:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Validate strategy
    if strategy not in {"dual", "hybrid", "spectral"}:
        raise HTTPException(400, f"Invalid strategy: {strategy}")

    # Validate category
    valid_categories = {"weight_loss", "ed", "supplements", "skincare", "fitness", "general", "random"}
    if category not in valid_categories:
        category = "general"

    # Read file with size limit
    job_id = str(uuid.uuid4())
    input_dir = UPLOAD_DIR / job_id
    input_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"input{ext}"
    input_path = str(input_dir / safe_filename)

    size = 0
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    try:
        with open(input_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                size += len(chunk)
                if size > max_bytes:
                    f.close()
                    shutil.rmtree(input_dir, ignore_errors=True)
                    raise HTTPException(413, f"File exceeds {MAX_FILE_SIZE_MB}MB limit")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        raise HTTPException(500, f"Failed to save file: {str(e)}")

    # Setup output
    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    original_stem = Path(file.filename or "video").stem
    output_path = str(output_dir / f"{original_stem}_shielded.mp4")

    # Register job
    jobs[job_id] = {
        "status": "queued",
        "input_path": input_path,
        "output_path": None,
        "filename": None,
        "error": None,
        "file_size": None,
        "created_at": datetime.now().isoformat(),
        "category": category,
        "strategy": strategy,
    }

    # Start processing in background
    background_tasks.add_task(run_aurelia, job_id, input_path, output_path, category, strategy)

    # Cleanup old files periodically
    background_tasks.add_task(cleanup_old_files)

    return JobResponse(
        job_id=job_id,
        status="queued",
        message="Processing started. Poll /api/v1/status/{job_id} for updates.",
    )


@app.get("/api/v1/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str, x_api_key: Optional[str] = Header(None)):
    """Get the status of a processing job."""
    verify_api_key(x_api_key)

    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    download_url = None
    if job["status"] == "completed":
        download_url = f"/api/v1/download/{job_id}"

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        filename=job.get("filename"),
        download_url=download_url,
        error=job.get("error"),
        created_at=job.get("created_at"),
    )


@app.get("/api/v1/download/{job_id}")
async def download_file(job_id: str, x_api_key: Optional[str] = Header(None)):
    """Download the processed video file."""
    verify_api_key(x_api_key)

    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job["status"] != "completed":
        raise HTTPException(400, f"Job not ready. Status: {job['status']}")

    output_path = job.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(404, "Output file not found")

    return FileResponse(
        path=output_path,
        filename=job.get("filename", "output.mp4"),
        media_type="video/mp4",
    )
