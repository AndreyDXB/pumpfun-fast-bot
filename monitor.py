import asyncio
import json
import websockets
import httpx
from filters import is_good_token, sol_price_usd
import filters

PUMP_WS = "wss://pumpportal.fun/api/data"

async def update_sol_price():
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
                    timeout=5
                )
                filters.sol_price_usd = float(r.json()["price"])
                print(f"SOL: ${filters.sol_price_usd:.2f}")
        except Exception as e:
            print(f"Цена SOL ошибка: {e}")
        await asyncio.sleep(30)

async def monitor_new_tokens(callback, positions: dict):
    print("Мониторинг запущен...")
    asyncio.ensure_future(update_sol_price())
    while True:
        try:
            async with websockets.connect(
                PUMP_WS,
                ping_interval=10,
                ping_timeout=5
            ) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                print("WebSocket подключён")
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        mint = data.get("mint")
                        if not mint:
                            continue
                        name = data.get("name", "Unknown")
                        print(f"Новая: {name}")
                        if is_good_token(data, positions):
                            asyncio.ensure_future(callback(mint, data))
                    except Exception as e:
                        print(f"Ошибка обработки: {e}")
        except Exception as e:
            print(f"WS ошибка: {e}, переподключение...")
            await asyncio.sleep(3)
