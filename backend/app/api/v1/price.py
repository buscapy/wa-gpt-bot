from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.openai_helper import get_price_url
from app.scrapers.basic import scrape

router = APIRouter()


# ---------- Esquemas de entrada / salida ---------- #
class PriceIn(BaseModel):
    product: str


class PriceOut(BaseModel):
    product: str
    results: list        # lo que devuelva el scraper
    source_url: str


# ---------- Endpoint /api/v1/price ---------- #
@router.post("/price", response_model=PriceOut, tags=["price"])
async def get_price(payload: PriceIn):
    """
    Recibe:   { "product": "heladera no frost" }

    1. Genera la URL de búsqueda.
    2. Ejecuta el scraper.
    3. Devuelve JSON con:
       • product
       • results  (lista de precios / tiendas)
       • source_url
    """
    product = payload.product.strip()
    if not product:
        raise HTTPException(status_code=400, detail="Falta el campo 'product'")

    url = get_price_url(product)
    scraped = scrape(url)        # ⬅️ tu función existente

    return {
        "product":   product,
        "results":   scraped,
        "source_url": url,
    }
