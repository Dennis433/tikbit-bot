import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Solana
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
PRESALE_WALLET = os.getenv("PRESALE_WALLET")
TOKEN_MINT = os.getenv("TOKEN_MINT")

# Token Info
TOKEN_NAME = os.getenv("TOKEN_NAME", "TIKBIT")
TOKEN_SYMBOL = os.getenv("TOKEN_SYMBOL", "TKB")

# Presale Settings
PRESALE_PRICE_SOL = 0.0001      # 1 token = 0.0001 SOL (10,000 tokens per SOL)
HARD_CAP_SOL = 1000             # Max SOL to raise = 10,000,000 tokens
SOFT_CAP_SOL = 100              # Min SOL to raise = 1,000,000 tokens
MIN_BUY_SOL = 0.1               # Minimum = 1,000 tokens
MAX_BUY_SOL = 10                # Maximum = 100,000 tokens
PRESALE_ACTIVE = True

# Admin
ADMIN_IDS = [7839044803]