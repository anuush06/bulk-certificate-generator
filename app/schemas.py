from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from typing_extensions import Annotated


NonEmptyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CreateJobRequest(BaseModel):
    event_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    issued_on: date
    recipients: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=1000)]


class RecipientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: NonEmptyName
    email: EmailStr


class RecipientResponse(BaseModel):
    id: int
    name: str
    email: str
    status: str
    error: str | None = None
    certificate_url: str | None = None


class JobResponse(BaseModel):
    id: int
    event_name: str
    issued_on: str
    status: str
    total: int
    succeeded: int
    failed: int
    created_at: str
    recipients: list[RecipientResponse]
