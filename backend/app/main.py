import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
@app.get("/ping", tags=["health"])
def ping() -> dict:
    return {"message": "pong"}

@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": "Welcome to wa-gpt-bot API"}

app.include_router(api_router, prefix=settings.API_V1_STR)

# --- WhatsApp Webhook -------------------------------------------------
from fastapi import Request, status
from fastapi.responses import PlainTextResponse
import os, logging

VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "olindarivas")

@app.get("/webhook", tags=["webhook"])
async def verify(request: Request):
    """
    Meta valida la URL con un GET.
    Parámetros recibidos: hub.mode, hub.verify_token, hub.challenge
    """
    params     = request.query_params
    mode       = params.get("hub.mode")
    token      = params.get("hub.verify_token")
    challenge  = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("error",
                             status_code=status.HTTP_403_FORBIDDEN)

@app.post("/webhook", tags=["webhook"])
async def receive(req: Request):
    """Recibe mensajes; por ahora solo los imprime en los logs."""
    body = await req.json()
    logging.info(body)
    return {"status": "ok"}   # WhatsApp necesita 200 en <10 s
