# app/api/v1/price.py

import time
import logging
import asyncio
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Union

from app.services.openai_helper import get_price_url, format_price_msg
from app.scrapers.basic import scrape

router = APIRouter()

@router.post("/price", response_model=Dict[str, Any])
async def get_price(body: Dict[str, Any]):
    """
    Recibe {"product": "<nombre>"}.
    Devuelve {"messages": [...]} o {"messages": [], "error":"no_data"}.
    """
    product = body.get("product", "").strip()
    if not product:
        raise HTTPException(status_code=400, detail="Falta el parámetro product")

    url = get_price_url(product)

    start = time.time()
    logging.info("→ /price called for product=%r", product)

    try:
        # Ejecutamos el scraper en un hilo para no bloquear el event loop
        data: Union[List[Dict], Dict] = await asyncio.to_thread(scrape, url)
    except Exception as e:
        logging.exception("Error interno en scraper")
        # Si el scraper falla, devolvemos rápidamente sin bloquear cliente
        return {"messages": [], "error": str(e)}
    finally:
        logging.info("← /price responded in %.2fs", time.time() - start)

    # Detectamos la bandera de "sin datos"
    if isinstance(data, dict) and data.get("price") == "#":
        return {"messages": [], "error": "no_data"}

    if not isinstance(data, list):
        logging.error("Scraper devolvió formato inesperado: %r", data)
        raise HTTPException(status_code=500, detail="Formato de datos inesperado")

    messages: List[str] = format_price_msg(product, data)
    return {"messages": messages}
