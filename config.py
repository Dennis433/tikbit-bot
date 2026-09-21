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
# If HELIUS_API_KEY is set, we use the Helius endpoint (much higher rate
# limits than the public node) and it takes precedence over any RPC_URL.
# Get a free key at https://dashboard.helius.dev → set HELIUS_API_KEY on Render.
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
if HELIUS_API_KEY:
    RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
else:
    RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com").strip()

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
SOL_PRICE_USD     = float(os.getenv("SOL_PRICE_USD", "80"))  # For display in announcements
MIN_BUY_USD       = 25                                       # Minimum buy in USD
MIN_BUY_SOL       = MIN_BUY_USD / SOL_PRICE_USD             # ~0.3125 SOL at $80/SOL
MAX_BUY_SOL       = 10
PRESALE_ACTIVE    = True

# ── REFERRALS ──
# Reward paid to a referrer when someone they invited makes their first
# qualifying buy. Paid in TKB, sent from the airdrop wallet.
REFERRAL_REWARD_TKB = int(os.getenv("REFERRAL_REWARD_TKB", "50"))
# A referee's buy must be at least this many SOL to trigger a referral reward.
# Defaults to the normal minimum buy. Raise it to reduce self-referral farming.
REFERRAL_MIN_BUY_SOL = float(os.getenv("REFERRAL_MIN_BUY_SOL", str(MIN_BUY_SOL)))

# Mini app URL
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tikbit-bot.onrender.com/miniapp")

# Admin Telegram IDs
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7839044803").split(",") if x.strip()]
