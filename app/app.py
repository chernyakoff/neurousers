from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.partners import router as partners_router
from config import config, init_db, shutdown_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await shutdown_db()


def _is_local_dev_env() -> bool:
    url = (config.api.url or "").lower()
    host = (config.api.host or "").lower()
    return "localhost" in url or "127.0.0.1" in url or host in {"localhost", "127.0.0.1"}


openapi_url = "/openapi.json" if _is_local_dev_env() else None
docs_url = "/docs" if _is_local_dev_env() else None
redoc_url = "/redoc" if _is_local_dev_env() else None


app = FastAPI(
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

cors_origins = config.auth.cors_origins or [
    "https://lidorub.online",
    "https://content.lidorub.online",
    "https://tg.lidorub.online",
    "https://users.lidorub.online",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(partners_router)


@app.get("/")
def root():
    raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "neurousers"}
