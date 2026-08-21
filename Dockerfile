FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot /app/bot

EXPOSE 8080

# Бот + Mini App в одном процессе (Railway: PORT)
CMD ["python", "-m", "bot"]
