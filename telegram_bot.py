# telegram_monitor.py
from telethon import TelegramClient, events
import asyncio
import re
import httpx

API_ID = 38522841
API_HASH = "c8758751e087a5d736d71501cd82af26"

# Реальные каналы с pump.fun calls
CHANNELS = [
    "bestcallsolana",      # Best Calls Solana
    "pumpfunalerts",       # Pump.fun alerts
    "solanagems",          # Solana gems
    "farmercistjournal",   # 47k подписчиков, ранние дропы
    "basedkookcalls",      # 18k подписчиков, ранние тренды
    "dextoolssolanapumps", # DEXTools Solana pumps
    "solana_calls",        # Solana calls
    "pumpfun_gems",        # Pump.fun gems
]

# Паттерн адреса Solana
SOLANA_ADDRESS_PATTERN = r'[1-9A-HJ-NP-Za-km-z]{32,44}'

# Ключевые слова для фильтрации
BUY_KEYWORDS = [
    "pump.fun", "pumpfun", "CA:", "contract:", 
    "🚀", "gem", "buy", "launch", "new token",
    "solana", "SOL", "mint:"
]

async def check_elon_twitter(buy_callback, positions):
    """Мониторим X канал Маска через Telegram бот"""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                # Проверяем последние твиты через nitter
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
        await asyncio.sleep(30)  # проверяем каждые 30 секунд

async def start_telegram_monitor(buy_callback, positions):
    client = TelegramClient("pump_monitor", API_ID, API_HASH)
    await client.start()
    print(f"Telegram мониторинг запущен | Каналов: {len(CHANNELS)}")

    @client.on(events.NewMessage(chats=CHANNELS))
    async def handler(event):
        text = event.message.text or ""
        
        # Проверяем наличие ключевых слов
        has_keyword = any(kw.lower() in text.lower() for kw in BUY_KEYWORDS)
        if not has_keyword:
            return

        # Ищем адрес монеты
        addresses = re.findall(SOLANA_ADDRESS_PATTERN, text)
        
        for address in addresses:
            if len(address) >= 32 and address not in positions:
                channel = event.chat.username or "unknown"
                print(f"🎯 [{channel}] Найден адрес: {address}")
                print(f"Сообщение: {text[:150]}")
                
                data = {
                    "mint": address,
                    "name": f"TG_{channel[:8]}_{address[:6]}",
                    "solAmount": 1.0,
                    "marketCapSol": 100,
                    "traderPublicKey": "",
                    "pool": "pump"
                }
                await buy_callback(address, data)

    # Запускаем мониторинг Маска параллельно
    asyncio.ensure_future(check_elon_twitter(buy_callback, positions))
    
    await client.run_until_disconnected()
