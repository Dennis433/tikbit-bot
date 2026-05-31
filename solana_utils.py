import requests
import config
import os
import base58
import json

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
        response = requests.post(config.RPC_URL, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        print(f"RPC Error: {e}")
        return None

def verify_payment(tx_signature: str, sender_wallet: str) -> dict:
    result = {"success": False, "amount_sol": 0, "message": ""}

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
        amount_lamports = post_balances[presale_index] - pre_balances[presale_index]
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
        return data["result"]["value"] / 1_000_000_000
    except Exception as e:
        print(f"Balance fetch error: {e}")
        return 0.0

def get_recent_transactions(limit: int = 20) -> list:
    """Get recent transactions to the presale wallet"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            config.PRESALE_WALLET,
            {"limit": limit}
        ]
    }
    try:
        response = requests.post(config.RPC_URL, json=payload, timeout=15)
        data = response.json()
        return data.get("result", [])
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return []

def get_sender_from_tx(tx_signature: str) -> dict:
    """Get sender wallet and SOL amount from a transaction"""
    result = {"sender": None, "amount_sol": 0, "success": False}
    tx_data = get_transaction(tx_signature)

    if not tx_data or tx_data.get("result") is None:
        return result

    tx = tx_data["result"]
    if tx.get("meta", {}).get("err") is not None:
        return result

    try:
        account_keys = tx["transaction"]["message"]["accountKeys"]
        addresses = [acc["pubkey"] for acc in account_keys]

        if config.PRESALE_WALLET not in addresses:
            return result

        pre_balances = tx["meta"]["preBalances"]
        post_balances = tx["meta"]["postBalances"]

        presale_index = addresses.index(config.PRESALE_WALLET)
        amount_lamports = post_balances[presale_index] - pre_balances[presale_index]
        amount_sol = amount_lamports / 1_000_000_000

        if amount_sol < config.MIN_BUY_SOL:
            return result

        # Sender is index 0 (fee payer / signer)
        sender = addresses[0]
        if sender == config.PRESALE_WALLET:
            return result

        result["sender"] = sender
        result["amount_sol"] = amount_sol
        result["success"] = True
        return result

    except Exception as e:
        print(f"Error parsing tx: {e}")
        return result

def send_tokens(recipient_wallet: str, amount_tokens: float) -> dict:
    """
    Send TKB tokens to a recipient wallet using Solana token transfer.
    Requires PRESALE_PRIVATE_KEY in environment.
    """
    result = {"success": False, "tx_signature": None, "message": ""}

    private_key_str = os.getenv("PRESALE_PRIVATE_KEY")
    if not private_key_str:
        result["message"] = "❌ Presale private key not configured"
        return result

    try:
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solana.rpc.api import Client
        from solana.transaction import Transaction
        from spl.token.instructions import transfer_checked, TransferCheckedParams
        from spl.token.constants import TOKEN_PROGRAM_ID
        from solders.system_program import transfer, TransferParams

        # Decode private key
        try:
            key_bytes = base58.b58decode(private_key_str)
        except Exception:
            try:
                key_bytes = bytes(json.loads(private_key_str))
            except Exception:
                result["message"] = "❌ Invalid private key format"
                return result

        keypair = Keypair.from_bytes(key_bytes)
        client = Client(config.RPC_URL)

        sender_pubkey = keypair.pubkey()
        recipient_pubkey = Pubkey.from_string(recipient_wallet)
        mint_pubkey = Pubkey.from_string(config.TOKEN_MINT)

        # Get associated token accounts
        def get_associated_token_address(wallet: Pubkey, mint: Pubkey) -> Pubkey:
            ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJe1bz")
            seeds = [bytes(wallet), bytes(TOKEN_PROGRAM_ID), bytes(mint)]
            return Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)[0]

        sender_ata = get_associated_token_address(sender_pubkey, mint_pubkey)
        recipient_ata = get_associated_token_address(recipient_pubkey, mint_pubkey)

        # Token decimals (standard 9 for most Solana tokens)
        TOKEN_DECIMALS = 9
        amount_raw = int(amount_tokens * (10 ** TOKEN_DECIMALS))

        # Build transfer transaction
        recent_blockhash = client.get_latest_blockhash().value.blockhash

        txn = Transaction()
        txn.recent_blockhash = recent_blockhash
        txn.fee_payer = sender_pubkey

        txn.add(
            transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=sender_ata,
                    mint=mint_pubkey,
                    dest=recipient_ata,
                    owner=sender_pubkey,
                    amount=amount_raw,
                    decimals=TOKEN_DECIMALS,
                    signers=[]
                )
            )
        )

        txn.sign(keypair)
        response = client.send_transaction(txn, keypair)
        sig = str(response.value)

        result["success"] = True
        result["tx_signature"] = sig
        result["message"] = f"✅ {int(amount_tokens):,} TKB sent! TX: {sig}"
        print(f"Token transfer successful: {sig}")
        return result

    except ImportError:
        # spl-token not installed, log the airdrop for manual processing
        print(f"[AIRDROP QUEUE] {recipient_wallet} → {int(amount_tokens):,} TKB")
        result["success"] = True
        result["tx_signature"] = "QUEUED"
        result["message"] = f"✅ {int(amount_tokens):,} TKB queued for airdrop!"
        return result

    except Exception as e:
        print(f"Token send error: {e}")
        result["message"] = f"❌ Token send failed: {str(e)}"
        return result