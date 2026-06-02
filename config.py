import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Tikbitbot")  # without @, used for buy links

# Community group chat ID for buy announcements (e.g. -1001234567890)
# Leave empty to disable announcements
_community_raw = os.getenv("COMMUNITY_CHAT_ID", "").strip()
COMMUNITY_CHAT_ID = int(_community_raw) if _community_raw and _community_raw.lstrip("-").isdigit() else None

# Solana RPC
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# ── WALLETS ──
PRESALE_WALLET = os.getenv("PRESALE_WALLET", "3erMv1GL79XMcPZFLiwbNApVbh9YPzLzEX3nrmNNbNjm")
AIRDROP_WALLET = os.getenv("AIRDROP_WALLET", "3erMv1GL79XMcPZFLiwbNApVbh9YPzLzEX3nrmNNbNjm")
AIRDROP_PRIVATE_KEY = os.getenv("AIRDROP_PRIVATE_KEY")

# Token
TOKEN_MINT     = os.getenv("TOKEN_MINT", "EKzLrEqgERdg4xAkmzY3LLb2RW9SfJ8WFxNLRd2u73yE")
TOKEN_NAME     = os.getenv("TOKEN_NAME", "TIKBIT")
TOKEN_SYMBOL   = os.getenv("TOKEN_SYMBOL", "TKB")
TOKEN_DECIMALS = int(os.getenv("TOKEN_DECIMALS", "9"))

# Presale settings
PRESALE_PRICE_SOL = 0.0001   # 1 TKB = 0.0001 SOL → 10,000 TKB per SOL
HARD_CAP_SOL      = 1000
SOFT_CAP_SOL      = 100
MIN_BUY_SOL       = 0.006    # Minimum ~$0.50 at $80/SOL
MAX_BUY_SOL       = 10
PRESALE_ACTIVE    = True
SOL_PRICE_USD     = float(os.getenv("SOL_PRICE_USD", "80"))  # For display in announcements

# Mini app URL
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tikbit-bot.onrender.com/miniapp")

# Admin Telegram IDs
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7839044803").split(",") if x.strip()]