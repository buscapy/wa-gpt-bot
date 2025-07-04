# mypy: ignore-errors

# backend/app/services/openai_helper.py

import os
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Palabras clave para identificar productos electrodomésticos.
ELECTRO_KEYWORDS = {
    "heladera",
    "lavadora",
    "lavarropas",
    "microondas",
    "cocina",
    "freezer",
    "licuadora",
    "secadora",
    "aspiradora",
    "plancha",
    "aire acondicionado",
}

def get_price_url(product: str) -> str:
    """Return a scraping URL for ``product`` using local heuristics."""

    query = product.strip()
    query_lower = query.lower()

    if any(keyword in query_lower for keyword in ELECTRO_KEYWORDS):
        search = query.replace(" ", "+")
        return f"https://www.tupy.com.py/search?q={search}"

    # Default to MercadoLibre search
    search = query.replace(" ", "-")
    return f"https://listado.mercadolibre.com.py/{search}"

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
