# Фильтры для отбора монет

MIN_INITIAL_BUY_SOL = 1.0    # минимальная начальная покупка создателя
MAX_INITIAL_BUY_SOL = 20.0   # максимальная (слишком большая = подозрительно)
MIN_MCAP_USD = 1000           # минимальный MCap в USD
MAX_MCAP_USD = 15000          # максимальный MCap в USD

sol_price_usd = 86.0

def is_good_token(data: dict, positions: dict) -> bool:
    try:
        if len(positions) >= 3:
            print("Максимум позиций (3)")
            return False

        mint = data.get("mint", "")
        name = data.get("name", "Unknown")

        # Проверка начальной покупки создателя
        initial_buy_sol = data.get("solAmount", 0) or 0
        if initial_buy_sol < MIN_INITIAL_BUY_SOL:
            print(f"Слабый старт: {initial_buy_sol:.3f} SOL | {name}")
            return False
        if initial_buy_sol > MAX_INITIAL_BUY_SOL:
            print(f"Подозрительный старт: {initial_buy_sol:.1f} SOL | {name}")
            return False

        # Проверка MCap
        market_cap_sol = data.get("marketCapSol", 0) or 0
        market_cap_usd = market_cap_sol * sol_price_usd
        if market_cap_usd < MIN_MCAP_USD or market_cap_usd > MAX_MCAP_USD:
            print(f"MCap не подходит: ${market_cap_usd:.0f} | {name}")
            return False

        # Проверка что не honeypot — токен должен быть на pump pool
        pool = data.get("pool", "")
        if pool and pool != "pump":
            print(f"Не pump pool: {pool} | {name}")
            return False

        print(f"ПОДХОДИТ: {name} | MCap: ${market_cap_usd:.0f} | Старт: {initial_buy_sol:.2f} SOL")
        return True

    except Exception as e:
        print(f"Ошибка фильтра: {e}")
        return False
