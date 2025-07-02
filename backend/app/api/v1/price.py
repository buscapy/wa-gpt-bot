from fastapi import APIRouter, Request
from app.services.openai_helper import get_price_url, format_price_msg
from app.scrapers.basic import scrape

router = APIRouter()

@router.post("/price")
async def get_price(request: Request):
    body = await request.json()
    msg = body.get("message", "")
    
    if not msg.lower().startswith("/precio "):
        return {"error": "Formato inválido. Usa /precio <producto>"}
    
    product = msg[len("/precio "):].strip()
    url = get_price_url(product)
    data = scrape(url)
    messages = format_price_msg(product, data)
    
    return {"messages": messages}
