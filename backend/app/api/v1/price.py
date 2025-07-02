from datetime import date
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

# ─── helpers propios ────────────────────────────────────────────────────────────
from app.services.openai_helper import get_price_url          # genera la URL
from app.scrapers.basic import scrape                         # hace el scraping

router = APIRouter()


# ─── schema de salida ───────────────────────────────────────────────────────────
class PriceOut(BaseModel):
    price: str = Field(..., description="Precio formateado, ej. '2.450.000 Gs'")
    date: str = Field(..., description="Fecha de obtención (YYYY-MM-DD)")
    shop: str = Field(..., description="Nombre de la tienda / marketplace")
    city: str = Field(..., description="Ciudad donde aplica el precio")


# ─── endpoint ───────────────────────────────────────────────────────────────────
@router.post("/price", response_model=PriceOut, tags=["price"])
async def get_price(request: Request):
    """
    Devuelve el mejor precio actual de un producto en Paraguay.

    Espera un JSON como:
        { "product": "lavarropas midea automatico" }

    Retorna un único dict (validado por PriceOut).  
    FastAPI se encarga de serializar la respuesta.
    """
    body = await request.json()
    product: str = body.get("product", "").strip()

    if not product:
        raise HTTPException(status_code=400, detail="Campo 'product' requerido")

    # 1️⃣ Construir URL de búsqueda
    url = get_price_url(product)

    # 2️⃣ Scrapear resultados
    results = scrape(url)  # ← debe devolver una lista de dicts compatibles

    if not results:
        raise HTTPException(status_code=404, detail="Sin resultados")

    # 3️⃣ Tomamos el primer resultado válido
    first = results[0]

    # 4️⃣ Aseguramos campos mínimos y devolvemos
    return {
        "price": first.get("price", "N/D"),
        "date": first.get("date") or date.today().isoformat(),
        "shop": first.get("shop", "Desconocido"),
        "city": first.get("city", "Paraguay"),
    }
