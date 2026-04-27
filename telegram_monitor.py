from telethon import TelegramClient, events
import asyncio
import re
import httpx
import os

API_ID = 38522841
API_HASH = "c8758751e087a5d736d71501cd82af26"
PHONE = os.getenv("TELEGRAM_PHONE")  # добавим в Railway переменные

CHANNELS = [
    "bestcallsolana",
    "pumpfunalerts",
    "solanagems",
    "farmercistjournal",
    "basedkookcalls",
    "dextoolssolanapumps",
    "solana_calls",
    "pumpfun_gems",
]

SOLANA_ADDRESS_PATTERN = r'[1-9A-HJ-NP-Za-km-z]{32,44}'

BUY_KEYWORDS = [
    "pump.fun", "pumpfun", "CA:", "contract:",
    "🚀", "gem", "buy", "launch", "new token",
    "solana", "SOL", "mint:"
]

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
                    if len(address) >= 32 and address not in positions:
                        print(f"🎯 ELON MUSK упомянул адрес: {address}")
                        data = {
                            "mint": address,
                            "name": f"ELON_CALL_{address[:8]}",
                            "solAmount": 1.0,
                            "marketCapSol": 100,
                            "traderPublicKey": "",
                            "pool": "pump"
                        }
                        await buy_callback(address, data)
        except Exception as e:
            print(f"Ошибка мониторинга Elon: {e}")
        await asyncio.sleep(30)

async def start_telegram_monitor(buy_callback, positions):
    try:
        client = TelegramClient("pump_monitor", API_ID, API_HASH)
        await client.start(phone=PHONE)
        print(f"Telegram мониторинг запущен | Каналов: {len(CHANNELS)}")

        @client.on(events.NewMessage(chats=CHANNELS))
        async def handler(event):
            text = event.message.text or ""
            has_keyword = any(kw.lower() in text.lower() for kw in BUY_KEYWORDS)
            if not has_keyword:
                return
            addresses = re.findall(SOLANA_ADDRESS_PATTERN, text)
            for address in addresses:
                if len(address) >= 32 and address not in positions:
                    channel = event.chat.username or "unknown"
                    print(f"🎯 [{channel}] Найден адрес: {address}")
                    data = {
                        "mint": address,
                        "name": f"TG_{channel[:8]}_{address[:6]}",
                        "solAmount": 1.0,
                        "marketCapSol": 100,
                        "traderPublicKey": "",
                        "pool": "pump"
                    }
                    await buy_callback(address, data)

        asyncio.ensure_future(check_elon_twitter(buy_callback, positions))
        await client.run_until_disconnected()

    except Exception as e:
        print(f"Telegram monitor ошибка: {e} — продолжаем без мониторинга каналов")
