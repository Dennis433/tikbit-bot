import requests
import config
import os
import base58
import json
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# ADDRESS VALIDATION
# ─────────────────────────────────────────

def is_valid_solana_address(address: str) -> bool:
    try:
        if not address or len(address) < 32 or len(address) > 44:
            return False
        valid_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        return all(c in valid_chars for c in address)
    except Exception:
        return False


# ─────────────────────────────────────────
# RPC HELPERS
# ─────────────────────────────────────────

def _rpc(payload: dict, timeout: int = 15) -> dict | None:
    try:
        r = requests.post(config.RPC_URL, json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        logger.error(f"RPC error: {e}")
        return None


def get_transaction(tx_signature: str) -> dict | None:
    return _rpc({
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [tx_signature, {
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0
        }]
    })


def get_presale_wallet_balance() -> float:
    data = _rpc({
        "jsonrpc": "2.0", "id": 1,
        "method": "getBalance",
        "params": [config.PRESALE_WALLET]
    }, timeout=10)
    try:
        return data["result"]["value"] / 1_000_000_000
    except Exception:
        return 0.0


def get_airdrop_wallet_balance() -> float:
    """SOL balance of the airdrop wallet (needed for tx fees)."""
    data = _rpc({
        "jsonrpc": "2.0", "id": 1,
        "method": "getBalance",
        "params": [config.AIRDROP_WALLET]
    }, timeout=10)
    try:
        return data["result"]["value"] / 1_000_000_000
    except Exception:
        return 0.0


def get_token_balance(wallet_address: str) -> float:
    """Get TKB token balance of a wallet."""
    data = _rpc({
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"mint": config.TOKEN_MINT},
            {"encoding": "jsonParsed"}
        ]
    }, timeout=10)
    try:
        accounts = data["result"]["value"]
        if not accounts:
            return 0.0
        amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
        return float(amount or 0)
    except Exception:
        return 0.0


def get_recent_transactions(limit: int = 20) -> list:
    """Recent transactions sent TO the presale wallet."""
    data = _rpc({
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [config.PRESALE_WALLET, {"limit": limit}]
    })
    try:
        return data.get("result", [])
    except Exception:
        return []


# ─────────────────────────────────────────
# PAYMENT VERIFICATION
# ─────────────────────────────────────────

def verify_payment(tx_signature: str, sender_wallet: str) -> dict:
    """
    Verify a transaction sent to the presale wallet.
    Returns dict with success, amount_sol, message.
    """
    result = {"success": False, "amount_sol": 0, "message": ""}

    tx_data = get_transaction(tx_signature)
    if not tx_data:
        result["message"] = "❌ Could not reach Solana network. Try again."
        return result

    if "error" in tx_data or tx_data.get("result") is None:
        result["message"] = "❌ Transaction not found. Make sure it is confirmed on-chain."
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

    pre_balances  = tx["meta"]["preBalances"]
    post_balances = tx["meta"]["postBalances"]

    try:
        idx = addresses.index(config.PRESALE_WALLET)
        amount_lamports = post_balances[idx] - pre_balances[idx]
        amount_sol = amount_lamports / 1_000_000_000

        if amount_sol <= 0:
            result["message"] = "❌ No SOL was received by the presale wallet."
            return result
        if amount_sol < config.MIN_BUY_SOL:
            result["message"] = (
                f"❌ Minimum buy is {config.MIN_BUY_SOL} SOL. "
                f"You sent {amount_sol:.4f} SOL."
            )
            return result
        if amount_sol > config.MAX_BUY_SOL:
            result["message"] = (
                f"❌ Maximum buy is {config.MAX_BUY_SOL} SOL. "
                f"You sent {amount_sol:.4f} SOL."
            )
            return result

        result["success"]    = True
        result["amount_sol"] = amount_sol
        result["message"]    = f"✅ Payment of {amount_sol:.4f} SOL verified!"
        return result

    except Exception as e:
        result["message"] = f"❌ Error reading transaction: {str(e)}"
        return result


def get_sender_from_tx(tx_signature: str) -> dict:
    """
    Parse a transaction and return the sender wallet + SOL amount.
    Used by the auto-monitor.
    """
    result = {"sender": None, "amount_sol": 0, "success": False}
    tx_data = get_transaction(tx_signature)

    if not tx_data or tx_data.get("result") is None:
        return result

    tx = tx_data["result"]
    if tx.get("meta", {}).get("err") is not None:
        return result

    try:
        account_keys = tx["transaction"]["message"]["accountKeys"]
        addresses    = [acc["pubkey"] for acc in account_keys]

        if config.PRESALE_WALLET not in addresses:
            return result

        pre_balances  = tx["meta"]["preBalances"]
        post_balances = tx["meta"]["postBalances"]

        idx = addresses.index(config.PRESALE_WALLET)
        amount_lamports = post_balances[idx] - pre_balances[idx]
        amount_sol = amount_lamports / 1_000_000_000

        if amount_sol < config.MIN_BUY_SOL:
            return result

        # Sender is the fee payer (index 0)
        # Skip if sender is the presale wallet itself (internal tx)
        sender = addresses[0]
        if sender == config.PRESALE_WALLET:
            # Try index 1 as sender (some wallet types)
            if len(addresses) > 1:
                sender = addresses[1]
            else:
                return result

        result["sender"]     = sender
        result["amount_sol"] = amount_sol
        result["success"]    = True
        return result

    except Exception as e:
        logger.error(f"Error parsing tx {tx_signature}: {e}")
        return result


# ─────────────────────────────────────────
# TOKEN SENDING  (from AIRDROP_WALLET)
# ─────────────────────────────────────────

