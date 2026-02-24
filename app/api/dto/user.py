from pydantic import BaseModel


class UserLoginIn(BaseModel):
    id: int
    auth_date: int
    hash: str
    first_name: str | None
    last_name: str | None
    username: str | None
    photo_url: str | None


class UserLoginOut(BaseModel):
    access_token: str


class UserMeOut(BaseModel):
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    photo_url: str | None
    role: str
    balance: int
    has_license: bool
    ref_code: str | None
    impersonated: bool | None = None
    real_user_id: int | None = None
