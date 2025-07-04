# app/scrapers/basic.py

import logging
from datetime import datetime
from typing import List, Dict, Union

import requests
from bs4 import BeautifulSoup

def _parse_mercadolibre(soup: BeautifulSoup) -> List[Dict]:
    results: List[Dict] = []
    for card in soup.select("li.ui-search-layout__item"):
        price_el = card.select_one("span.andes-money-amount__fraction")
        if not price_el:
            continue
        city_el = card.select_one(
            "span.ui-search-item__group__element.ui-search-item__location"
        )
        shop_el = card.select_one("p.ui-search-official-store-label__text")
        results.append(
            {
                "price": price_el.get_text(strip=True),
                "date": datetime.utcnow().isoformat(),
                "shop": shop_el.get_text(strip=True) if shop_el else "MercadoLibre",
                "city": city_el.get_text(strip=True) if city_el else "",
            }
        )
    return results


def _parse_fravega(soup: BeautifulSoup) -> List[Dict]:
    results: List[Dict] = []
    for card in soup.select("div.card-product"):  # general card selector
        price_el = card.select_one(".card-product-price")
        if not price_el:
            continue
        results.append(
            {
                "price": price_el.get_text(strip=True),
                "date": datetime.utcnow().isoformat(),
                "shop": "Frávega",
                "city": "",
            }
        )
    return results


def scrape(url: str) -> Union[List[Dict], Dict]:
    """Extrae precios de la URL indicada.

    Devuelve una lista de dicts con keys: ``price``, ``date``, ``shop`` y
    ``city``. Si no se pudo extraer un precio devuelve ``{"price": "#"}``.
    """
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logging.exception("Network error while scraping %s", url)
        return {"price": "#"}

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        if "mercadolibre" in url.lower():
            results = _parse_mercadolibre(soup)
        elif "fravega" in url.lower():
            results = _parse_fravega(soup)
        else:
            logging.warning("Unknown site for URL: %s", url)
            results = []
    except Exception as exc:
        logging.exception("Parsing error for %s", url)
        return {"price": "#"}

    if not results:
        return {"price": "#"}

    return results

