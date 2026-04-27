import requests
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot_state = {
    "running": True,
    "buy_amount": 0.01,
    "take_profit": 0.25,
    "stop_loss": 0.15,
    "daily_loss": 0.0,
    "max_daily_loss": 0.5,
    "total_pnl": 0.0,
}

async def send_message(text: str):
    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            }, timeout=15)
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

async def poll_updates(positions, trade_history):
    import httpx
    last_update_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params={
                    "offset": last_update_id + 1,
                    "timeout": 10
                }, timeout=15)
                updates = r.json().get("result", [])
                for update in updates:
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip().lower()
                    if text == "/stop":
                        bot_state["running"] = False
                        await send_message("🛑 Бот остановлен")
                    elif text == "/start":
                        bot_state["running"] = True
                        await send_message("✅ Бот запущен")
                    elif text == "/status":
                        status = "✅ Работает" if bot_state["running"] else "🛑 Остановлен"
                        await send_message(
                            f"Статус: {status}\n"
                            f"Позиций: {len(positions)}\n"
                            f"PnL: {bot_state['total_pnl']:+.4f} SOL"
                        )
        except Exception as e:
            print(f"Poll ошибка: {e}")
        import asyncio
        await asyncio.sleep(2)
