import asyncio
import json
import websockets
from datetime import datetime, timezone
from filters import check_anti_rug, is_good_token_basic

watching = {}

WATCH_SECONDS = 60
MIN_WALLETS = 10
MIN_VOLUME_SOL = 0.5
MAX_PRICE_DROP = 0.15

PUMP_WS = "wss://pumpportal.fun/api/data"

async def watch_token(mint: str, initial_data: dict, callback, positions: dict):
    # Базовая проверка
    if not is_good_token_basic(initial_data, positions):
        return

    start_price = initial_data.get("marketCapSol", 0)
    start_time = datetime.now(timezone.utc)
    name = initial_data.get("name", mint[:8])

    watching[mint] = {
        "name": name,
        "start_price": start_price,
        "start_time": start_time,
        "wallets": set(),
        "volume_sol": 0,
        "current_price": start_price,
        "creator": initial_data.get("traderPublicKey", ""),
        "creator_sold": False,
    }

    print(f"Наблюдаем: {name} | MCap: {start_price:.2f} SOL")

    # Анти-rug проверка сразу
    rug_ok, rug_reason = await check_anti_rug(mint)
    if not rug_ok:
        print(f"Анти-rug: {name} — {rug_reason}")
        watching.pop(mint, None)
        return
    print(f"Анти-rug OK: {name} — {rug_reason}")

    try:
        async with websockets.connect(PUMP_WS, ping_interval=10, ping_timeout=5) as ws:
            await ws.send(json.dumps({
                "method": "subscribeTokenTrade",
                "keys": [mint]
            }))

            async def check_timeout():
                await asyncio.sleep(WATCH_SECONDS)
                data = watching.get(mint)
                if not data:
                    return

                wallets = len(data["wallets"])
                volume = data["volume_sol"]
                current = data["current_price"]
                start = data["start_price"]
                creator_sold = data["creator_sold"]
                name = data["name"]

                price_change = ((current - start) / start) if start > 0 else 0

                print(f"Итог {name}: кошельков={wallets} | объём={volume:.3f} SOL | цена={price_change*100:.1f}%")

                if creator_sold:
                    print(f"Создатель продал — пропускаем {name}")
                    watching.pop(mint, None)
                    return
                if wallets < MIN_WALLETS:
                    print(f"Мало кошельков ({wallets}) — пропускаем {name}")
                    watching.pop(mint, None)
                    return
                if volume < MIN_VOLUME_SOL:
                    print(f"Мало объёма ({volume:.3f} SOL) — пропускаем {name}")
                    watching.pop(mint, None)
                    return
                if price_change < -MAX_PRICE_DROP:
                    print(f"Цена упала ({price_change*100:.1f}%) — пропускаем {name}")
                    watching.pop(mint, None)
                    return

                print(f"ПОДХОДИТ: {name} | кошельков={wallets} | объём={volume:.3f} SOL")
                watching.pop(mint, None)
                await callback(mint, {**initial_data, "marketCapSol": current})

            asyncio.ensure_future(check_timeout())

            async for msg in ws:
                try:
                    data = json.loads(msg)
                    if data.get("mint") != mint:
                        continue
                    if mint not in watching:
                        break

                    trader = data.get("traderPublicKey", "")
                    sol_amount = data.get("solAmount", 0) or 0
                    current_mcap = data.get("marketCapSol", 0) or 0
                    tx_type = data.get("txType", "")

                    if trader == watching[mint]["creator"] and tx_type == "sell":
                        watching[mint]["creator_sold"] = True
                        print(f"Создатель продаёт! Пропускаем {watching[mint]['name']}")
                        watching.pop(mint, None)
                        break

                    if tx_type == "buy":
                        watching[mint]["wallets"].add(trader)
                        watching[mint]["volume_sol"] += sol_amount

                    if current_mcap > 0:
                        watching[mint]["current_price"] = current_mcap

                except Exception as e:
                    print(f"Ошибка наблюдения: {e}")

    except Exception as e:
        print(f"WS наблюдения ошибка: {e}")
        watching.pop(mint, None)
