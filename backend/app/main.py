# mypy: ignore-errors
from __future__ import annotations

import os
import json
import logging
import asyncio
from typing import Any

import sentry_sdk
import openai
import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.v1.price import router as price_router
from app.core.config import settings
from app.gpt.tools import price_function

# ────────────────────────── FastAPI base ─────────────────────────────
def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"

if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ───────────────────────────── routes ────────────────────────────────
@app.get("/ping", tags=["health"])
def ping() -> dict:
    return {"message": "pong"}

@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": "Welcome to wa-gpt-bot API"}

app.include_router(api_router,   prefix=settings.API_V1_STR)
app.include_router(price_router, prefix=settings.API_V1_STR, tags=["price"])

# ─────────────────── credenciales & constantes ──────────────────────
VERIFY_TOKEN   = os.getenv("WA_VERIFY_TOKEN", "olindarivas")
PHONE_ID       = os.getenv("WA_PHONE_NUMBER_ID")
ACCESS_TOKEN   = os.getenv("WA_ACCESS_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

GRAPH_API_URL  = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
INTERNAL_PORT  = os.getenv("PORT", "10000")

# ───────────────────── GPT — primera pasada ─────────────────────────
async def chat_gpt(user_text: str) -> Any:
    return await asyncio.to_thread(
        openai.chat.completions.create,
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente conciso en español.\n\n"
                    "• Si el usuario pide un precio real ⇒ usa la función get_price.\n"
                    "• Si la función devuelve la bandera “#” significa que no se encontró "
                    "precio en los sitios web; en ese caso responde con un precio de "
                    "referencia aproximado, dejando claro que es estimado.\n"
                    "Responde siempre en guaraníes (Gs) cuando des cifras."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        tools=[price_function],
        tool_choice="auto",
        max_tokens=300,
    )

# ────────────────── WhatsApp Cloud API helpers ───────────────────────
async def send_whatsapp(to: str, text: str) -> None:
    if not (PHONE_ID and ACCESS_TOKEN):
        logging.warning("WA credentials missing; skipping send.")
        return

    body_text = (text or "").strip()
    if not body_text:
        logging.warning("Empty message; skipping send.")
        return

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body_text[:4096],
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(GRAPH_API_URL, headers=headers, json=data)
        if r.status_code != 200:
            logging.error("WA send failed [%s]: %s", r.status_code, r.text)
        r.raise_for_status()

# ──────────────── llamada interna al micro-scraper ───────────────────
async def call_price_endpoint(product: str) -> dict:
    url = f"http://127.0.0.1:{INTERNAL_PORT}{settings.API_V1_STR}/price"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"product": product})
        r.raise_for_status()
        return r.json()

# ────────────────────────── Webhooks WA ──────────────────────────────
@app.get("/webhook", tags=["webhook"])
async def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge") or "")
    return PlainTextResponse("error", status_code=status.HTTP_403_FORBIDDEN)

@app.post("/webhook", tags=["webhook"])
async def receive(request: Request):
    body = await request.json()
    logging.info(body)

    try:
        msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
    except (KeyError, IndexError):
        return {"status": "ignored"}

    user_text = msg.get("text", {}).get("body", "") or ""
    wid       = msg.get("from", "")

    # — 1ª pasada GPT —
    first_rsp = await chat_gpt(user_text)
    choice    = first_rsp.choices[0]
    logging.info("First GPT finish_reason: %s", choice.finish_reason)

    if choice.finish_reason == "tool_call":
        args    = json.loads(choice.message.tool_call.arguments)
        product = args.get("product", user_text)

        try:
            price_json = await call_price_endpoint(product)
        except Exception as exc:
            logging.exception("Error en /price: %s", exc)
            price_json = {"price": "#", "product": product, "error": str(exc)}

        # — 2ª pasada: formatear resultado JSON —
        format_prompt = {
            "role": "system",
            "content": (
                "Eres un formateador: recibes un JSON con el precio encontrado "
                "y debes devolver únicamente un texto en español, en guaraníes (Gs), "
                "incluyendo el precio y aclarando si es estimado. No repitas JSON."
            ),
        }
        json_msg = {"role": "user", "content": json.dumps(price_json, ensure_ascii=False)}

        second_rsp = await asyncio.to_thread(
            openai.chat.completions.create,
            model="gpt-4o-mini",
            messages=[format_prompt, json_msg],
            max_tokens=250,
        )
        answer = (second_rsp.choices[0].message.content or "").strip()
        logging.info("Second GPT answer: %r", answer)
    else:
        answer = (choice.message.content or "").strip()

    logging.info("GPT reply to send: %r", answer)
    await send_whatsapp(wid, answer)
    return {"status": "ok"}