def _load_airdrop_keypair():
    """Load the airdrop wallet keypair from AIRDROP_PRIVATE_KEY env var."""
    key_str = config.AIRDROP_PRIVATE_KEY
    if not key_str:
        raise ValueError("AIRDROP_PRIVATE_KEY not set in environment variables")

    from solders.keypair import Keypair

    # Try base58 first, then JSON array
    try:
        key_bytes = base58.b58decode(key_str.strip())
        return Keypair.from_bytes(key_bytes)
    except Exception:
        pass

    try:
        key_bytes = bytes(json.loads(key_str.strip()))
        return Keypair.from_bytes(key_bytes)
    except Exception:
        pass

    raise ValueError(
        "AIRDROP_PRIVATE_KEY format not recognised. "
        "Use base58 string or JSON byte array [1,2,3,...]"
    )


def send_tokens(recipient_wallet: str, amount_tokens: float) -> dict:
    """
    Send TKB tokens using pure solders — no spl-token package needed.
    Builds transfer_checked instruction manually.
    Requires AIRDROP_PRIVATE_KEY in environment.
    """
    result = {"success": False, "tx_signature": None, "message": ""}

    if not config.AIRDROP_PRIVATE_KEY:
        logger.warning(f"[QUEUED] {recipient_wallet} → {int(amount_tokens):,} TKB — set AIRDROP_PRIVATE_KEY")
        result["success"]      = True
        result["tx_signature"] = "QUEUED"
        result["message"]      = f"✅ {int(amount_tokens):,} TKB queued — set AIRDROP_PRIVATE_KEY on Render"
        return result

    try:
        import struct, base64
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.hash import Hash
        from solders.instruction import Instruction, AccountMeta
        from solders.message import Message
        from solders.transaction import Transaction as SoldersTransaction

        keypair = _load_airdrop_keypair()
        sender_pubkey    = keypair.pubkey()
        recipient_pubkey = Pubkey.from_string(recipient_wallet)
        mint_pubkey      = Pubkey.from_string(config.TOKEN_MINT)
        amount_raw       = int(amount_tokens * (10 ** config.TOKEN_DECIMALS))

        TOKEN_PROGRAM_ID    = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        ASSOC_TOKEN_PROG_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJe1bz")
        SYSTEM_PROGRAM      = Pubkey.from_string("11111111111111111111111111111111")
        SYSVAR_RENT         = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

        def get_ata(owner: Pubkey, mint: Pubkey) -> Pubkey:
            seeds = [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)]
            return Pubkey.find_program_address(seeds, ASSOC_TOKEN_PROG_ID)[0]

        sender_ata    = get_ata(sender_pubkey, mint_pubkey)
        recipient_ata = get_ata(recipient_pubkey, mint_pubkey)

        logger.info(f"Sender ATA:    {sender_ata}")
        logger.info(f"Recipient ATA: {recipient_ata}")

        # Get latest blockhash
        bh_data = _rpc({
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}]
        })
        blockhash_str = bh_data["result"]["value"]["blockhash"]
        blockhash = Hash.from_string(blockhash_str)

        # Check if recipient ATA exists
        ata_info = _rpc({
            "jsonrpc": "2.0", "id": 1,
            "method": "getAccountInfo",
            "params": [str(recipient_ata), {"encoding": "base64"}]
        })
        needs_ata = ata_info["result"]["value"] is None

        instructions = []

        # Create recipient ATA if needed
        if needs_ata:
            logger.info(f"Creating ATA for {recipient_wallet}")
            ata_accounts = [
                AccountMeta(sender_pubkey,    True,  True),
                AccountMeta(recipient_ata,    False, True),
                AccountMeta(recipient_pubkey, False, False),
                AccountMeta(mint_pubkey,      False, False),
                AccountMeta(SYSTEM_PROGRAM,   False, False),
                AccountMeta(TOKEN_PROGRAM_ID, False, False),
                AccountMeta(SYSVAR_RENT,      False, False),
            ]
            create_ata_ix = Instruction(ASSOC_TOKEN_PROG_ID, bytes([]), ata_accounts)
            instructions.append(create_ata_ix)

        # Build transfer_checked instruction
        # Discriminator 12 = transfer_checked, then u64 amount, then u8 decimals
        ix_data = struct.pack("<BQB", 12, amount_raw, config.TOKEN_DECIMALS)
        transfer_accounts = [
            AccountMeta(sender_ata,      False, True),
            AccountMeta(mint_pubkey,     False, False),
            AccountMeta(recipient_ata,   False, True),
            AccountMeta(sender_pubkey,   True,  False),
        ]
        transfer_ix = Instruction(TOKEN_PROGRAM_ID, ix_data, transfer_accounts)
        instructions.append(transfer_ix)

        # Build and sign transaction
        msg = Message.new_with_blockhash(instructions, sender_pubkey, blockhash)
        tx  = SoldersTransaction.new_unsigned(msg)
        tx.sign([keypair], blockhash)

        tx_b64 = base64.b64encode(bytes(tx)).decode()

        # Send transaction
        send_resp = _rpc({
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [tx_b64, {
                "encoding": "base64",
                "preflightCommitment": "confirmed",
                "skipPreflight": False
            }]
        })

        if send_resp and "result" in send_resp and send_resp["result"]:
            sig = send_resp["result"]
            logger.info(f"✅ Token TX: {sig} | {int(amount_tokens):,} TKB → {recipient_wallet}")
            result["success"]      = True
            result["tx_signature"] = sig
            result["message"]      = f"✅ {int(amount_tokens):,} TKB sent! TX: {sig}"
        else:
            err = send_resp.get("error", {}) if send_resp else "No response"
            raise Exception(f"RPC sendTransaction failed: {err}")

        return result

    except Exception as e:
        logger.error(f"Token send error: {e}", exc_info=True)
        result["message"] = f"❌ Token send failed: {str(e)}"
        return result