import asyncio
import httpx
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Состояние бота
bot_state = {
    "running": True,
    "take_profit": 0.50,
    "stop_loss": 0.25,
    "buy_amount": 0.01,
    "daily_loss": 0.0,
    "max_daily_loss": 0.05,
    "total_pnl": 0.0,
}

async def send_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=5
            )
    except Exception as e:
        print(f"Telegram ошибка: {e}")

async def send_keyboard(text: str, buttons: list):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    keyboard = {"inline_keyboard": [[{"text": b["text"], "callback_data": b["data"]} for b in row] for row in buttons]}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "reply_markup": keyboard,
                    "parse_mode": "HTML"
                },
                timeout=5
            )
    except Exception as e:
        print(f"Telegram keyboard ошибка: {e}")

async def process_command(text: str, positions: dict, trade_history: list):
    text = text.strip().lower()

    if text == "/start" or text == "/menu":
        await send_keyboard(
            "🤖 <b>Pumpfun Bot</b>\nВыбери действие:",
            [
                [{"text": "📊 Статус", "data": "status"}, {"text": "⏸ Стоп", "data": "stop"}],
                [{"text": "▶️ Старт", "data": "start"}, {"text": "💰 Позиции", "data": "positions"}],
                [{"text": "📈 История", "data": "history"}, {"text": "⚙️ Настройки", "data": "settings"}],
            ]
        )

    elif text == "/status" or text == "status":
        status = "✅ Работает" if bot_state["running"] else "⏸ Остановлен"
        msg = (
            f"🤖 <b>Статус бота</b>\n"
            f"Состояние: {status}\n"
            f"Позиций: {len(positions)}/3\n"
            f"TP: {bot_state['take_profit']*100:.0f}% | SL: {bot_state['stop_loss']*100:.0f}%\n"
            f"Размер: {bot_state['buy_amount']} SOL\n"
            f"PnL сегодня: {bot_state['total_pnl']:+.4f} SOL\n"
            f"Макс. потеря/день: {bot_state['max_daily_loss']} SOL"
        )
        await send_message(msg)

    elif text == "/stop" or text == "stop":
        bot_state["running"] = False
        await send_message("⏸ Бот остановлен — новые покупки заблокированы")

    elif text == "/start_bot" or text == "start":
        bot_state["running"] = True
        await send_message("▶️ Бот запущен — ищем монеты")

    elif text == "/positions" or text == "positions":
        if not positions:
            await send_message("📭 Открытых позиций нет")
            return
        msg = "💰 <b>Открытые позиции:</b>\n"
        for mint, pos in positions.items():
            msg += f"• {pos['name']} | вход: ${pos['entry_mcap_usd']:.0f}\n"
        await send_message(msg)

    elif text == "/history" or text == "history":
        if not trade_history:
            await send_message("📭 История пуста")
            return
        wins = [t for t in trade_history if t["change"] > 0]
        losses = [t for t in trade_history if t["change"] <= 0]
        total_pnl = sum(t["pnl_sol"] for t in trade_history)
        winrate = len(wins) / len(trade_history) * 100 if trade_history else 0
        msg = (
            f"📈 <b>История сделок</b>\n"
            f"Всего: {len(trade_history)}\n"
            f"Прибыльных: {len(wins)} | Убыточных: {len(losses)}\n"
            f"Winrate: {winrate:.0f}%\n"
            f"PnL: {total_pnl:+.4f} SOL"
        )
        await send_message(msg)

    elif text.startswith("/tp "):
        try:
            val = float(text.split()[1])
            bot_state["take_profit"] = val / 100
            await send_message(f"✅ Take Profit установлен: {val:.0f}%")
        except:
            await send_message("❌ Формат: /tp 50")

    elif text.startswith("/sl "):
        try:
            val = float(text.split()[1])
            bot_state["stop_loss"] = val / 100
            await send_message(f"✅ Stop Loss установлен: {val:.0f}%")
        except:
            await send_message("❌ Формат: /sl 25")

    elif text.startswith("/amount "):
        try:
            val = float(text.split()[1])
            bot_state["buy_amount"] = val
            await send_message(f"✅ Размер сделки: {val} SOL")
        except:
            await send_message("❌ Формат: /amount 0.01")

    elif text.startswith("/maxloss "):
        try:
            val = float(text.split()[1])
            bot_state["max_daily_loss"] = val
            await send_message(f"✅ Макс. потеря в день: {val} SOL")
        except:
            await send_message("❌ Формат: /maxloss 0.05")

    elif text == "/settings" or text == "settings":
        msg = (
            f"⚙️ <b>Настройки</b>\n"
            f"TP: {bot_state['take_profit']*100:.0f}% — изменить: /tp 50\n"
            f"SL: {bot_state['stop_loss']*100:.0f}% — изменить: /sl 25\n"
            f"Размер: {bot_state['buy_amount']} SOL — изменить: /amount 0.01\n"
            f"Макс. потеря: {bot_state['max_daily_loss']} SOL — изменить: /maxloss 0.05"
        )
        await send_message(msg)

    elif text == "/help":
        msg = (
            "📋 <b>Команды:</b>\n"
            "/menu — главное меню\n"
            "/status — статус бота\n"
            "/stop — остановить покупки\n"
            "/start_bot — запустить покупки\n"
            "/positions — открытые позиции\n"
            "/history — история сделок\n"
            "/tp 50 — установить Take Profit %\n"
            "/sl 25 — установить Stop Loss %\n"
            "/amount 0.01 — размер сделки SOL\n"
            "/maxloss 0.05 — макс. потеря в день SOL"
        )
        await send_message(msg)

async def poll_updates(positions: dict, trade_history: list):
    offset = 0
    print("Telegram бот запущен, ждём команды...")
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 10},
                    timeout=15
                )
                data = r.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    
                    # Обычное сообщение
                    if "message" in update:
                        text = update["message"].get("text", "")
                        chat_id = str(update["message"]["chat"]["id"])
                        if chat_id == str(TELEGRAM_CHAT_ID):
                            await process_command(text, positions, trade_history)
                    
                    # Нажатие кнопки
                    elif "callback_query" in update:
                        data_cb = update["callback_query"]["data"]
                        chat_id = str(update["callback_query"]["message"]["chat"]["id"])
                        if chat_id == str(TELEGRAM_CHAT_ID):
                            await process_command(data_cb, positions, trade_history)
                            # Подтверждаем нажатие кнопки
                            await client.post(
                                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                                json={"callback_query_id": update["callback_query"]["id"]},
                                timeout=5
                            )
        except Exception as e:
            print(f"Poll ошибка: {e}")
            await asyncio.sleep(3)
