import uvicorn

from config import config

if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host=config.api.host,
        port=config.api.port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
