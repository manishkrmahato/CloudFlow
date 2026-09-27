from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from .models import JobStatus


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: str
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class OperationSpec(BaseModel):
    name: str
    width: int | None = Field(default=None, ge=1, le=5000)
    height: int | None = Field(default=None, ge=1, le=5000)
    quality: int | None = Field(default=None, ge=10, le=95)


class JobOut(BaseModel):
    id: UUID
    filename: str
    operation: str
    status: JobStatus
    attempt_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class UploadOut(BaseModel):
    jobs: list[JobOut]
