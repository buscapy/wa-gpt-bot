# mypy: ignore-errors

import os
import json
import logging
from typing import Any

import sentry_sdk
import openai                  # SDK oficial de OpenAI
import httpx                   # Cliente HTTP async
from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.v1.price import router as price_router
from app.core.config import settings
from app.gpt.tools import price_function   # ← tool definida en app/gpt/tools.py


# ---------- Configuración base FastAPI ---------- #
def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# CORS (opcional)
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------- Endpoints básicos ---------- #
@app.get("/ping", tags=["health"])
def ping() -> dict:
    return {"message": "pong"}


@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": "Welcome to wa-gpt-bot API"}


# ---------- Routers de la API v1 ---------- #
app.include_router(api_router,   prefix=settings.API_V1_STR)              # router central
app.include_router(price_router, prefix=settings.API_V1_STR, tags=["price"])  # /api/v1/price


# ---------- Variables de entorno ---------- #
VERIFY_TOKEN   = os.getenv("WA_VERIFY_TOKEN", "olindarivas")
PHONE_ID       = os.getenv("WA_PHONE_NUMBER_ID")
ACCESS_TOKEN   = os.getenv("WA_ACCESS_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

GRAPH_API_URL  = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
INTERNAL_PORT  = os.getenv("PORT", "10000")        # Render expone PORT=10000


# ---------- GPT con “tools” ---------- #
async def chat_gpt(user_text: str) -> Any:
    """
    Primera llamada: GPT decide si responde directo
    o si necesita llamar a la tool get_price.
    Devuelve el objeto Response completo (no sólo el texto).
    """
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente conciso en español. "
                    "Cuando el usuario pida un precio real usa la función get_price."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        tools=[price_function],
        tool_choice="auto",
        max_tokens=300,
    )
    return rsp


# ---------- Enviar mensaje a WhatsApp ---------- #
async def send_whatsapp(to: str, text: str) -> None:
    if not (PHONE_ID and ACCESS_TOKEN):
        logging.warning("WA credentials missing; skipping send.")
        return

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(GRAPH_API_URL, headers=headers, json=data)
        r.raise_for_status()


# ---------- Llamada interna al scraper ---------- #
async def call_price_endpoint(product: str) -> dict:
    """
    Envía { "product": ... } al endpoint interno /api/v1/price
    y devuelve el JSON de respuesta.
    """
    url = f"http://127.0.0.1:{INTERNAL_PORT}{settings.API_V1_STR}/price"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"product": product})
        r.raise_for_status()
        return r.json()


# ---------- Webhook de WhatsApp Cloud API ---------- #
@app.get("/webhook", tags=["webhook"])
async def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge") or "")
    return PlainTextResponse("error", status_code=status.HTTP_403_FORBIDDEN)


@app.post("/webhook", tags=["webhook"])
async def receive(request: Request):
    """
    1. Recibimos mensaje de WhatsApp.
    2. Lo mandamos a GPT (tool-enabled).
    3. Si GPT pide get_price → llamamos /price.
    4. GPT formatea la respuesta final.
    5. Se envía al usuario por WhatsApp.
    """
    body = await request.json()
    logging.info(body)

    # Filtrar actualizaciones que no contienen 'messages'
    try:
        msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
    except (KeyError, IndexError):
        return {"status": "ignored"}   # sólo status, no hay texto

    user_text = msg["text"]["body"]
    wid       = msg["from"]

    # ---------- 1ª llamada a GPT ----------
    first_rsp = await chat_gpt(user_text)
    choice    = first_rsp.choices[0]

    if choice.finish_reason == "tool_call":
        # GPT quiere la función get_price
        args = json.loads(choice.message.tool_call.arguments)
        product = args["product"]

        try:
            price_json = await call_price_endpoint(product)
        except Exception as exc:
            logging.exception("Error en /price: %s", exc)
            price_json = {"error": str(exc), "product": product}

        # ---------- 2ª llamada : GPT formatea la respuesta ----------
        second_rsp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                *first_rsp.messages,                       # historial
                {
                    "role": "tool",
                    "name": "get_price",
                    "content": json.dumps(price_json),
                },
            ],
            max_tokens=200,
        )
        answer = second_rsp.choices[0].message.content.strip()
    else:
        # GPT respondió directo
        answer = choice.message.content.strip()

    logging.info("GPT reply: %s", answer)
    await send_whatsapp(wid, answer)

    return {"status": "ok"}
