# backend/app/main.py
# mypy: ignore-errors

import os
import json
import logging
from typing import Any, Dict, List

import sentry_sdk
import openai                      # SDK oficial de OpenAI
import httpx                       # Cliente HTTP async
from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.v1.price import router as price_router
from app.core.config import settings
from app.gpt.tools import price_function          # ← definición de la tool

# ---------------------------------------------------------------------------
# configuración general de FastAPI
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# rutas básicas
# ---------------------------------------------------------------------------

@app.get("/ping", tags=["health"])
def ping() -> Dict[str, str]:
    return {"message": "pong"}

@app.get("/", tags=["root"])
def read_root() -> Dict[str, str]:
    return {"message": "Welcome to wa-gpt-bot API"}

# API routers
app.include_router(api_router,   prefix=settings.API_V1_STR)
app.include_router(price_router, prefix=settings.API_V1_STR, tags=["price"])

# ---------------------------------------------------------------------------
# variables de entorno (WhatsApp Cloud API)
# ---------------------------------------------------------------------------

VERIFY_TOKEN   = os.getenv("WA_VERIFY_TOKEN", "olindarivas")
PHONE_ID       = os.getenv("WA_PHONE_NUMBER_ID")
ACCESS_TOKEN   = os.getenv("WA_ACCESS_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

GRAPH_API_URL  = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
INTERNAL_PORT  = os.getenv("PORT", "10000")                     # Render PORT

# prompt fijo para ChatGPT
SYSTEM_PROMPT = (
    "Eres un asistente conciso en español. "
    "Cuando el usuario pida un precio real usa la función get_price."
)

# ---------------------------------------------------------------------------
# 1) helper para la 1ª llamada a GPT (con tools)
# ---------------------------------------------------------------------------

async def chat_gpt(user_text: str) -> Any:
    """
    Llamada a GPT-4o con la tool declarada.  Devolvemos el objeto completo
    para inspeccionar finish_reason y posibles tool_calls.
    """
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_text},
        ],
        tools=[price_function],
        tool_choice="auto",
        max_tokens=300,
    )
    return rsp


# ---------------------------------------------------------------------------
# 2) enviar mensaje a WhatsApp
# ---------------------------------------------------------------------------

async def send_whatsapp(to: str, text: str) -> None:
    """
    Envía `text` (<= 4096 caracteres) al número `to` mediante WhatsApp Cloud API.
    """
    if not (PHONE_ID and ACCESS_TOKEN):
        logging.warning("WA credentials missing; skipping send.")
        return

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to":   to,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(GRAPH_API_URL, headers=headers, json=data)
        r.raise_for_status()


# ---------------------------------------------------------------------------
# 3) llamada interna al endpoint /api/v1/price  (nuestro scraper)
# ---------------------------------------------------------------------------

async def call_price_endpoint(product: str) -> Dict[str, Any]:
    """
    Envía {"product": ...} al endpoint interno /price y devuelve el JSON.
    """
    url = f"http://127.0.0.1:{INTERNAL_PORT}{settings.API_V1_STR}/price"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"product": product})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# 4) Webhook (WhatsApp Cloud API)
# ---------------------------------------------------------------------------

@app.get("/webhook", tags=["webhook"])
async def verify(request: Request):
    """
    Verificación inicial de Facebook (GET).
    """
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge") or "")
    return PlainTextResponse("error", status_code=status.HTTP_403_FORBIDDEN)


@app.post("/webhook", tags=["webhook"])
async def receive(request: Request):
    """
    1. Recibe evento de WhatsApp.
    2. Pasa el texto a GPT (con tools).
    3. Si GPT pide get_price ➜ llama a /price y hace una 2ª consulta.
    4. Envía la respuesta final al usuario.
    """
    body = await request.json()
    logging.info(body)

    # --- extraer mensaje entrante ---
    try:
        msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
    except (KeyError, IndexError):
        return {"status": "ignored"}          # no es mensaje de texto normal

    user_text: str = msg["text"]["body"]
    wid:       str = msg["from"]             # WhatsApp ID del usuario

    # -----------------------------------------------------------------------
    # PRIMERA llamada a GPT
    # -----------------------------------------------------------------------
    first_rsp  = await chat_gpt(user_text)
    choice     = first_rsp.choices[0]

    # La API 2024-05-01 usa finish_reason = "tool_calls" (plural)
    is_tool_call = (
        choice.finish_reason == "tool_calls"
        or (choice.message and getattr(choice.message, "tool_calls", None))
    )

    if is_tool_call:
        # ---------------------------------------------------------------
        # GPT solicitó get_price → ejecutamos el scraper
        # ---------------------------------------------------------------
        tool_call   = choice.message.tool_calls[0]
        args        = json.loads(tool_call.function.arguments)
        product     = args["product"]

        try:
            price_json = await call_price_endpoint(product)
        except Exception as exc:
            logging.exception("Error en /price: %s", exc)
            price_json = {"error": str(exc), "product": product}

        # ---------------------------------------------------------------
        # SEGUNDA llamada a GPT: formatear la respuesta final
        # ---------------------------------------------------------------
        second_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_text},
            # assistant indica que llamó a la función
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id":        tool_call.id,
                        "type":      "function",
                        "function": {
                            "name":       "get_price",
                            "arguments":  tool_call.function.arguments,
                        },
                    }
                ],
                "content": None,
            },
            # respuesta de la función
            {
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "name":         "get_price",
                "content":      json.dumps(price_json),
            },
        ]

        second_rsp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=second_messages,
            max_tokens=200,
        )
        answer = (second_rsp.choices[0].message.content or "").strip()

    else:
        # GPT contestó directamente (sin tool)
        answer = (choice.message.content or "").strip()

    # -----------------------------------------------------------------------
    # enviar al usuario
    # -----------------------------------------------------------------------
    logging.info("GPT reply: %s", answer)
    await send_whatsapp(wid, answer)

    return {"status": "ok"}
