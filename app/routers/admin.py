import hmac
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from tortoise.expressions import F

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
    license_end_date: datetime | None = None
    balance: int | None = None
    ref_code: str | None = None
    or_api_key: str | None = None
    or_api_hash: str | None = None
    or_model: str | None = None

    # Keep payload tolerant: CLI may send extra fields from neurogram user model.
    model_config = ConfigDict(extra="ignore")


class CreateUserOut(BaseModel):
    status: Literal["created", "updated"]
    user_id: int


class InternalUserStateIn(BaseModel):
    user_id: int


class InternalUserStateOut(BaseModel):
    user_id: int
    balance_kopecks: int
    api_key: str | None
    api_hash: str | None
    model: str | None


class InternalSetOpenRouterIn(BaseModel):
    user_id: int
    api_key: str | None = None
    api_hash: str | None = None
    model: str | None = None


class InternalDebitBalanceIn(BaseModel):
    user_id: int
    amount_kopecks: int


class InternalDebitBalanceOut(BaseModel):
    status: Literal["ok", "insufficient_funds", "not_found"]
    balance_kopecks: int | None


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
    # Partial upsert: do not overwrite existing values with nulls when fields are omitted.
    defaults: dict[str, Any] = data.model_dump(
        exclude={"id"},
        exclude_none=True,
    )

    _, created = await orm.User.update_or_create(
        defaults=defaults,
        id=data.id,
    )
    return CreateUserOut(status="created" if created else "updated", user_id=data.id)


@router.post(
    "/internal/user-state",
    response_model=InternalUserStateOut,
    dependencies=[Depends(internal_sync_required)],
)
async def internal_user_state(data: InternalUserStateIn):
    user = await orm.User.get_or_none(id=data.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    settings = user.get_openrouter_settings()
    return InternalUserStateOut(
        user_id=user.id,
        balance_kopecks=user.balance,
        api_key=settings["api_key"],
        api_hash=settings["api_hash"],
        model=settings["model"],
    )


@router.post(
    "/internal/set-openrouter-settings",
    response_model=InternalUserStateOut,
    dependencies=[Depends(internal_sync_required)],
)
async def internal_set_openrouter_settings(data: InternalSetOpenRouterIn):
    user = await orm.User.get_or_none(id=data.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    await user.set_openrouter_settings(
        api_key=data.api_key,
        api_hash=data.api_hash,
        model=data.model,
    )
    await user.refresh_from_db()
    settings = user.get_openrouter_settings()
    return InternalUserStateOut(
        user_id=user.id,
        balance_kopecks=user.balance,
        api_key=settings["api_key"],
        api_hash=settings["api_hash"],
        model=settings["model"],
    )


@router.post(
    "/internal/debit-balance",
    response_model=InternalDebitBalanceOut,
    dependencies=[Depends(internal_sync_required)],
)
async def internal_debit_balance(data: InternalDebitBalanceIn):
    if data.amount_kopecks <= 0:
        raise HTTPException(status_code=400, detail="amount_kopecks must be positive")

    user = await orm.User.get_or_none(id=data.user_id)
    if user is None:
        return InternalDebitBalanceOut(status="not_found", balance_kopecks=None)

    updated = await orm.User.filter(
        id=data.user_id,
        balance__gte=data.amount_kopecks,
    ).update(balance=F("balance") - data.amount_kopecks)

    if not updated:
        fresh = await orm.User.get(id=data.user_id)
        return InternalDebitBalanceOut(
            status="insufficient_funds",
            balance_kopecks=fresh.balance,
        )

    fresh = await orm.User.get(id=data.user_id)
    return InternalDebitBalanceOut(status="ok", balance_kopecks=fresh.balance)
