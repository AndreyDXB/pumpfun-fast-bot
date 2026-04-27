import asyncio
import re
import httpx
from datetime import datetime, timezone

SOLANA_ADDRESS_PATTERN = r'[1-9A-HJ-NP-Za-km-z]{44}'

CHANNELS = [
    "bestcallsolana",
    "solanagems",
    "solana_calls",
    "pumpfun_gems",
    "farmercistjournal",
]

seen_addresses = set()

async def is_fresh_token(address: str) -> bool:
    """Проверяем что монета создана менее 30 минут назад"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://frontend-api.pump.fun/coins/{address}",
                timeout=5
            )
            if r.status_code != 200:
                return False
            data = r.json()
            created_ts = data.get("created_timestamp", 0)
            if not created_ts:
                return False
            created = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
            print(f"Возраст монеты {address[:8]}: {age_minutes:.0f} мин")
            return age_minutes < 30  # только свежие монеты
    except Exception as e:
        print(f"Ошибка проверки возраста: {e}")
        return False

async def fetch_channel(channel: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://t.me/s/{channel}",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            return r.text
    except Exception as e:
        print(f"Ошибка чтения канала {channel}: {e}")
        return ""

async def check_elon_twitter(buy_callback, positions):
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://nitter.net/elonmusk/rss",
                    timeout=10
                )
                text = r.text
                addresses = re.findall(SOLANA_ADDRESS_PATTERN, text)
                for address in addresses:
                    if address not in positions and address not in seen_addresses:
                        if await is_fresh_token(address):
                            seen_addresses.add(address)
                            print(f"🎯 ELON MUSK упомянул свежий адрес: {address}")
                            data = {
                                "mint": address,
                                "name": f"ELON_{address[:8]}",
                                "solAmount": 1.0,
                                "marketCapSol": 100,
                                "traderPublicKey": "",
                                "pool": "pump"
                            }
                            await buy_callback(address, data)
        except Exception as e:
            print(f"Ошибка мониторинга Elon: {e}")
        await asyncio.sleep(30)

async def monitor_channel(channel: str, buy_callback, positions):
    while True:
        try:
            html = await fetch_channel(channel)
            addresses = re.findall(SOLANA_ADDRESS_PATTERN, html)
            for address in addresses:
                if address not in positions and address not in seen_addresses:
                    seen_addresses.add(address)
                    if await is_fresh_token(address):
                        print(f"🎯 [{channel}] Свежий адрес: {address}")
                        data = {
                            "mint": address,
                            "name": f"TG_{channel[:8]}_{address[:6]}",
                            "solAmount": 1.0,
                            "marketCapSol": 100,
                            "traderPublicKey": "",
                            "pool": "pump"
                        }
                        await buy_callback(address, data)
                    else:
                        print(f"⏰ [{channel}] Старая монета — пропускаем: {address[:8]}")
        except Exception as e:
            print(f"Ошибка канала {channel}: {e}")
        await asyncio.sleep(15)

async def start_telegram_monitor(buy_callback, positions):
    print(f"HTTP мониторинг каналов запущен | Каналов: {len(CHANNELS)}")
    tasks = [monitor_channel(ch, buy_callback, positions) for ch in CHANNELS]
    tasks.append(check_elon_twitter(buy_callback, positions))
    await asyncio.gather(*tasks)
