import hashlib
import hmac
import html
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import ExpiredSignatureError, JWTError, jwt
from tortoise import timezone as tz

from api.dto.user import UserLoginIn, UserLoginOut, UserMeOut
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


def _is_secure_cookie() -> bool:
    if config.api.url:
        return config.api.url.startswith("https")
    return True


def _cookie_samesite() -> str:
    return "none" if _is_secure_cookie() else "lax"


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
async def login_page(return_to: str | None = Query(default=None)):
    safe_return_to = _validate_return_to(return_to)
    escaped_return = html.escape(safe_return_to, quote=True)
    bot_name = html.escape(config.api.bot.name, quote=True)

    page = f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Auth Login</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f4f6f8; }}
    .wrap {{ max-width: 480px; margin: 12vh auto; background: #fff; padding: 28px; border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,.08); }}
    h1 {{ margin: 0 0 10px; font-size: 24px; }}
    p {{ margin: 0 0 18px; color: #4b5563; }}
    .meta {{ margin-top: 14px; color: #6b7280; font-size: 13px; word-break: break-all; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Sign in with Telegram</h1>
    <p>Unified login for all Lidorub services.</p>
    <div id=\"tg-login\"></div>
    <div class=\"meta\">return_to: <span id=\"rt\">{escaped_return}</span></div>
  </div>

  <script>
    const RETURN_TO = {html.escape(repr(safe_return_to), quote=False)};

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

      const resp = await fetch('/auth', {{
        method: 'POST',
        credentials: 'include',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});

      if (!resp.ok) {{
        const text = await resp.text();
        alert('Login failed: ' + text);
        return;
      }}

      const data = await resp.json();
      try {{
        localStorage.setItem('accessToken', data.access_token);
      }} catch (_e) {{}}
      window.location.href = RETURN_TO;
    }};

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.async = true;
    script.setAttribute('data-telegram-login', '{bot_name}');
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-radius', '8');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.setAttribute('data-request-access', 'write');
    document.getElementById('tg-login').appendChild(script);
  </script>
</body>
</html>
"""
    return HTMLResponse(page)


@router.post("/auth", response_model=UserLoginOut)
async def login(data: UserLoginIn, response: Response):
    data_dict = data.model_dump()
    validate_telegram_data(data_dict)

    user = await orm.User.get_or_none(id=data.id)
    if not user:
        user = await orm.User.create(
            id=data.id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            photo_url=data.photo_url,
        )
    else:
        await orm.User.filter(id=user.id).update(
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            photo_url=data.photo_url,
        )

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
