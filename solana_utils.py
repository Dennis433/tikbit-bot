import requests
import config

def is_valid_solana_address(address: str) -> bool:
    try:
        if len(address) < 32 or len(address) > 44:
            return False
        valid_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        return all(c in valid_chars for c in address)
    except Exception:
        return False

def get_transaction(tx_signature: str) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            tx_signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0
            }
        ]
    }
    try:
        response = requests.post(config.RPC_URL, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"RPC Error: {e}")
        return None

def verify_payment(tx_signature: str, sender_wallet: str) -> dict:
    result = {
        "success": False,
        "amount_sol": 0,
        "message": ""
    }

    tx_data = get_transaction(tx_signature)

    if not tx_data:
        result["message"] = "❌ Could not reach Solana network. Try again."
        return result

    if "error" in tx_data or tx_data.get("result") is None:
        result["message"] = "❌ Transaction not found. Make sure it is confirmed."
        return result

    tx = tx_data["result"]

    if tx.get("meta", {}).get("err") is not None:
        result["message"] = "❌ Transaction failed on-chain."
        return result

    account_keys = tx["transaction"]["message"]["accountKeys"]
    addresses = [acc["pubkey"] for acc in account_keys]

    if sender_wallet not in addresses:
        result["message"] = "❌ Your wallet does not match this transaction."
        return result

    if config.PRESALE_WALLET not in addresses:
        result["message"] = "❌ Payment was not sent to the presale wallet."
        return result

    pre_balances = tx["meta"]["preBalances"]
    post_balances = tx["meta"]["postBalances"]

    try:
        presale_index = addresses.index(config.PRESALE_WALLET)
        pre = pre_balances[presale_index]
        post = post_balances[presale_index]
        amount_lamports = post - pre
        amount_sol = amount_lamports / 1_000_000_000

        if amount_sol <= 0:
            result["message"] = "❌ No SOL was received by the presale wallet."
            return result

        if amount_sol < config.MIN_BUY_SOL:
            result["message"] = f"❌ Minimum buy is {config.MIN_BUY_SOL} SOL. You sent {amount_sol:.4f} SOL."
            return result

        if amount_sol > config.MAX_BUY_SOL:
            result["message"] = f"❌ Maximum buy is {config.MAX_BUY_SOL} SOL. You sent {amount_sol:.4f} SOL."
            return result

        result["success"] = True
        result["amount_sol"] = amount_sol
        result["message"] = f"✅ Payment of {amount_sol:.4f} SOL verified!"
        return result

    except Exception as e:
        result["message"] = f"❌ Error reading transaction: {str(e)}"
        return result

def get_presale_wallet_balance() -> float:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [config.PRESALE_WALLET]
    }
    try:
        response = requests.post(config.RPC_URL, json=payload, timeout=10)
        data = response.json()
        lamports = data["result"]["value"]
        return lamports / 1_000_000_000
    except Exception as e:
        print(f"Balance fetch error: {e}")
        return 0.0
