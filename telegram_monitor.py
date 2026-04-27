import asyncio
import re
import httpx

SOLANA_ADDRESS_PATTERN = r'[1-9A-HJ-NP-Za-km-z]{32,44}'

# Публичные каналы — читаем через web.telegram.org
CHANNELS = [
    "bestcallsolana",
    "solanagems", 
    "solana_calls",
    "pumpfun_gems",
    "farmercistjournal",
]

seen_addresses = set()

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
                    if len(address) >= 32 and address not in positions and address not in seen_addresses:
                        seen_addresses.add(address)
                        print(f"🎯 ELON MUSK упомянул адрес: {address}")
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
                if (len(address) >= 32 and 
                    address not in positions and 
                    address not in seen_addresses):
                    seen_addresses.add(address)
                    print(f"🎯 [{channel}] Новый адрес: {address}")
                    data = {
                        "mint": address,
                        "name": f"TG_{channel[:8]}_{address[:6]}",
                        "solAmount": 1.0,
                        "marketCapSol": 100,
                        "traderPublicKey": "",
                        "pool": "pump"
                    }
                    await buy_callback(address, data)
        except Exception as e:
            print(f"Ошибка канала {channel}: {e}")
        await asyncio.sleep(15)  # проверяем каждые 15 секунд

async def start_telegram_monitor(buy_callback, positions):
    print(f"HTTP мониторинг каналов запущен | Каналов: {len(CHANNELS)}")
    tasks = [monitor_channel(ch, buy_callback, positions) for ch in CHANNELS]
    tasks.append(check_elon_twitter(buy_callback, positions))
    await asyncio.gather(*tasks)
