price_function = {
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
    }
}
