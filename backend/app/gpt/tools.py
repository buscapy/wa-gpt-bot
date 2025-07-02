# app/gpt/tools.py
# ------------------------------------------------------------------
# Definición de la “tool” que OpenAI espera para invocar tu scraper.
# Importar nada extra: basta con exponer el dict `price_function`.
# ------------------------------------------------------------------

price_function = {
    "type": "function",        # ✅ OpenAI 1.x exige este wrapper
    "function": {
        "name": "get_price",
        "description": "Devuelve el precio actual de un producto en Paraguay",
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Nombre del producto a buscar, en español"
                }
            },
            "required": ["product"]
        },
    },
}
