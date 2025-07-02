# mypy: ignore-errors


import os
import logging

import json               # ⬅️ nuevo
from typing import Any    # ⬅️ nuevo

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
app.include_router(api_router, prefix=settings.API_V1_STR)        # router central
app.include_router(price_router, prefix=settings.API_V1_STR, tags=["price"])  # /api/v1/price


# ---------- Variables de entorno para WhatsApp ---------- #
VERIFY_TOKEN   = os.getenv("WA_VERIFY_TOKEN", "olindarivas")
PHONE_ID       = os.getenv("WA_PHONE_NUMBER_ID")
ACCESS_TOKEN   = os.getenv("WA_ACCESS_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")
GRAPH_API_URL  = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"


# ---------- Utilidades GPT y WhatsApp ---------- #
async def chat_gpt(user_text: str) -> str:
    """Devuelve una respuesta concisa en español usando GPT-4o Mini."""
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un asistente conciso en español."},
            {"role": "user", "content": user_text},
        ],
        max_tokens=300,
    )
    return rsp.choices[0].message.content.strip()


async def send_whatsapp(to: str, text: str):
    """Envía `text` a un usuario de WhatsApp Cloud API."""
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
        r.raise_for_status()   # lanza excepción si falla
from app.gpt.tools import price_function

async def chat_gpt(user_text: str):
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": (
               "Eres un asistente en español que contesta preguntas generales. "
               "Si el usuario pregunta un precio real usa la función get_price."
             )
            },
            {"role": "user", "content": user_text}
        ],
        tools=[price_function],
        tool_choice="auto",
        max_tokens=300,
    )
    return rsp


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
    • Extrae el texto entrante
    • Pregunta a GPT
    • Envía la respuesta a WhatsApp
    • Devuelve la respuesta de GPT cuando:
        – DEBUG_ECHO=true (env var) **o**
        – X-Debug: 1      (header)
    """
    body = await request.json()
    logging.info(body)

    gpt_reply = ""
    try:
        msg  = body["entry"][0]["changes"][0]["value"]["messages"][0]
        text = msg["text"]["body"]
        wid  = msg["from"]

        gpt_reply = await chat_gpt(text)
        logging.info("GPT reply: %s", gpt_reply)

        await send_whatsapp(wid, gpt_reply)

    except Exception as exc:
        logging.exception("Error procesando mensaje: %s", exc)

    # --- decidir si incluimos la respuesta en el body ---
    debug_env    = os.getenv("DEBUG_ECHO", "false").lower() == "true"
    debug_header = request.headers.get("x-debug") == "1"

    if debug_env or debug_header:
        return {"status": "ok", "gpt_reply": gpt_reply}

    return {"status": "ok"}
