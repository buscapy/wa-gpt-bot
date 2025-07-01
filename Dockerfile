FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── AÑADE ESTA LÍNEA ─────────────────────────
ENV PYTHONPATH="/app/backend:${PYTHONPATH}"
# ──────────────────────────────────────────────

COPY . .

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "10000"]
