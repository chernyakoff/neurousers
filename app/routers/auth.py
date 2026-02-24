import hashlib
import hmac
import html
import json
import random
import string
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import ExpiredSignatureError, JWTError, jwt
from tortoise import timezone as tz

from dto.user import (
    UserBalanceOut,
    UserLoginIn,
    UserLoginOut,
    UserMeOut,
    UserOpenRouterSettingsIn,
    UserOpenRouterSettingsOut,
)
from config import config
from models import orm

router = APIRouter(tags=["auth"])


ALLOWED_RETURN_HOSTS = {
    "lidorub.online",
    "content.lidorub.online",
    "tg.lidorub.online",
    "users.lidorub.online",
    "localhost:5173",
    "localhost:5273",
}

DEV_MOCK_USER_ID = 359107176
DEV_MOCK_HASH = "mock"


def _is_secure_cookie() -> bool:
    if config.api.url:
        return config.api.url.startswith("https")
    return True


def _cookie_samesite() -> str:
    return "none" if _is_secure_cookie() else "lax"


def _is_local_dev_env() -> bool:
    url = (config.api.url or "").lower()
    return "localhost" in url or "127.0.0.1" in url


def _refresh_cookie_options() -> dict:
    options = {
        "httponly": True,
        "samesite": _cookie_samesite(),
        "secure": _is_secure_cookie(),
        "max_age": config.api.jwt.refresh_expire_days * 24 * 60 * 60,
        "path": "/",
    }
    if config.auth.cookie_domain:
        options["domain"] = config.auth.cookie_domain
    return options


def _validate_return_to(value: str | None) -> str:
    if not value:
        return config.auth.default_return_to
    from urllib.parse import urlparse

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return config.auth.default_return_to
    if parsed.netloc not in ALLOWED_RETURN_HOSTS:
        return config.auth.default_return_to
    return value


def validate_telegram_data(data: dict):
    received_hash = data.pop("hash", None)
    auth_date = data.get("auth_date")

    if not received_hash:
        raise HTTPException(400, "No hash in Telegram data")

    if auth_date is None or int(time.time()) - int(auth_date) > 86400:
        raise HTTPException(400, "Telegram authentication session is expired")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if v)
    secret_key = hashlib.sha256(
        config.api.bot.token.get_secret_value().encode()
    ).digest()
    generated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(generated_hash, received_hash):
        raise HTTPException(400, "Telegram data signature mismatch")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=config.api.jwt.expire_seconds)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.api.jwt.secret, algorithm=config.api.jwt.algorithm)


def create_refresh_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=config.api.jwt.refresh_expire_days)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.api.jwt.secret, algorithm=config.api.jwt.algorithm)


def create_impersonation_tokens(target_user_id: int, admin_id: int) -> tuple[str, str]:
    claims = {
        "sub": str(target_user_id),
        "real_sub": str(admin_id),
        "impersonated": True,
    }
    return create_access_token(claims), create_refresh_token(claims)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.api.jwt.secret, algorithms=[config.api.jwt.algorithm])
    except ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except JWTError:
        raise HTTPException(401, "Invalid token")


def set_refresh_cookie(response: Response, user_id: int):
    refresh_token = create_refresh_token({"sub": str(user_id)})
    response.set_cookie(key="refresh_token", value=refresh_token, **_refresh_cookie_options())


def set_refresh_cookie_raw(response: Response, refresh_token: str):
    response.set_cookie(key="refresh_token", value=refresh_token, **_refresh_cookie_options())


def clear_refresh_cookie(response: Response):
    response.delete_cookie(key="refresh_token", path="/", domain=config.auth.cookie_domain)


def _extract_bearer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authorization header missing or invalid")
    return authorization.split(" ", 1)[1]


async def get_current_user(authorization: str = Header(...)) -> orm.User:
    token = _extract_bearer_token(authorization)
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Invalid token")

    user = await orm.User.get_or_none(id=int(user_id))
    if not user:
        raise HTTPException(404, "User not found")
    return user


async def get_real_user(authorization: str = Header(...)) -> orm.User:
    token = _extract_bearer_token(authorization)
    payload = decode_token(token)

    user_id_raw = payload.get("sub")
    if payload.get("impersonated") and payload.get("real_sub"):
        user_id_raw = payload.get("real_sub")

    if not user_id_raw:
        raise HTTPException(401, "Invalid token")

    user = await orm.User.get_or_none(id=int(user_id_raw))
    if not user:
        raise HTTPException(404, "User not found")
    return user


