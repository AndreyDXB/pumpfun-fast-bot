import asyncio
import json
import websockets
import httpx
from watcher import watch_token
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
                        initial_buy_sol = data.get("solAmount", 0) or 0

                        # Базовая проверка перед наблюдением
                        if initial_buy_sol < 0.5:
                            print(f"Слабый старт: {initial_buy_sol:.3f} SOL | {name}")
                            continue

                        if len(positions) >= 3:
                            print(f"Максимум позиций (3)")
                            continue

                        print(f"Новая: {name} | Старт: {initial_buy_sol:.2f} SOL — начинаем наблюдение")
                        asyncio.ensure_future(
                            watch_token(mint, data, callback, positions)
                        )

                    except Exception as e:
                        print(f"Ошибка обработки: {e}")
        except Exception as e:
            print(f"WS ошибка: {e}, переподключение...")
            await asyncio.sleep(3)
