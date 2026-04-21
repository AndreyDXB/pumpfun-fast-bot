import asyncio
import httpx
import json
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

PUMPPORTAL_API = "https://pumpportal.fun/api/trade-local"

async def send_transaction(content: bytes, keypair: Keypair, rpc_url: str) -> str:
    tx = VersionedTransaction.from_bytes(content)
    signed_tx = VersionedTransaction(tx.message, [keypair])
    rpc = AsyncClient(rpc_url)
    try:
        result = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="processed")
        )
        return str(result.value)
    finally:
        await rpc.close()

async def buy(mint: str, data: dict, keypair: Keypair, rpc_url: str,
              buy_amount: float, positions: dict, save_fn, tg_fn) -> bool:
    if mint in positions:
        return False
    if len(positions) >= 3:
        return False
    try:
        payload = {
            "publicKey": str(keypair.pubkey()),
            "action": "buy",
            "mint": mint,
            "amount": buy_amount,
            "denominatedInSol": "true",
            "slippage": 50,
            "priorityFee": 0.005,
            "pool": "pump"
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(PUMPPORTAL_API, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"API ошибка: {r.status_code} | {r.text}")
                return False

        sig = await send_transaction(r.content, keypair, rpc_url)
        name = data.get("name", mint[:8])
        entry_mcap_sol = data.get("marketCapSol", 0)
        entry_mcap_usd = entry_mcap_sol * 86

        positions[mint] = {
            "entry_mcap_sol": entry_mcap_sol,
            "entry_mcap_usd": entry_mcap_usd,
            "name": name,
            "buy_tx": sig,
            "time": datetime.utcnow().isoformat(),
        }
        save_fn(positions)

        msg = (f"КУПЛЕНО: {name}\n"
               f"MCap: ${entry_mcap_usd:.0f}\n"
               f"SOL: {buy_amount}\n"
               f"TX: {sig[:20]}...")
        print(msg)
        await tg_fn(msg)
        return True

    except Exception as e:
        print(f"Покупка ошибка: {e}")
        return False

async def sell(mint: str, reason: str, current_mcap_sol: float,
               keypair: Keypair, rpc_url: str, buy_amount: float,
               positions: dict, trade_history: list, save_fn, save_history_fn, tg_fn) -> bool:
    try:
        payload = {
            "publicKey": str(keypair.pubkey()),
            "action": "sell",
            "mint": mint,
            "amount": "100%",
            "denominatedInSol": "false",
            "slippage": 50,
            "priorityFee": 0.005,
            "pool": "pump"
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(PUMPPORTAL_API, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"API ошибка продажи: {r.status_code}")
                return False

        sig = await send_transaction(r.content, keypair, rpc_url)
        pos = positions.pop(mint, {})
        save_fn(positions)

        name = pos.get("name", mint[:8])
        entry_mcap_sol = pos.get("entry_mcap_sol", 0)
        entry_mcap_usd = pos.get("entry_mcap_usd", 0)
        exit_mcap_usd = current_mcap_sol * 86
        change = ((current_mcap_sol - entry_mcap_sol) / entry_mcap_sol * 100) if entry_mcap_sol > 0 else 0
        pnl_sol = buy_amount * (change / 100)
        emoji = "✅" if change > 0 else "❌"

        msg = (f"ПРОДАНО ({reason}): {name}\n"
               f"Вход: ${entry_mcap_usd:.0f} -> Выход: ${exit_mcap_usd:.0f}\n"
               f"Результат: {emoji} {change:+.1f}% ({pnl_sol:+.4f} SOL)\n"
               f"TX: {sig[:20]}...")
        print(msg)
        await tg_fn(msg)

        trade_history.append({
            "name": name,
            "change": change,
            "pnl_sol": pnl_sol,
            "reason": reason,
            "time": datetime.utcnow().isoformat(),
        })
        save_history_fn(trade_history)
        return True

    except Exception as e:
        print(f"Продажа ошибка: {e}")
        return False