def admin_required(user: orm.User = Depends(get_real_user)) -> orm.User:
    if user.role != orm.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    return_to: str | None = Query(default=None),
    invite_ref_code: str | None = Query(default=None),
    ref: str | None = Query(default=None),
):
    safe_return_to = _validate_return_to(return_to)
    safe_invite_ref_code = invite_ref_code or ref
    bot_name = html.escape(config.api.bot.name, quote=True)
    show_mock_login = _is_local_dev_env()
    show_telegram_widget = not show_mock_login
    mock_button_html = (
        """
    <button id="mock-login-btn" class="mock-btn" type="button">
      Mock login (dev)
    </button>
"""
        if show_mock_login
        else ""
    )
    mock_script = (
        """
    const mockBtn = document.getElementById('mock-login-btn');
    if (mockBtn) {
      mockBtn.addEventListener('click', async () => {
        mockBtn.disabled = true;
        const original = mockBtn.textContent;
        mockBtn.textContent = 'Signing in...';
        try {
          await loginWithPayload({
            id: 359107176,
            first_name: 'Mike',
            last_name: null,
            username: 'mike',
            photo_url: null,
            auth_date: Math.floor(Date.now() / 1000),
            hash: 'mock',
          });
        } catch (e) {
          mockBtn.disabled = false;
          mockBtn.textContent = original;
        }
      });
    }
"""
        if show_mock_login
        else ""
    )
    telegram_script = (
        f"""
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.async = true;
    script.setAttribute('data-telegram-login', '{bot_name}');
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-radius', '8');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.setAttribute('data-request-access', 'write');
    document.getElementById('tg-login').appendChild(script);
"""
        if show_telegram_widget
        else ""
    )

    page = f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <meta name=\"color-scheme\" content=\"light dark\" />
  <title>Lidorub Users Login</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f3f6fb;
      --card: #ffffff;
      --text: #0f172a;
      --line: rgba(15, 23, 42, 0.12);
      --shadow: 0 18px 42px rgba(15, 23, 42, 0.12);
      --accent: #0ea5e9;
      --accent-hover: #0284c7;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0a1222;
        --card: #111b30;
        --text: #e2e8f0;
        --line: rgba(148, 163, 184, 0.25);
        --shadow: 0 22px 50px rgba(2, 6, 23, 0.55);
        --accent: #38bdf8;
        --accent-hover: #0ea5e9;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 20px;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      color: var(--text);
      background: var(--bg);
    }}
    .wrap {{
      width: 100%;
      max-width: 520px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--card) 95%, transparent);
      box-shadow: var(--shadow);
      border-radius: 22px;
      padding: 26px;
      backdrop-filter: blur(8px);
    }}
    h1 {{ margin: 0 0 18px; font-size: 28px; line-height: 1.2; text-align: center; }}
    .login-row {{
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
    }}
    .mock-btn {{
      border: 1px solid var(--line);
      background: var(--accent);
      color: #fff;
      border-radius: 10px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 600;
      transition: .2s background ease;
    }}
    .mock-btn:hover {{ background: var(--accent-hover); }}
    .mock-btn:disabled {{ opacity: .7; cursor: wait; }}
    .status {{
      margin-top: 12px;
      min-height: 22px;
      font-size: 13px;
      text-align: center;
    }}
    .status.error {{ color: #ef4444; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Логин</h1>
    <div class=\"login-row\">
      <div id=\"tg-login\"></div>
{mock_button_html}
    </div>
    <div id=\"status\" class=\"status\"></div>
  </div>

  <script>
    const RETURN_TO = {json.dumps(safe_return_to, ensure_ascii=False)};
    const INVITE_REF_CODE = {json.dumps(safe_invite_ref_code, ensure_ascii=False)};
    const statusEl = document.getElementById('status');

    async function loginWithPayload(payload) {{
      if (statusEl) {{
        statusEl.classList.remove('error');
        statusEl.textContent = 'Авторизация...';
      }}

      const resp = await fetch('/auth', {{
        method: 'POST',
        credentials: 'include',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});

      if (!resp.ok) {{
        const text = await resp.text();
        if (statusEl) {{
          statusEl.textContent = 'Login failed: ' + text;
          statusEl.classList.add('error');
        }}
        throw new Error(text);
      }}

      const data = await resp.json();
      if (statusEl) statusEl.textContent = 'Успешно. Переход...';
      const callbackUrl = `/auth/callback?access_token=${{encodeURIComponent(data.access_token)}}&return_to=${{encodeURIComponent(RETURN_TO)}}`;
      window.location.href = callbackUrl;
    }}

    window.onTelegramAuth = async (user) => {{
      const payload = {{
        id: user.id,
        first_name: user.first_name ?? null,
        last_name: user.last_name ?? null,
        username: user.username ?? null,
        photo_url: user.photo_url ?? null,
        auth_date: user.auth_date,
        hash: user.hash,
      }};
      if (INVITE_REF_CODE) {{
        payload.invite_ref_code = INVITE_REF_CODE;
      }}
      await loginWithPayload(payload);
    }};

{telegram_script}
{mock_script}
  </script>
</body>
</html>
"""
    return HTMLResponse(page)


def generate_ref_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


async def create_unique_ref_code() -> str:
    for _ in range(10):
        code = generate_ref_code()
        exists = await orm.User.filter(ref_code=code).exists()
        if not exists:
            return code
    raise RuntimeError("Failed to generate unique ref_code")


@router.post("/auth", response_model=UserLoginOut)
async def login(data: UserLoginIn, response: Response):
    data_dict = data.model_dump()

    # Local-only Telegram bypass for frontend development without public domain.
    if (
        _is_local_dev_env()
        and data_dict["hash"] == DEV_MOCK_HASH
        and data_dict["id"] == DEV_MOCK_USER_ID
    ):
        access_token = create_access_token({"sub": str(DEV_MOCK_USER_ID)})
        set_refresh_cookie(response, DEV_MOCK_USER_ID)
        return {"access_token": access_token}

    invite_ref_code = data_dict.pop("invite_ref_code", None)

    validate_telegram_data(data_dict)

    user = await orm.User.get_or_none(id=data.id)
    referrer = None
    if invite_ref_code:
        referrer = await orm.User.get_or_none(ref_code=invite_ref_code)
        if referrer and referrer.id == data.id:
            referrer = None

    if not user:
        user = await orm.User.create(
            id=data.id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            photo_url=data.photo_url,
            ref_code=await create_unique_ref_code(),
            referred_by=referrer,
        )
    else:
        await orm.User.filter(id=user.id).update(
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            photo_url=data.photo_url,
        )
        if not user.ref_code:
            user.ref_code = await create_unique_ref_code()
            await user.save(update_fields=["ref_code"])
        if (
            not user.referred_by
            and referrer
            and not user.license_end_date
            and referrer.id != user.id
        ):
            user.referred_by = referrer
            await user.save(update_fields=["referred_by"])

    access_token = create_access_token({"sub": str(user.id)})
    set_refresh_cookie(response, user.id)
    return {"access_token": access_token}


@router.post("/auth/refresh", response_model=UserLoginOut)
async def refresh_token_endpoint(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
):
    if not refresh_token:
        raise HTTPException(401, "No refresh token cookie found")

    payload = decode_token(refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Invalid refresh token")

    user = await orm.User.get_or_none(id=int(user_id))
    if not user:
        raise HTTPException(401, "Invalid refresh token")

    if payload.get("impersonated") and payload.get("real_sub"):
        real_sub = int(payload["real_sub"])
        admin = await orm.User.get_or_none(id=real_sub)
        if not admin or admin.role != orm.Role.ADMIN:
            raise HTTPException(401, "Invalid refresh token")

        access_token, new_refresh = create_impersonation_tokens(
            target_user_id=user.id,
            admin_id=admin.id,
        )
        set_refresh_cookie_raw(response, new_refresh)
    else:
        access_token = create_access_token({"sub": str(user.id)})
        set_refresh_cookie(response, user.id)

    return {"access_token": access_token}


@router.post("/auth/logout")
async def logout(response: Response):
    clear_refresh_cookie(response)
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserMeOut)
async def me(
    current: orm.User = Depends(get_current_user),
    authorization: str = Header(...),
):
    has_license = bool(current.license_end_date and current.license_end_date > tz.now())
    payload = decode_token(_extract_bearer_token(authorization))

    result = UserMeOut(
        id=current.id,
        username=current.username,
        first_name=current.first_name,
        last_name=current.last_name,
        photo_url=current.photo_url,
        role=current.role.name,
        balance=current.balance,
        has_license=has_license,
        ref_code=current.ref_code,
    )

    if payload.get("impersonated") and payload.get("real_sub"):
        result.impersonated = True
        result.real_user_id = int(payload["real_sub"])

    return result


@router.get("/auth/callback")
async def callback_with_token(
    access_token: str,
    response: Response,
    return_to: str | None = Query(default=None),
):
    payload = decode_token(access_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Invalid token")

    set_refresh_cookie(response, int(user_id))
    destination = _validate_return_to(return_to)
    sep = "&" if "?" in destination else "?"
    return RedirectResponse(f"{destination}{sep}access_token={quote(access_token)}", status_code=302)


@router.get("/auth/openrouter-settings", response_model=UserOpenRouterSettingsOut)
async def get_openrouter_settings(current: orm.User = Depends(get_current_user)):
    return UserOpenRouterSettingsOut(**current.get_openrouter_settings())


@router.post("/auth/openrouter-settings", response_model=UserOpenRouterSettingsOut)
async def set_openrouter_settings(
    data: UserOpenRouterSettingsIn,
    current: orm.User = Depends(get_current_user),
):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(400, "No fields to update")

    await current.set_openrouter_settings(
        api_key=payload.get("api_key"),
        api_hash=payload.get("api_hash"),
        model=payload.get("model"),
    )
    return UserOpenRouterSettingsOut(**current.get_openrouter_settings())


@router.get("/auth/balance", response_model=UserBalanceOut)
async def get_balance(current: orm.User = Depends(get_current_user)):
    return UserBalanceOut(
        balance_kopecks=current.balance,
        balance_rub=current.get_balance_rub(),
    )
