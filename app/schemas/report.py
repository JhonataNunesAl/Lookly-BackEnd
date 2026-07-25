from enum import Enum
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class ReportTarget(str, Enum):
    PROFILE = "profile"
    SELLER = "seller"
    LOOK = "look"


class ReportCreate(BaseModel):
    target_type: ReportTarget
    target_id: UUID
    reason: str
    description: str | None = None
    contact_email: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    target_type: ReportTarget
    target_id: UUID
    reason: str
    description: str | None = None
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True
