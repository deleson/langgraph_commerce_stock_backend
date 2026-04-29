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
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)