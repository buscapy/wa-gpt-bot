import os
import logging

import sentry_sdk
import openai                # ← SDK oficial de OpenAI
import httpx                 # ← cliente HTTP async (ya está en requirements.txt de FastAPI, si no lo añades)
from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
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

# CORS si lo necesitas
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Endpoints básicos de salud
@app.get("/ping", tags=["health"])
def ping() -> dict:
    return {"message": "pong"}

@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": "Welcome to wa-gpt-bot API"}

# Router principal (endpoints de tu proyecto)
app.include_router(api_router, prefix=settings.API_V1_STR)


# ---------- Variables de entorno necesarias ---------- #
VERIFY_TOKEN      = os.getenv("WA_VERIFY_TOKEN", "olindarivas")
PHONE_ID          = os.getenv("WA_PHONE_NUMBER_ID")      # la obtienes en Meta Step 1
ACCESS_TOKEN      = os.getenv("WA_ACCESS_TOKEN")         # token temporal o permanente
openai.api_key    = os.getenv("OPENAI_API_KEY")          # clave de OpenAI
GRAPH_API_URL     = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"


# ---------- Utilidades GPT y WhatsApp ---------- #
async def chat_gpt(user_text: str) -> str:
    """Pide una respuesta a GPT-4o Mini (puedes cambiar de modelo)."""
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": "Eres un asistente conciso en español."},
            {"role": "user", "content": user_text}
        ],
        max_tokens=300
    )
    return rsp.choices[0].message.content.strip()


async def send_whatsapp(to: str, text: str):
    """Envía texto a un usuario de WhatsApp."""
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},      # 4096 = límite de WhatsApp
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(GRAPH_API_URL, headers=headers, json=data)
        r.raise_for_status()               # si falla, lanza excepción


# ---------- Webhook de WhatsApp Cloud API ---------- #
@app.get("/webhook", tags=["webhook"])
async def verify(request: Request):
    """
    Meta valida la URL con un GET único.
    Recibimos: hub.mode, hub.verify_token, hub.challenge
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
async def receive(request: Request):
    """
    Recibe mensajes entrantes.
    • Extrae el texto.
    • Pregunta a GPT.
    • Responde al mismo usuario.
    """
    body = await request.json()
    logging.info(body)                     # ver JSON entrante en Logs

    try:
        msg   = body["entry"][0]["changes"][0]["value"]["messages"][0]
        text  = msg["text"]["body"]
        wid   = msg["from"]               # WhatsApp ID del usuario

        reply = await chat_gpt(text)
        await send_whatsapp(wid, reply)

    except Exception as exc:
        logging.exception("Error procesando mensaje: %s", exc)

    # WhatsApp exige 200 OK rápidamente aunque haya errores internos
    return {"status": "ok"}
@app.post("/webhook", tags=["webhook"])
async def receive(request: Request):
    """
    • Extrae el texto entrante.
    • Pide respuesta a GPT.
    • La envía a WhatsApp.
    • (Opcional) La devuelve en el body cuando DEBUG_ECHO=true
      o cuando el header X-Debug: 1 esté presente.
    """
    body = await request.json()
    logging.info(body)

    gpt_reply = ""
    try:
        msg   = body["entry"][0]["changes"][0]["value"]["messages"][0]
        text  = msg["text"]["body"]
        wid   = msg["from"]

        gpt_reply = await chat_gpt(text)
        logging.info("GPT reply: %s", gpt_reply)

        await send_whatsapp(wid, gpt_reply)

    except Exception as exc:
        logging.exception("Error procesando mensaje: %s", exc)

    # ---------- decidir qué devolver ----------
    debug_env   = os.getenv("DEBUG_ECHO", "false").lower() == "true"
    debug_header = request.headers.get("x-debug") == "1"

    if debug_env or debug_header:
        # Mostrar también el texto de GPT
        return {"status": "ok", "gpt_reply": gpt_reply}

    # Respuesta mínima para Meta
    return {"status": "ok"}
