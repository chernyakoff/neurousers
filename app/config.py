from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, PostgresDsn, SecretStr
from tortoise import BaseDBAsyncClient, Tortoise


class Jwt(BaseModel):
    expire_seconds: int
    refresh_expire_days: int
    secret: str
    algorithm: str


class Bot(BaseModel):
    token: SecretStr
    name: str


class Api(BaseModel):
    port: int = Field(default=8834)
    host: str = Field(default="0.0.0.0")
    url: str | None = None
    jwt: Jwt
    bot: Bot


class Auth(BaseModel):
    cors_origins: list[str] = Field(default_factory=list)
    cookie_domain: str | None = None
    default_return_to: str = "https://lidorub.online/app"


class Internal(BaseModel):
    user_sync_token: SecretStr | None = None


class Postgres(BaseModel):
    dsn: PostgresDsn


class Settings(BaseModel):
    api: Api
    auth: Auth = Field(default_factory=Auth)
    internal: Internal = Field(default_factory=Internal)
    postgres: Postgres

    @classmethod
    def create(cls, path: str | Path = "config.yml") -> Self:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


config = Settings.create()


tortoise_config = {
    "connections": {
        "default": config.postgres.dsn.unicode_string(),
    },
    "apps": {
        "models": {
            "models": ["models.orm", "aerich.models"],
            "default_connection": "default",
        },
    },
}


async def init_db() -> BaseDBAsyncClient:
    await Tortoise.init(config=tortoise_config, timezone="Europe/Moscow", use_tz=False)
    return Tortoise.get_connection("default")


async def shutdown_db() -> None:
    await Tortoise.close_connections()
