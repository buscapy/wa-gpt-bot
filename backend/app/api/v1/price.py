from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.openai_helper import get_price_url
from app.scrapers.basic import scrape

router = APIRouter()


class PriceIn(BaseModel):
    product: str


@router.post("/price")
async def get_price(payload: PriceIn) -> dict:
    """
    • Construye la URL con la ayuda de openai_helper
    • Lanza el scraper
    • Devuelve:

        – {"price":"#", "product": … }               si el scraper no halló datos
        – {"price": "...", "shop": "...", ... }      con el primer match
    """
    url = get_price_url(payload.product)
    data = scrape(url)

    # ── 1) bandera “sin datos” ────────────────────────────────────────
    if isinstance(data, dict) and data.get("price") == "#":
        return {"price": "#", "product": payload.product}

    # ── 2) al menos un precio válido ──────────────────────────────────
    if isinstance(data, list) and data:
        first = data[0]
        first["product"] = payload.product
        return first

    # ── 3) cualquier otro caso inesperado ─────────────────────────────
    return {"price": "#", "product": payload.product}
