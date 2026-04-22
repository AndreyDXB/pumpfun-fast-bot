import asyncio
import json
import websockets
import httpx

PUMP_WS = "wss://pumpportal.fun/api/data"

# Топовые кошельки для копирования — добавляй сюда успешных трейдеров
TOP_WALLETS = set()

# Минимальная сумма покупки топового трейдера чтобы копировать
MIN_COPY_SOL = 0.1

async def load_top_wallets():
    global TOP_WALLETS
    try:
        async with httpx.AsyncClient() as client:
            # Берём топ трейдеров с pump.fun leaderboard
            r = await client.get(
                "https://frontend-api.pump.fun/traders/summary?limit=20&type=weekly",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                for trader in data:
                    wallet = trader.get("user", "")
                    pnl = trader.get("realized_profit", 0) or 0
                    if wallet and pnl > 10:  # только с прибылью > 10 SOL
                        TOP_WALLETS.add(wallet)
                print(f"Загружено топ кошельков: {len(TOP_WALLETS)}")
            else:
                print(f"Leaderboard API недоступен: {r.status_code}")
    except Exception as e:
        print(f"Ошибка загрузки топ кошельков: {e}")

async def update_top_wallets():
    while True:
        await load_top_wallets()
        await asyncio.sleep(3600)  # обновляем каждый час

def add_wallet(wallet: str):
    TOP_WALLETS.add(wallet)
    print(f"Добавлен кошелёк для копирования: {wallet}")

def remove_wallet(wallet: str):
    TOP_WALLETS.discard(wallet)
    print(f"Удалён кошелёк: {wallet}")

async def monitor_copy_trading(callback, positions: dict):
    print("Copy trading запущен...")
    asyncio.ensure_future(update_top_wallets())

    while True:
        if not TOP_WALLETS:
            await asyncio.sleep(5)
            continue
        try:
            async with websockets.connect(
                PUMP_WS,
                ping_interval=10,
                ping_timeout=5
            ) as ws:
                # Подписываемся на сделки топ кошельков
                await ws.send(json.dumps({
                    "method": "subscribeAccountTrade",
                    "keys": list(TOP_WALLETS)
                }))
                print(f"Следим за {len(TOP_WALLETS)} кошельками")

                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        tx_type = data.get("txType", "")
                        trader = data.get("traderPublicKey", "")
                        mint = data.get("mint", "")
                        sol_amount = data.get("solAmount", 0) or 0

                        if tx_type != "buy":
                            continue
                        if sol_amount < MIN_COPY_SOL:
                            continue
                        if not mint:
                            continue
                        if mint in positions:
                            continue
                        if len(positions) >= 3:
                            continue

                        name = data.get("name", mint[:8])
                        print(f"Copy: {trader[:8]}... купил {name} на {sol_amount:.3f} SOL")
                        await callback(mint, data)

                    except Exception as e:
                        print(f"Ошибка copy trading: {e}")

        except Exception as e:
            print(f"WS copy trading ошибка: {e}")
            await asyncio.sleep(3)
