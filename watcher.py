import httpx

MIN_INITIAL_BUY_SOL = 0.5
MAX_INITIAL_BUY_SOL = 20.0
MIN_MCAP_USD = 0          # убираем MCap фильтр
MAX_MCAP_USD = 50000
MAX_CREATOR_PERCENT = 20.0
TOTAL_SUPPLY = 1_000_000_000
sol_price_usd = 86.0

async def check_anti_rug(mint: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary",
                timeout=5
            )
            if r.status_code != 200:
                return True, "API недоступен — пропускаем проверку"
            data = r.json()
            risks = data.get("risks", [])
            for risk in risks:
                risk_name = risk.get("name", "")
                level = risk.get("level", "")
                if level == "danger":
                    return False, f"Danger risk: {risk_name}"
                if "freeze" in risk_name.lower():
                    return False, "Токен можно заморозить"
                if "mint" in risk_name.lower() and level in ["warn", "danger"]:
                    return False, "Mint authority не отозван"
                if "top holders" in risk_name.lower() and level == "danger":
                    return False, "Концентрация у топ холдеров"
            score = data.get("score", 0)
            if score < 500:
                return False, f"Низкий rug score: {score}"
            return True, f"OK (score: {score})"
    except Exception as e:
        return True, f"Ошибка проверки: {e}"


def is_good_token_basic(data: dict, positions: dict) -> bool:
    try:
        if len(positions) >= 3:
            print("Максимум позиций (3)")
            return False

        name = data.get("name", "Unknown")

        initial_buy_sol = data.get("solAmount", 0) or 0
        if initial_buy_sol < MIN_INITIAL_BUY_SOL:
            print(f"Слабый старт: {initial_buy_sol:.3f} SOL | {name}")
            return False
        if initial_buy_sol > MAX_INITIAL_BUY_SOL:
            print(f"Подозрительный старт: {initial_buy_sol:.1f} SOL | {name}")
            return False

        pool = data.get("pool", "")
        if pool and pool != "pump":
            print(f"Не pump pool: {pool} | {name}")
            return False

        return True

    except Exception as e:
        print(f"Ошибка фильтра: {e}")
        return False
