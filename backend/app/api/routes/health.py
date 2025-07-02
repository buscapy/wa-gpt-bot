# backend/app/api/routes/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/ping", include_in_schema=False)
def ping() -> dict[str, str]:
    """Ruta de salud usada por Render."""
    return {"message": "pong"}
