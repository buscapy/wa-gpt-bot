# app/scrapers/basic.py

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Union

def scrape(url: str) -> Union[List[Dict], Dict]:
    """
    Devuelve:
      - Una lista de dicts con keys: price, date, shop, city.
      - Si no encuentra datos, devuelve {"price": "#"} como bandera.
    """
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results: List[Dict] = []
    # ————— Aquí va tu lógica existente de scraping —————
    # for element in soup.select("..."):
    #     price = ...
    #     date  = ...
    #     shop  = ...
    #     city  = ...
    #     results.append({
    #         "price": price,
    #         "date": date,
    #         "shop": shop,
    #         "city": city,
    #     })

    # Si no obtuvimos nada, devolvemos la bandera
    if not results:
        return {"price": "#"}

    return results
