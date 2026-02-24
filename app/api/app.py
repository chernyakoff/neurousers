from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.admin import router as admin_router
from api.routers.auth import router as auth_router
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
def health_check():
    return {"status": "ok", "service": "neurousers"}
