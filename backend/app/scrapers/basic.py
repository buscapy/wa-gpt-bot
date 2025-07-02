"""
Scraper MUY sencillo de ejemplo.
Extrae el primer precio encontrado o devuelve la bandera "#" si no hay resultados.
"""

from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup
from datetime import date

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )
}

price_re = re.compile(r"([\d\.]+)\s*gs", re.I)


def _extract_prices(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    texts = soup.get_text(" ", strip=True).split()
    joined = " ".join(texts)

    matches = price_re.finditer(joined)
    results: list[dict] = []

    for m in matches:
        value = m.group(1).replace(".", "")
        try:
            price_int = int(value)
        except ValueError:
            continue
        results.append(
            {
                "price": f"{price_int:,} Gs".replace(",", "."),
                "date": str(date.today()),
                "shop": "N/D",
                "city": "N/D",
            }
        )

    return results


def scrape(url: str) -> list[dict] | dict:
    """
    Devuelve una **lista de dicts** con precios.
    Si no encuentra nada ⇒ {"price": "#"}  ← bandera para el caller.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception:
        return {"price": "#"}

    results = _extract_prices(resp.text)
    return results if results else {"price": "#"}
