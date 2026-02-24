from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routers.admin import router as admin_router
from routers.auth import router as auth_router
from config import config, init_db, shutdown_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await shutdown_db()


app = FastAPI(lifespan=lifespan)

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


@app.get("/")
def root():
    raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "neurousers"}
