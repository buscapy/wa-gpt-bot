# backend/app/services/openai_helper.py

import os
import logging
from openai import OpenAI, ChatCompletion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    message = "OPENAI_API_KEY environment variable is not set"
    logger.error(message)
    raise RuntimeError(message)

client = OpenAI(api_key=OPENAI_API_KEY)

def get_price_url(product: str) -> str:
    prompt = (
        f"Dame una URL confiable para scrapear el mejor precio de “{product}” "
        "(MercadoLibre, Frávega, etc.). Responde solo con la URL."
    )
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()

def format_price_msg(product: str, data: dict) -> list[str]:
    prompt = (
        f"Tengo estos datos JSON sobre “{product}”: {data}. "
        "Escribe máximo dos mensajes de WhatsApp:"
        "1) precio y comercio"
        "2) recomendación breve"
    )
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user", "content": prompt}],
    )
    # Dividimos en líneas o mensajes
    return [m.strip() for m in resp.choices[0].message.content.split("\n") if m.strip()]
