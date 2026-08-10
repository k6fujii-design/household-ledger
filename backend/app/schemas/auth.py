from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    line_user_id: str | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserOut


class UserUpdate(BaseModel):
    name: str
    line_user_id: str | None = None
