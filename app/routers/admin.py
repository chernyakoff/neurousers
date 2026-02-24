import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from routers.auth import (
    admin_required,
    create_impersonation_tokens,
    get_real_user,
    set_refresh_cookie,
    set_refresh_cookie_raw,
)
from config import config
from models import orm

router = APIRouter(prefix="/admin", tags=["admin"])


class ImpersonateIn(BaseModel):
    username: str


class ImpersonateOut(BaseModel):
    access: str


class LicenseIn(BaseModel):
    username: str
    days: int


class LicenseOut(BaseModel):
    status: Literal["success", "error"]
    message: str


class BalanceIn(BaseModel):
    username: str
    amount: int


class BalanceOut(BaseModel):
    status: Literal["success", "error"]
    message: str


class CreateUserIn(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    role: orm.Role | None = None

    # Keep payload tolerant: CLI may send extra fields from neurogram user model.
    model_config = ConfigDict(extra="ignore")


class CreateUserOut(BaseModel):
    status: Literal["created", "updated"]
    user_id: int


def internal_sync_required(x_internal_token: str | None = Header(default=None)) -> None:
    token = config.internal.user_sync_token
    if token is None:
        raise HTTPException(status_code=503, detail="User sync token is not configured")

    expected = token.get_secret_value()
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal token")


@router.post(
    "/impersonate",
    response_model=ImpersonateOut,
    dependencies=[Depends(admin_required)],
)
async def impersonate(
    data: ImpersonateIn,
    response: Response,
    admin: orm.User = Depends(get_real_user),
):
    username = data.username.removeprefix("https://t.me/").removeprefix("@")
    user = await orm.User.get_or_none(username=username)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    access, refresh = create_impersonation_tokens(user.id, admin.id)
    set_refresh_cookie_raw(response, refresh)

    return ImpersonateOut(access=access)


@router.post("/stop-impersonate")
async def stop_impersonate(response: Response, admin: orm.User = Depends(admin_required)):
    set_refresh_cookie(response, admin.id)
    return {"status": "ok"}


@router.post(
    "/license",
    response_model=LicenseOut,
    dependencies=[Depends(admin_required)],
)
async def extend_license(data: LicenseIn):
    username = data.username.removeprefix("https://t.me/").removeprefix("@")
    user = await orm.User.get_or_none(username=username)
    if not user:
        return LicenseOut(status="error", message="Пользователь не найден")

    await user.extend_license(data.days)
    display_date = user.license_end_date.strftime("%d.%m.%Y")
    return LicenseOut(status="success", message=f"Выписана лицензия до {display_date}")


@router.post(
    "/balance",
    response_model=BalanceOut,
    dependencies=[Depends(admin_required)],
)
async def add_balance(data: BalanceIn):
    username = data.username.removeprefix("https://t.me/").removeprefix("@")
    user = await orm.User.get_or_none(username=username)
    if not user:
        return BalanceOut(status="error", message="Пользователь не найден")

    await user.add_balance(data.amount)
    return BalanceOut(status="success", message=f"Баланс пополнен на {data.amount} руб")


@router.post(
    "/create-user",
    response_model=CreateUserOut,
    dependencies=[Depends(internal_sync_required)],
)
async def create_user(data: CreateUserIn):
    defaults: dict[str, Any] = {
        "username": data.username,
        "first_name": data.first_name,
        "last_name": data.last_name,
        "photo_url": data.photo_url,
    }
    if data.role is not None:
        defaults["role"] = data.role

    _, created = await orm.User.update_or_create(
        defaults=defaults,
        id=data.id,
    )
    return CreateUserOut(status="created" if created else "updated", user_id=data.id)
