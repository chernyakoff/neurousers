from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from api.routers.auth import (
    admin_required,
    create_impersonation_tokens,
    get_real_user,
    set_refresh_cookie,
    set_refresh_cookie_raw,
)
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
