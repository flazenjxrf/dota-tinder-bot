# 🎮 FeedEther — Dota Tinder

Телеграм-бот + Mini App для поиска тиммейтов в Dota 2.

### Стек
- **Python** (aiogram 3 + FastAPI в одном процессе)
- **PostgreSQL** + SQLAlchemy 2 async
- **Docker** / **Railway**

### Railway (как у тебя сейчас)
1. Пушь в git — билдится `Dockerfile`, старт: `python -m bot`.
2. В сервисе должен быть **публичный HTTP** (Settings → Networking → Generate Domain).
3. `WEBAPP_URL` можно не задавать: возьмётся `https://$RAILWAY_PUBLIC_DOMAIN`.
4. В BotFather → Bot Settings → Domain укажи тот же домен (без `https://`).

Один контейнер слушает `$PORT` (Mini App) и параллельно крутит polling бота. Команды в чате работают как раньше.

### Локально
```bash
cp .env.example .env   # BOT_TOKEN
docker compose up -d --build
# Mini App: http://localhost:8080 (для Telegram нужен HTTPS-туннель)
```
