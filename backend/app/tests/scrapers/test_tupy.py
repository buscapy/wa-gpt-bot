from bs4 import BeautifulSoup

from app.scrapers.basic import _parse_tupy


HTML = """
<div class="product-item">
  <span class="product-price">1.000</span>
</div>
<div class="product-item">
  <span class="product-price">2.000</span>
</div>
"""


def test_parse_tupy_extracts_prices() -> None:
    soup = BeautifulSoup(HTML, "html.parser")
    results = _parse_tupy(soup)
    assert len(results) == 2
    assert results[0]["price"] == "1.000"
    assert all(r["shop"] == "Tupy" for r in results)
