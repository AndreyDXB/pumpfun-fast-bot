import asyncio
import json
import websockets
from filters import is_good_token_basic

watching = {}

WATCH_SECONDS = 60
MIN_WALLETS = 5
MIN_VOLUME_SOL = 0.3
MAX_PRICE_DROP = 0.20
MAX_SINGLE_HOLDER_PERCENT = 40.0  # в конце наблюдения
INSTANT_WHALE_PERCENT = 80.0      # мгновенная блокировка только явных китов

PUMP_WS = "wss://pumpportal.fun/api/data"

async def watch_token(mint: str, initial_data: dict, callback, positions: dict):
    if not is_good_token_basic(initial_data, positions):
        return

    start_price = initial_data.get("marketCapSol", 0)
    name = initial_data.get("name", mint[:8])
    creator = initial_data.get("traderPublicKey", "")

    watching[mint] = {
        "name": name,
        "start_price": start_price,
        "wallets": set(),
        "volume_sol": 0,
        "wallet_volumes": {},
        "current_price": start_price,
        "creator": creator,
        "creator_sold": False,
    }

    print(f"Наблюдаем: {name} | MCap: {start_price:.2f} SOL")

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
                name = data["name"]
                wallet_volumes = data["wallet_volumes"]

                price_change = ((current - start) / start) if start > 0 else 0

                print(f"Итог {name}: кошельков={wallets} | объём={volume:.3f} SOL | цена={price_change*100:.1f}%")

                if data["creator_sold"]:
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

                # Проверка концентрации в конце наблюдения
                if volume > 0:
                    for wallet, vol in wallet_volumes.items():
                        percent = (vol / volume) * 100
                        if percent > MAX_SINGLE_HOLDER_PERCENT:
                            print(f"Концентрация! {wallet[:8]}... держит {percent:.1f}% — пропускаем {name}")
                            watching.pop(mint, None)
                            return

                print(f"ПОДХОДИТ: {name} | кошельков={wallets} | объём={volume:.3f} SOL | цена={price_change*100:.1f}%")
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
                        if trader not in watching[mint]["wallet_volumes"]:
                            watching[mint]["wallet_volumes"][trader] = 0
                        watching[mint]["wallet_volumes"][trader] += sol_amount

                        # Мгновенно блокируем только явных китов >80%
                        total = watching[mint]["volume_sol"]
                        if total > 0.5:
                            trader_vol = watching[mint]["wallet_volumes"][trader]
                            percent = (trader_vol / total) * 100
                            if percent > INSTANT_WHALE_PERCENT:
                                print(f"Явный кит! {trader[:8]}... купил {percent:.1f}% — пропускаем {watching[mint]['name']}")
                                watching.pop(mint, None)
                                break

                    if current_mcap > 0:
                        watching[mint]["current_price"] = current_mcap

                except Exception as e:
                    print(f"Ошибка наблюдения: {e}")

    except Exception as e:
        print(f"WS наблюдения ошибка: {e}")
        watching.pop(mint, None)
