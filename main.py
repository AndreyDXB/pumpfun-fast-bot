import asyncio
import httpx
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from solders.keypair import Keypair
from monitor import monitor_new_tokens
from buyer import buy, sell

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
BUY_AMOUNT = float(os.getenv("BUY_AMOUNT", 0.01))
TAKE_PROFIT = float(os.getenv("TAKE_PROFIT", 0.50))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.25))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

keypair = Keypair.from_base58_string(PRIVATE_KEY)

POSITIONS_FILE = "positions.json"
HISTORY_FILE = "history.json"

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_positions(data):
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения позиций: {e}")

def save_history(data):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения истории: {e}")

positions = load_json(POSITIONS_FILE, {})
trade_history = load_json(HISTORY_FILE, [])
if isinstance(trade_history, dict):
    trade_history = []
print(f"Загружено позиций: {len(positions)}")

async def tg(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=5
            )
    except Exception as e:
        print(f"Telegram ошибка: {e}")

async def buy_token(mint: str, data: dict):
    await buy(
        mint=mint, data=data, keypair=keypair, rpc_url=RPC_URL,
        buy_amount=BUY_AMOUNT, positions=positions,
        save_fn=save_positions, tg_fn=tg
    )

async def sell_token(mint: str, reason: str, current_mcap_sol: float):
    await sell(
        mint=mint, reason=reason, current_mcap_sol=current_mcap_sol,
        keypair=keypair, rpc_url=RPC_URL, buy_amount=BUY_AMOUNT,
        positions=positions, trade_history=trade_history,
        save_fn=save_positions, save_history_fn=save_history, tg_fn=tg
    )

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
                        if change >= TAKE_PROFIT:
                            await sell_token(mint, f"TP +{change*100:.0f}%", current_mcap_sol)
                        elif change <= -STOP_LOSS:
                            await sell_token(mint, f"SL {change*100:.0f}%", current_mcap_sol)

                        # Если позиции изменились — переподключаемся
                        if set(positions.keys()) != set(mints):
                            print("Позиции изменились — переподключение")
                            break
                    except Exception as e:
                        print(f"Ошибка трейда: {e}")
        except Exception as e:
            print(f"WS позиции ошибка: {e}")
            await asyncio.sleep(2)

async def daily_report():
    while True:
        await asyncio.sleep(86400)
        if not trade_history:
            await tg("Суточный отчёт: сделок не было")
            continue
        total = len(trade_history)
        wins = [t for t in trade_history if t["change"] > 0]
        losses = [t for t in trade_history if t["change"] <= 0]
        total_pnl = sum(t["pnl_sol"] for t in trade_history)
        win_rate = len(wins) / total * 100
        msg = (f"СУТОЧНЫЙ ОТЧЁТ\n"
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
        save_history(trade_history)

async def main():
    print(f"Fast Bot! BUY={BUY_AMOUNT} SOL | TP={TAKE_PROFIT*100:.0f}% | SL={STOP_LOSS*100:.0f}%")
    print(f"RPC: {RPC_URL[:40]}...")
    await tg(f"Fast Pumpfun бот запущен!\nBUY={BUY_AMOUNT} SOL | TP={TAKE_PROFIT*100:.0f}% | SL={STOP_LOSS*100:.0f}%")
    await asyncio.gather(
        monitor_new_tokens(buy_token, positions),
        monitor_positions(),
        daily_report()
    )

if __name__ == "__main__":
    asyncio.run(main())
