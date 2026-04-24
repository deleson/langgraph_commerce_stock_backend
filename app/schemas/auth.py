from pydantic import BaseModel,ConfigDict,EmailStr,Field

class UserRegisterRequest(BaseModel):
    email:EmailStr
    username: str = Field(min_length=3,max_length=50)
    password: str = Field(min_length=3,max_length=128)
    timezone: str | None = Field(default=None,max_length=50)
    risk_preference:str | None = Field(default=None,max_length=20)


class UserLoginRequest(BaseModel):
    email:EmailStr
    password:str = Field(min_length=8,max_length=128)


class TokenPayload(BaseModel):
    sub:str
    user_id: int
    is_superuser: bool = False

class TokenResponse(BaseModel):
    access_token:str
    token_type:str = "bearer"

class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:int
    email:EmailStr
    username:str
    is_active:bool
    is_superuser:bool




class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"