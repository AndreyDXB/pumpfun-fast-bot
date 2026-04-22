import asyncio
import httpx
import os
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.pubkey import Pubkey
import base58

PUMPPORTAL_API = "https://pumpportal.fun/api/trade-local"
JITO_ENDPOINT = "https://mainnet.block-engine.jito.labs.io/api/v1/bundles"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

_buying = set()
_selling = set()

async def send_jito_bundle(transactions: list, keypairs: list, rpc_url: str) -> str:
    signed_txs = []
    for tx_bytes, keypair in zip(transactions, keypairs):
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        signed_txs.append(signed_tx)

    encoded = [
        base58.b58encode(bytes(tx)).decode("utf-8")
        for tx in signed_txs
    ]

    async with httpx.AsyncClient() as client:
        r = await client.post(
            JITO_ENDPOINT,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [encoded]
            },
            timeout=15
        )
        result = r.json()
        if "error" in result:
            raise Exception(f"Jito ошибка: {result['error']}")
        return result.get("result", "unknown")

async def check_token_balance(mint: str, pubkey: str, rpc_url: str) -> float:
    try:
        rpc = AsyncClient(rpc_url)
        result = await rpc.get_token_accounts_by_owner(
            Pubkey.from_string(pubkey),
            {"mint": Pubkey.from_string(mint)}
        )
        await rpc.close()
        if result.value:
            balance = result.value[0].account.data.parsed["info"]["tokenAmount"]["uiAmount"]
            return float(balance or 0)
        return 0
    except:
        return 0

async def buy(mint: str, data: dict, keypair: Keypair, rpc_url: str,
              buy_amount: float, positions: dict, save_fn, tg_fn) -> bool:
    if mint in positions:
        return False
    if len(positions) >= 3:
        return False
    if mint in _buying:
        print(f"Уже покупается: {data.get('name')}")
        return False

    _buying.add(mint)
    try:
        name = data.get("name", mint[:8])
        entry_mcap_sol = data.get("marketCapSol", 0)
        entry_mcap_usd = entry_mcap_sol * 86

        if DRY_RUN:
            # Симуляция покупки
            print(f"[DRY RUN] Симуляция покупки: {name}")
            positions[mint] = {
                "entry_mcap_sol": entry_mcap_sol,
                "entry_mcap_usd": entry_mcap_usd,
                "name": name,
                "buy_tx": "DRY_RUN",
                "time": datetime.utcnow().isoformat(),
            }
            await save_fn(positions)
            msg = (f"[ТЕСТ] КУПЛЕНО: {name}\n"
                   f"MCap: ${entry_mcap_usd:.0f}\n"
                   f"SOL: {buy_amount} (симуляция)\n"
                   f"TX: DRY_RUN")
            print(msg)
            await tg_fn(msg)
            return True

        # Реальная покупка через Jito
        payload = [
            {
                "publicKey": str(keypair.pubkey()),
                "action": "buy",
                "mint": mint,
                "amount": buy_amount,
                "denominatedInSol": "true",
                "slippage": 50,
                "priorityFee": 0.001,
                "pool": "pump"
            }
        ]

        async with httpx.AsyncClient() as client:
            r = await client.post(PUMPPORTAL_API, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"API ошибка: {r.status_code} | {r.text}")
                return False

        try:
            tx_list = r.json()
            if isinstance(tx_list, list):
                sig = await send_jito_bundle(
                    [bytes.fromhex(tx) if isinstance(tx, str) else tx for tx in tx_list],
                    [keypair] * len(tx_list),
                    rpc_url
                )
            else:
                raise ValueError("Не список")
        except:
            tx = VersionedTransaction.from_bytes(r.content)
            signed_tx = VersionedTransaction(tx.message, [keypair])
            rpc = AsyncClient(rpc_url)
            result = await rpc.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, preflight_commitment="processed")
            )
            await rpc.close()
            sig = str(result.value)

        print(f"TX: {str(sig)[:20]}... Проверяем баланс...")
        await asyncio.sleep(8)

        balance = await check_token_balance(mint, str(keypair.pubkey()), rpc_url)
        if balance <= 0:
            print(f"Покупка failed — токены не получены: {name}")
            return False

        positions[mint] = {
            "entry_mcap_sol": entry_mcap_sol,
            "entry_mcap_usd": entry_mcap_usd,
            "name": name,
            "buy_tx": str(sig)[:20],
            "time": datetime.utcnow().isoformat(),
        }
        await save_fn(positions)

        msg = (f"КУПЛЕНО: {name}\n"
               f"MCap: ${entry_mcap_usd:.0f}\n"
               f"SOL: {buy_amount}\n"
               f"Токенов: {balance:.0f}\n"
               f"TX: {str(sig)[:20]}...")
        print(msg)
        await tg_fn(msg)
        return True

    except Exception as e:
        print(f"Покупка ошибка: {e}")
        return False
    finally:
        _buying.discard(mint)

