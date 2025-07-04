# mypy: ignore-errors

# backend/app/services/openai_helper.py

import os
from openai import OpenAI, ChatCompletion

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

ELECTRO_KEYWORDS = [
    "heladera",
    "lavarropa",
    "microondas",
    "cocina",
    "licuadora",
    "plancha",
]


def get_price_url(product: str) -> str:
    lower = product.lower()
    if any(word in lower for word in ELECTRO_KEYWORDS):
        query = product.replace(" ", "+")
        return f"https://www.tupy.com.py/buscar?q={query}"

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
    """Use OpenAI to create two WhatsApp messages from price data."""

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
