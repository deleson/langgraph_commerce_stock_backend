from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_superuser: bool
    status: str
    timezone: str | None
    risk_preference: str | None
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    timezone: str | None = Field(default=None, max_length=50)
    risk_preference: str | None = Field(default=None, max_length=20)