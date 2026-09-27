import logging
from pathlib import Path
from uuid import UUID, uuid4
import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import current_user
from .aws import s3
from .config import settings
from .database import get_db
from .models import Job, JobStatus, User
from .queue import send_job
from .schemas import Credentials, JobOut, OperationSpec, TokenOut, UploadOut, UserOut
from .security import create_access_token, hash_password, verify_password

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("cloudflow.api")
app = FastAPI(title=settings.app_name)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=TokenOut, status_code=201)
def register(data: Credentials, db: Session = Depends(get_db)):
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id)), user=user)


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(data: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return TokenOut(access_token=create_access_token(str(user.id)), user=user)


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@app.post("/api/v1/jobs", response_model=UploadOut, status_code=202)
async def create_jobs(files: list[UploadFile] = File(...), operation: str = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        spec = OperationSpec.model_validate_json(operation)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Operation must be valid JSON") from exc
    if spec.name not in {"resize", "compress", "jpeg_to_png", "png_to_jpeg", "grayscale"}:
        raise HTTPException(status_code=422, detail="Unsupported operation")
    if spec.name == "resize" and not spec.width and not spec.height:
        raise HTTPException(status_code=422, detail="Resize requires width or height")
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one image")
    results = []
    for upload in files:
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"{upload.filename or 'Image'} exceeds upload limit")
        safe_name = Path(upload.filename or "image").name.replace("/", "_").replace(chr(92), "_")[:255] or "image"
        job_id = uuid4()
        key = f"uploads/{user.id}/{job_id}/original{Path(safe_name).suffix.lower()}"
        try:
            s3().put_object(Bucket=settings.aws_s3_bucket, Key=key, Body=content, ContentType=upload.content_type or "application/octet-stream")
        except Exception as exc:
            logger.exception("S3 upload failed for job %s", job_id)
            raise HTTPException(status_code=502, detail="Could not store uploaded image in S3") from exc
        job = Job(id=job_id, user_id=user.id, filename=safe_name, operation=spec.name, options_json=spec.model_dump_json(), input_s3_key=key)
        db.add(job)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            try:
                s3().delete_object(Bucket=settings.aws_s3_bucket, Key=key)
            except Exception:
                logger.exception("S3 cleanup failed for %s", key)
            raise HTTPException(status_code=503, detail="Could not create processing job") from exc
        try:
            send_job(job_id)
        except Exception:
            job.status = JobStatus.FAILED
            job.error_message = "Queue send failed; retry this job."
            db.commit()
            logger.exception("SQS send failed for job %s", job_id)
        db.refresh(job)
        results.append(job)
    return UploadOut(jobs=results)


def owned_job(job_id: UUID, user: User, db: Session) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/v1/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return list(db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(100)))


@app.get("/api/v1/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return owned_job(job_id, user, db)


@app.post("/api/v1/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = owned_job(job_id, user, db)
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
    job.status, job.error_message, job.completed_at = JobStatus.QUEUED, None, None
    db.commit()
    try:
        send_job(job.id)
    except Exception as exc:
        job.status, job.error_message = JobStatus.FAILED, "Queue send failed; try later."
        db.commit()
        raise HTTPException(status_code=502, detail="Could not enqueue retry") from exc
    db.refresh(job)
    return job


@app.get("/api/v1/jobs/{job_id}/download")
def download_job(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = owned_job(job_id, user, db)
    if job.status != JobStatus.COMPLETED or not job.output_s3_key:
        raise HTTPException(status_code=409, detail="Result is not ready")
    try:
        url = s3().generate_presigned_url("get_object", Params={"Bucket": settings.aws_s3_bucket, "Key": job.output_s3_key}, ExpiresIn=settings.presigned_url_seconds)
    except Exception as exc:
        logger.exception("Could not sign result URL")
        raise HTTPException(status_code=502, detail="Could not create download link") from exc
    return {"url": url, "expires_in": settings.presigned_url_seconds}
