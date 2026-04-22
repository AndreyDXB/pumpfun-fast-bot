import asyncio
import httpx
import os
import json
import redis.asyncio as aioredis
from datetime import datetime
from dotenv import load_dotenv
from solders.keypair import Keypair
from monitor import monitor_new_tokens
from buyer import buy, sell
from telegram_bot import bot_state, poll_updates, send_message
from copy_trading import monitor_copy_trading, add_wallet, remove_wallet

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

keypair = Keypair.from_base58_string(PRIVATE_KEY)

redis_client = None
positions = {}
trade_history = []

async def init_redis():
    global redis_client, positions, trade_history
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pos_data = await redis_client.get("positions")
    if pos_data:
        positions.update(json.loads(pos_data))
        print(f"Загружено позиций из Redis: {len(positions)}")
    else:
        print("Позиций в Redis нет")
    hist_data = await redis_client.get("trade_history")
    if hist_data:
        trade_history.extend(json.loads(hist_data))
        print(f"Загружено сделок из Redis: {len(trade_history)}")

async def save_positions(data):
    if redis_client:
        await redis_client.set("positions", json.dumps(data))

async def save_history(data):
    if redis_client:
        await redis_client.set("trade_history", json.dumps(data))

async def tg(text: str):
    await send_message(text)

async def buy_token(mint: str, data: dict):
    if not bot_state["running"]:
        print("Бот остановлен — пропускаем покупку")
        return
    if bot_state["daily_loss"] >= bot_state["max_daily_loss"]:
        print(f"Достигнут лимит потерь — бот остановлен")
        bot_state["running"] = False
        await tg(f"🛑 Авто-стоп! Потери достигли {bot_state['max_daily_loss']} SOL за день")
        return

    await buy(
        mint=mint,
        data=data,
        keypair=keypair,
        rpc_url=RPC_URL,
        buy_amount=bot_state["buy_amount"],
        positions=positions,
        save_fn=save_positions,
        tg_fn=tg
    )

async def sell_token(mint: str, reason: str, current_mcap_sol: float):
    result = await sell(
        mint=mint,
        reason=reason,
        current_mcap_sol=current_mcap_sol,
        keypair=keypair,
        rpc_url=RPC_URL,
        buy_amount=bot_state["buy_amount"],
        positions=positions,
        trade_history=trade_history,
        save_fn=save_positions,
        save_history_fn=save_history,
        tg_fn=tg
    )
    if result and trade_history:
        last = trade_history[-1]
        bot_state["total_pnl"] += last["pnl_sol"]
        if last["pnl_sol"] < 0:
            bot_state["daily_loss"] += abs(last["pnl_sol"])

async def monitor_positions():
    import websockets
    PUMP_WS = "wss://pumpportal.fun/api/data"
    while True:
        if not positions:
            await asyncio.sleep(1)
            continue
        try:
            async with websockets.connect(PUMP_WS, ping_interval=10, ping_timeout=5) as ws:
                mints = list(positions.keys())
                for mint in mints:
                    await ws.send(json.dumps({
                        "method": "subscribeTokenTrade",
                        "keys": [mint]
                    }))
                    print(f"Слежу за: {positions[mint]['name']}")

                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        mint = data.get("mint")
                        if not mint or mint not in positions:
                            continue
                        current_mcap_sol = data.get("marketCapSol", 0) or 0
                        if current_mcap_sol == 0:
                            continue
                        entry_mcap_sol = positions[mint]["entry_mcap_sol"]
                        change = (current_mcap_sol - entry_mcap_sol) / entry_mcap_sol
                        name = positions[mint]["name"]
                        print(f"{name}: {change*100:.1f}%")
                        if change >= bot_state["take_profit"]:
                            await sell_token(mint, f"TP +{change*100:.0f}%", current_mcap_sol)
                        elif change <= -bot_state["stop_loss"]:
                            await sell_token(mint, f"SL {change*100:.0f}%", current_mcap_sol)

                        if set(positions.keys()) != set(mints):
                            print("Позиции изменились — переподключение")
                            break
                    except Exception as e:
                        print(f"Ошибка трейда: {e}")
        except Exception as e:
            print(f"WS позиции ошибка: {e}")
            await asyncio.sleep(2)

async def daily_reset():
    while True:
        await asyncio.sleep(86400)
        bot_state["daily_loss"] = 0.0
        bot_state["total_pnl"] = 0.0
        bot_state["running"] = True
        if not trade_history:
            await tg("📊 Суточный отчёт: сделок не было")
            continue
        total = len(trade_history)
        wins = [t for t in trade_history if t["change"] > 0]
        losses = [t for t in trade_history if t["change"] <= 0]
        total_pnl = sum(t["pnl_sol"] for t in trade_history)
        win_rate = len(wins) / total * 100
        msg = (f"📊 СУТОЧНЫЙ ОТЧЁТ\n"
               f"Сделок: {total}\n"
               f"Прибыльных: {len(wins)} | Убыточных: {len(losses)}\n"
               f"Winrate: {win_rate:.0f}%\n"
               f"PnL: {total_pnl:+.4f} SOL\n")
        if wins:
            best = max(wins, key=lambda t: t["change"])
            msg += f"Лучшая: {best['name']} {best['change']:+.1f}%\n"
        if losses:
            worst = min(losses, key=lambda t: t["change"])
            msg += f"Худшая: {worst['name']} {worst['change']:+.1f}%"
        await tg(msg)
        trade_history.clear()
        await save_history(trade_history)

async def process_extra_commands(text: str):
    if text.startswith("/addwallet "):
        wallet = text.split()[1]
        add_wallet(wallet)
        await tg(f"✅ Кошелёк добавлен для copy trading: {wallet[:8]}...")
    elif text.startswith("/removewallet "):
        wallet = text.split()[1]
        remove_wallet(wallet)
        await tg(f"✅ Кошелёк удалён: {wallet[:8]}...")
    elif text == "/wallets":
        from copy_trading import TOP_WALLETS
        if not TOP_WALLETS:
            await tg("📭 Нет кошельков для copy trading")
        else:
            msg = "👛 Кошельки для copy trading:\n"
            for w in list(TOP_WALLETS)[:10]:
                msg += f"• {w[:8]}...\n"
            await tg(msg)

async def main():
    await init_redis()
    BUY_AMOUNT = float(os.getenv("BUY_AMOUNT", 0.01))
    TAKE_PROFIT = float(os.getenv("TAKE_PROFIT", 0.50))
    STOP_LOSS = float(os.getenv("STOP_LOSS", 0.25))
    bot_state["buy_amount"] = BUY_AMOUNT
    bot_state["take_profit"] = TAKE_PROFIT
    bot_state["stop_loss"] = STOP_LOSS

    print(f"Fast Bot! BUY={BUY_AMOUNT} SOL | TP={TAKE_PROFIT*100:.0f}% | SL={STOP_LOSS*100:.0f}%")
    print(f"RPC: {RPC_URL[:40]}...")
    await tg(f"🚀 Pumpfun бот запущен!\nBUY={BUY_AMOUNT} SOL | TP={TAKE_PROFIT*100:.0f}% | SL={STOP_LOSS*100:.0f}%\n\nКоманды: /menu")
    await asyncio.gather(
        monitor_new_tokens(buy_token, positions),
        monitor_copy_trading(buy_token, positions),
        monitor_positions(),
        daily_reset(),
        poll_updates(positions, trade_history)
    )

if __name__ == "__main__":
    asyncio.run(main())
