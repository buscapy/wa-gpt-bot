from datetime import date
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List

# ─── helpers ────────────────────────────────────────────────────────────────────
from app.services.openai_helper import get_price_url   # genera la URL de búsqueda
from app.scrapers.basic import scrape                  # hace el scraping real

router = APIRouter()


# ─── schema de salida ───────────────────────────────────────────────────────────
class PriceOut(BaseModel):
    price: str = Field(..., description="Precio formateado (ej. '2.450.000 Gs')")
    date: str = Field(..., description="Fecha YYYY-MM-DD")
    shop: str = Field(..., description="Tienda o marketplace")
    city: str = Field(..., description="Ciudad")


# ─── tiny helpers ───────────────────────────────────────────────────────────────
def pick_first(result: Any) -> Dict[str, Any]:
    """
    Normaliza la primera entrada independientemente de la forma que
    devuelva el scraper:

    • lista de dicts  → toma el primer elemento
    • dict plano      → lo devuelve tal cual si incluye 'price'
    • dict de dicts   → toma el primer value()
    """
    if isinstance(result, list):                        # [ {...}, {...} ]
        return result[0] if result else {}
    if isinstance(result, dict):
        if "price" in result:                           # {"price": "...", ...}
            return result
        # {"0": {...}, "1": {...}}  ó  {0: {...}}
        try:
            return next(iter(result.values()))
        except StopIteration:
            return {}
    return {}                                           # formato desconocido


# ─── endpoint /price ────────────────────────────────────────────────────────────
@router.post("/price", response_model=PriceOut, tags=["price"])
async def get_price(request: Request):
    """
    Body esperado:  { "product": "<texto del producto>" }

    Devuelve: PriceOut  (único dict con los campos normalizados)
    """
    body = await request.json()
    product: str = body.get("product", "").strip()

    if not product:
        raise HTTPException(400, detail="Campo 'product' requerido")

    url = get_price_url(product)        # 1) URL destino
    raw_results = scrape(url)           # 2) Scrape

    first = pick_first(raw_results)     # 3) Normalizar

    if not first or not first.get("price"):
        raise HTTPException(404, detail="Sin resultados")

    # 4) Completar campos y devolver
    return {
        "price": first.get("price", "N/D"),
        "date": first.get("date") or date.today().isoformat(),
        "shop": first.get("shop", "Desconocido"),
        "city": first.get("city", "Paraguay"),
    }
