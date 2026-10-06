import os
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .certificates import generate_certificate
from .database import Base, SessionLocal, engine
from .models import GenerationJob, RecipientResult
from .schemas import CreateJobRequest, JobResponse, RecipientInput, RecipientResponse


Base.metadata.create_all(bind=engine)
app = FastAPI(title="Bulk Certificate Generator", version="1.0.0")
OUTPUT_DIR = Path(os.getenv("CERTIFICATE_OUTPUT_DIR", "./generated_certificates")).resolve()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_job(job_id: int) -> None:
    """Process each recipient independently; a bad row never aborts its siblings."""
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return
        job.status = "processing"
        db.commit()
        rows = db.scalars(select(RecipientResult).where(RecipientResult.job_id == job_id)).all()
        for row in rows:
            if row.status == "failed":
                continue
            try:
                path = OUTPUT_DIR / str(job_id) / f"{row.id}.pdf"
                generate_certificate(row.name, job.event_name, job.issued_on, str(path))
                row.certificate_path = str(path)
                row.status = "succeeded"
                row.error = None
            except Exception as exc:
                row.status = "failed"
                row.error = f"Certificate generation failed: {exc}"[:1000]
            db.commit()
        job.succeeded = sum(1 for row in rows if row.status == "succeeded")
        job.failed = sum(1 for row in rows if row.status == "failed")
        job.status = "completed_with_errors" if job.failed else "completed"
        db.commit()
    finally:
        db.close()


def serialize_job(job: GenerationJob) -> JobResponse:
    recipients = [
        RecipientResponse(
            id=r.id, name=r.name, email=r.email, status=r.status, error=r.error,
            certificate_url=f"/certificates/{r.id}" if r.status == "succeeded" else None,
        )
        for r in job.recipients
    ]
    return JobResponse(
        id=job.id, event_name=job.event_name, issued_on=job.issued_on, status=job.status,
        total=job.total, succeeded=job.succeeded, failed=job.failed,
        created_at=job.created_at.isoformat(), recipients=recipients,
    )


@app.post("/jobs", response_model=JobResponse, status_code=202)
def create_job(payload: CreateJobRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = GenerationJob(event_name=payload.event_name, issued_on=payload.issued_on.isoformat(), total=len(payload.recipients))
    db.add(job)
    db.flush()
    for item in payload.recipients:
        try:
            recipient = RecipientInput.model_validate(item)
            row = RecipientResult(job_id=job.id, name=recipient.name, email=str(recipient.email), status="queued")
        except ValidationError as exc:
            # Retain safe identifying input where available so the failed row is traceable.
            row = RecipientResult(
                job_id=job.id,
                name=str(item.get("name", ""))[:200] if isinstance(item, dict) else "",
                email=str(item.get("email", ""))[:320] if isinstance(item, dict) else "",
                status="failed",
                error="; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:1000],
            )
        job.recipients.append(row)
        db.add(row)
    db.flush()
    job.failed = sum(1 for row in job.recipients if row.status == "failed")
    if job.failed == job.total:
        job.status = "completed_with_errors"
    db.commit()
    db.refresh(job)
    if job.status != "completed_with_errors":
        background_tasks.add_task(run_job, job.id)
    return serialize_job(job)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)


@app.get("/certificates/{recipient_id}")
def get_certificate(recipient_id: int, db: Session = Depends(get_db)):
    row = db.get(RecipientResult, recipient_id)
    if not row or row.status != "succeeded" or not row.certificate_path:
        raise HTTPException(status_code=404, detail="Certificate not found")
    path = Path(row.certificate_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file is unavailable")
    return FileResponse(path, media_type="application/pdf", filename=f"certificate-{recipient_id}.pdf")