async def sell(mint: str, reason: str, current_mcap_sol: float,
               keypair: Keypair, rpc_url: str, buy_amount: float,
               positions: dict, trade_history: list,
               save_fn, save_history_fn, tg_fn) -> bool:
    if mint not in positions:
        return False
    if mint in _selling:
        print(f"Уже продаётся: {positions.get(mint, {}).get('name')}")
        return False

    _selling.add(mint)
    try:
        pos = positions.pop(mint, {})
        await save_fn(positions)

        name = pos.get("name", mint[:8])
        entry_mcap_sol = pos.get("entry_mcap_sol", 0)
        entry_mcap_usd = pos.get("entry_mcap_usd", 0)
        exit_mcap_usd = current_mcap_sol * 86
        change = ((current_mcap_sol - entry_mcap_sol) / entry_mcap_sol * 100) if entry_mcap_sol > 0 else 0
        pnl_sol = buy_amount * (change / 100)
        emoji = "✅" if change > 0 else "❌"

        if DRY_RUN:
            print(f"[DRY RUN] Симуляция продажи: {name}")
            msg = (f"[ТЕСТ] ПРОДАНО ({reason}): {name}\n"
                   f"Вход: ${entry_mcap_usd:.0f} -> Выход: ${exit_mcap_usd:.0f}\n"
                   f"Результат: {emoji} {change:+.1f}% ({pnl_sol:+.4f} SOL)\n"
                   f"TX: DRY_RUN")
            print(msg)
            await tg_fn(msg)
            trade_history.append({
                "name": name,
                "change": change,
                "pnl_sol": pnl_sol,
                "reason": reason,
                "time": datetime.utcnow().isoformat(),
            })
            await save_history_fn(trade_history)
            return True

        # Реальная продажа
        payload = [
            {
                "publicKey": str(keypair.pubkey()),
                "action": "sell",
                "mint": mint,
                "amount": "100%",
                "denominatedInSol": "false",
                "slippage": 50,
                "priorityFee": 0.001,
                "pool": "pump"
            }
        ]

        async with httpx.AsyncClient() as client:
            r = await client.post(PUMPPORTAL_API, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"API ошибка продажи: {r.status_code}")
                return False

        try:
            tx_list = r.json()
            if isinstance(tx_list, list):
                sig = await send_jito_bundle(
                    [bytes.fromhex(tx) if isinstance(tx, str) else tx for tx in tx_list],
                    [keypair] * len(tx_list),
                    rpc_url
                )
            else:
                raise ValueError("Не список")
        except:
            tx = VersionedTransaction.from_bytes(r.content)
            signed_tx = VersionedTransaction(tx.message, [keypair])
            rpc = AsyncClient(rpc_url)
            result = await rpc.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, preflight_commitment="processed")
            )
            await rpc.close()
            sig = str(result.value)

        msg = (f"ПРОДАНО ({reason}): {name}\n"
               f"Вход: ${entry_mcap_usd:.0f} -> Выход: ${exit_mcap_usd:.0f}\n"
               f"Результат: {emoji} {change:+.1f}% ({pnl_sol:+.4f} SOL)\n"
               f"TX: {str(sig)[:20]}...")
        print(msg)
        await tg_fn(msg)

        trade_history.append({
            "name": name,
            "change": change,
            "pnl_sol": pnl_sol,
            "reason": reason,
            "time": datetime.utcnow().isoformat(),
        })
        await save_history_fn(trade_history)
        return True

    except Exception as e:
        print(f"Продажа ошибка: {e}")
        return False
    finally:
        _selling.discard(mint)
