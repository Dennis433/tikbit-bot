from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import config
import db
import solana_utils
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# TELEGRAM BOT
# ─────────────────────────────────────────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tikbit-bot.onrender.com/miniapp")
REGISTER_WALLET, VERIFY_TX = range(2)

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💰 Buy via Chat", callback_data="buy"),
         InlineKeyboardButton("📊 Presale Status", callback_data="status")],
        [InlineKeyboardButton("👛 Register Wallet", callback_data="register"),
         InlineKeyboardButton("📋 My Stats", callback_data="mystats")],
        [InlineKeyboardButton("ℹ️ How to Buy", callback_data="howtobuy"),
         InlineKeyboardButton("🔍 Verify Payment", callback_data="verify")],
        [InlineKeyboardButton("👥 Community", url="https://t.me/tikbitcoincommunity"),
         InlineKeyboardButton("🐦 Twitter/X", url="https://x.com/TikBitcoin")],
        [InlineKeyboardButton("🎵 TikTok", url="https://www.tiktok.com/@tikbitcoin")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.init_db()
    user = update.effective_user
    tokens_per_sol = int(1 / config.PRESALE_PRICE_SOL)
    text = (
        f"👋 Welcome *{user.first_name}* to the *{config.TOKEN_NAME} Presale!*\n\n"
        f"TikTok + Bitcoin on Solana ⚡💎\n"
        f"Viral coins + Real utility = Next 1000x 🚀\n\n"
        f"🪙 Token: *{config.TOKEN_NAME}* (${config.TOKEN_SYMBOL})\n"
        f"💵 Price: *{config.PRESALE_PRICE_SOL} SOL* per token\n"
        f"📊 Rate: *{tokens_per_sol:,} {config.TOKEN_SYMBOL}* per SOL\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* | Max: *{config.MAX_BUY_SOL} SOL*\n"
        f"🎯 Hard Cap: *{config.HARD_CAP_SOL} SOL*\n\n"
        f"*Choose how to participate:*\n"
        f"📱 *Presale App* — Connect Phantom & buy instantly\n"
        f"💬 *Chat Commands* — Manual step by step\n\n"
        f"👇 Use the menu below to get started!"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    text = (
        "📖 *TIKBIT Presale — Help*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *Option 1 — Mini App (Recommended)*\n"
        "Tap Open Presale App → Connect Phantom → Enter amount → Done!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 *Option 2 — Chat Commands*\n\n"
        "1️⃣ /register — Register your Solana wallet\n"
        "2️⃣ /buy — Get presale wallet address\n"
        "3️⃣ Send SOL manually to the address shown\n"
        "4️⃣ /verify — Paste your tx signature\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *Other Commands*\n"
        "/start — Main menu\n"
        "/status — Presale progress\n"
        "/mystats — Your contributions\n\n"
        "💬 Support: @tikbitcoincommunity"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "👛 *Register Your Solana Wallet*\n\n"
            "Please send your Solana wallet address below.\n"
            "This is where your *TIKBIT tokens* will be sent automatically after payment is confirmed!\n\n"
            "💡 Tip: Copy your address from Phantom wallet app.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "👛 *Register Your Solana Wallet*\n\n"
            "Please send your Solana wallet address below.",
            parse_mode="Markdown"
        )
    return REGISTER_WALLET

async def register_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    user = update.effective_user
    if not solana_utils.is_valid_solana_address(wallet):
        await update.message.reply_text("❌ Invalid Solana address. Please send a valid wallet address.")
        return REGISTER_WALLET
    db.register_wallet(user.id, user.username, wallet)
    await update.message.reply_text(
        f"✅ *Wallet Registered Successfully!*\n\n"
        f"`{wallet}`\n\n"
        f"🎯 As soon as we detect your SOL payment, TKB tokens will be sent to this wallet automatically!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    if not config.PRESALE_ACTIVE:
        await message.reply_text("⏸ Presale is currently paused. Check back soon!")
        return
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if not wallet:
        await message.reply_text(
            "⚠️ You haven't registered a wallet yet!\n\nUse /register first.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👛 Register Wallet", callback_data="register")]
            ])
        )
        return
    tokens_per_sol = int(1 / config.PRESALE_PRICE_SOL)
    text = (
        f"💰 *How to Buy {config.TOKEN_NAME}*\n\n"
        f"1️⃣ Send SOL to this presale wallet:\n"
        f"`{config.PRESALE_WALLET}`\n\n"
        f"💱 *Rate: {tokens_per_sol:,} {config.TOKEN_SYMBOL} per SOL*\n\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* = {int(config.MIN_BUY_SOL / config.PRESALE_PRICE_SOL):,} tokens\n"
        f"📦 Max: *{config.MAX_BUY_SOL} SOL* = {int(config.MAX_BUY_SOL / config.PRESALE_PRICE_SOL):,} tokens\n\n"
        f"2️⃣ Our system detects your payment automatically!\n"
        f"3️⃣ TKB tokens are sent to your wallet instantly ✅\n\n"
        f"📌 Your registered wallet:\n`{wallet}`\n\n"
        f"⚡ No need to verify manually — we handle it!"
    )
    await message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Buy via App Instead", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔍 Verify Manually", callback_data="verify")]
        ])
    )

async def verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if not wallet:
        await message.reply_text("⚠️ Please register your wallet first using /register")
        return ConversationHandler.END
    await message.reply_text(
        "🔍 *Manual Verify Payment*\n\n"
        "Paste your *transaction signature* below.\n\n"
        "💡 Only needed if auto-detection missed your payment.",
        parse_mode="Markdown"
    )
    return VERIFY_TX

async def verify_tx_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_sig = update.message.text.strip()
    user = update.effective_user
    wallet = db.get_wallet(user.id)

    if db.tx_exists(tx_sig):
        await update.message.reply_text("⚠️ This transaction has already been verified.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("⏳ Verifying your transaction on-chain...")
    result = solana_utils.verify_payment(tx_sig, wallet)

    if not result["success"]:
        await update.message.reply_text(result["message"])
        return ConversationHandler.END

    amount_sol = result["amount_sol"]
    tokens = amount_sol / config.PRESALE_PRICE_SOL
    saved = db.add_contribution(user.id, user.username, wallet, amount_sol, tx_sig)

    if not saved:
        await update.message.reply_text("⚠️ Could not save contribution. Contact admin.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ *Payment Verified!*\n\n"
        f"💵 Amount: *{amount_sol:.4f} SOL*\n"
        f"🪙 Tokens: *{tokens:,.0f} {config.TOKEN_SYMBOL}*\n"
        f"👛 Wallet: `{wallet}`\n\n"
        f"⏳ Sending tokens to your wallet...",
        parse_mode="Markdown"
    )

    # Send tokens
    token_result = solana_utils.send_tokens(wallet, tokens)
    if token_result["success"]:
        await update.message.reply_text(
            f"🎉 *{int(tokens):,} {config.TOKEN_SYMBOL} Sent!*\n\n"
            f"👛 To: `{wallet}`\n"
            f"{'🔗 TX: ' + token_result['tx_signature'] if token_result['tx_signature'] != 'QUEUED' else '📋 Queued for airdrop after presale ends'}",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            f"⚠️ Token transfer failed. Will be airdropped manually after presale.\n{token_result['message']}",
            reply_markup=main_menu_keyboard()
        )
    return ConversationHandler.END

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    user = update.effective_user
    total_sol, total_tokens, tx_count = db.get_user_stats(user.id)
    wallet = db.get_wallet(user.id) or "Not registered"
    total_sol = total_sol or 0
    total_tokens = total_tokens or 0
    text = (
        f"📋 *Your Presale Stats*\n\n"
        f"👛 Wallet: `{wallet}`\n"
        f"💵 Total Contributed: *{total_sol:.4f} SOL*\n"
        f"🪙 Tokens Allocated: *{total_tokens:,.0f} {config.TOKEN_SYMBOL}*\n"
        f"🔁 Transactions: *{tx_count}*\n\n"
        f"💱 Rate: *{int(1 / config.PRESALE_PRICE_SOL):,} {config.TOKEN_SYMBOL} per SOL*\n\n"
        f"{'🎉 You are in the presale!' if total_sol > 0 else '⏳ No contributions yet.'}"
    )
    await message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def presale_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    total_sol, total_tokens, unique_buyers = db.get_presale_stats()
    total_sol = total_sol or 0
    total_tokens = total_tokens or 0
    progress = (total_sol / config.HARD_CAP_SOL) * 100
    bars = int(progress / 5)
    bar = "🟩" * bars + "⬜" * (20 - bars)
    max_tokens = int(config.HARD_CAP_SOL / config.PRESALE_PRICE_SOL)
    text = (
        f"📊 *{config.TOKEN_NAME} Presale Status*\n\n"
        f"{bar}\n"
        f"💰 Raised: *{total_sol:.2f} / {config.HARD_CAP_SOL} SOL*\n"
        f"📈 Progress: *{progress:.1f}%*\n"
        f"🎯 Hard Cap: *{config.HARD_CAP_SOL} SOL*\n"
        f"📉 Soft Cap: *{config.SOFT_CAP_SOL} SOL*\n"
        f"👥 Participants: *{unique_buyers}*\n"
        f"🪙 Tokens Sold: *{total_tokens:,.0f} / {max_tokens:,} {config.TOKEN_SYMBOL}*\n"
        f"💱 Rate: *{int(1 / config.PRESALE_PRICE_SOL):,} {config.TOKEN_SYMBOL} per SOL*\n\n"
        f"{'✅ Soft cap reached!' if total_sol >= config.SOFT_CAP_SOL else '⏳ Presale in progress...'}"
    )
    await message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Join Presale Now", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
        ])
    )

async def how_to_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens_per_sol = int(1 / config.PRESALE_PRICE_SOL)
    text = (
        f"📖 *How to Buy {config.TOKEN_NAME} Tokens*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Option 1 — Mini App (Easy)*\n\n"
        f"1️⃣ Tap *Open Presale App*\n"
        f"2️⃣ Connect your Phantom wallet\n"
        f"3️⃣ Enter SOL amount\n"
        f"4️⃣ Tap *Send SOL & Get Tokens*\n"
        f"5️⃣ Approve in Phantom\n"
        f"6️⃣ TKB sent to your wallet automatically! ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 *Option 2 — Chat Commands*\n\n"
        f"1️⃣ /register — Register your wallet\n"
        f"2️⃣ /buy — Get presale wallet address\n"
        f"3️⃣ Send SOL — system auto-detects payment\n"
        f"4️⃣ Receive TKB automatically! ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💱 Rate: *{tokens_per_sol:,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* | Max: *{config.MAX_BUY_SOL} SOL*"
    )
    await query.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
        ])
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    total_sol, total_tokens, unique_buyers = db.get_presale_stats()
    total_sol = total_sol or 0
    total_tokens = total_tokens or 0
    balance = solana_utils.get_presale_wallet_balance()
    progress = (total_sol / config.HARD_CAP_SOL) * 100
    text = (
        f"👑 *Admin Panel — {config.TOKEN_NAME}*\n\n"
        f"💰 Total Raised: *{total_sol:.4f} SOL*\n"
        f"🏦 Wallet Balance: *{balance:.4f} SOL*\n"
        f"📈 Progress: *{progress:.1f}%*\n"
        f"🪙 Tokens Allocated: *{total_tokens:,.0f} {config.TOKEN_SYMBOL}*\n"
        f"👥 Unique Buyers: *{unique_buyers}*\n"
        f"🏷 Mint: `{config.TOKEN_MINT}`\n"
        f"👛 Presale Wallet: `{config.PRESALE_WALLET}`\n\n"
        f"Presale Active: *{'✅ Yes' if config.PRESALE_ACTIVE else '⏸ Paused'}*\n"
        f"🤖 Auto-detection: *✅ Running*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "buy":
        await buy(update, context)
    elif data == "mystats":
        await my_stats(update, context)
    elif data == "status":
        await presale_status(update, context)
    elif data == "howtobuy":
        await how_to_buy(update, context)
    elif data == "verify":
        await verify_start(update, context)
    elif data == "menu":
        await query.answer()
        await query.message.reply_text("Main menu 👇", reply_markup=main_menu_keyboard())

def build_bot():
    app = Application.builder().token(config.BOT_TOKEN).build()
    register_conv = ConversationHandler(
        entry_points=[
            CommandHandler("register", register_start),
            CallbackQueryHandler(register_start, pattern="^register$")
        ],
        states={REGISTER_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_wallet_handler)]},
        fallbacks=[],
        per_message=False
    )
    verify_conv = ConversationHandler(
        entry_points=[
            CommandHandler("verify", verify_start),
            CallbackQueryHandler(verify_start, pattern="^verify$")
        ],
        states={VERIFY_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_tx_handler)]},
        fallbacks=[],
        per_message=False
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("mystats", my_stats))
    app.add_handler(CommandHandler("status", presale_status))
    app.add_handler(CommandHandler("adminpanel", admin_panel))
    app.add_handler(register_conv)
    app.add_handler(verify_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    return app

# ─────────────────────────────────────────
# TRANSACTION MONITOR
# ─────────────────────────────────────────

async def monitor_transactions(bot_app):
    """
    Polls presale wallet every 30 seconds for new transactions.
    When a payment is detected from a registered wallet,
    it automatically sends TKB tokens and notifies the user.
    """
    logger.info("🔍 Transaction monitor started...")
    seen_signatures = set()

    # Pre-load existing tx signatures so we don't reprocess old ones
    try:
        recent = solana_utils.get_recent_transactions(50)
        for tx in recent:
            seen_signatures.add(tx["signature"])
        logger.info(f"Loaded {len(seen_signatures)} existing transactions")
    except Exception as e:
        logger.error(f"Error loading existing transactions: {e}")

    while True:
        try:
            await asyncio.sleep(30)
            recent_txs = solana_utils.get_recent_transactions(20)

            for tx_info in recent_txs:
                sig = tx_info["signature"]
                if sig in seen_signatures:
                    continue

                seen_signatures.add(sig)
                logger.info(f"New transaction detected: {sig}")

                # Parse transaction
                tx_result = solana_utils.get_sender_from_tx(sig)
                if not tx_result["success"]:
                    continue

                sender_wallet = tx_result["sender"]
                amount_sol = tx_result["amount_sol"]
                tokens = amount_sol / config.PRESALE_PRICE_SOL

                logger.info(f"Payment: {amount_sol} SOL from {sender_wallet}")

                # Check if this wallet is registered
                user_id = db.get_user_id_by_wallet(sender_wallet)

                # Check for duplicate tx
                if db.tx_exists(sig):
                    continue

                # Get username for saving
                username = db.get_username_by_wallet(sender_wallet) if user_id else "unknown"

                # Save contribution
                saved = db.add_contribution(
                    user_id or sender_wallet,
                    username,
                    sender_wallet,
                    amount_sol,
                    sig
                )

                if not saved:
                    continue

                # Send tokens
                token_result = solana_utils.send_tokens(sender_wallet, tokens)

                # Notify user on Telegram if registered
                if user_id:
                    try:
                        if token_result["success"] and token_result["tx_signature"] != "QUEUED":
                            msg = (
                                f"🎉 *Payment Confirmed!*\n\n"
                                f"💵 Received: *{amount_sol:.4f} SOL*\n"
                                f"🪙 Sent: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                                f"👛 To: `{sender_wallet}`\n"
                                f"🔗 TX: `{token_result['tx_signature']}`\n\n"
                                f"✅ Tokens are in your wallet!"
                            )
                        else:
                            msg = (
                                f"✅ *Payment Confirmed!*\n\n"
                                f"💵 Received: *{amount_sol:.4f} SOL*\n"
                                f"🪙 Allocated: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                                f"👛 Wallet: `{sender_wallet}`\n\n"
                                f"📋 Tokens queued — will be airdropped after presale ends on June 6, 2026!"
                            )
                        await bot_app.bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            parse_mode="Markdown",
                            reply_markup=main_menu_keyboard()
                        )
                        logger.info(f"Notified user {user_id}")
                    except Exception as e:
                        logger.error(f"Could not notify user {user_id}: {e}")

                    # Notify admins
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await bot_app.bot.send_message(
                                chat_id=admin_id,
                                text=(
                                    f"💰 *New Presale Contribution!*\n\n"
                                    f"👤 User: {user_id}\n"
                                    f"💵 Amount: *{amount_sol:.4f} SOL*\n"
                                    f"🪙 Tokens: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                                    f"👛 Wallet: `{sender_wallet}`\n"
                                    f"🔗 TX: `{sig}`"
                                ),
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.error(f"Could not notify admin {admin_id}: {e}")

        except Exception as e:
            logger.error(f"Monitor error: {e}")
            await asyncio.sleep(30)

# ─────────────────────────────────────────
# FASTAPI
# ─────────────────────────────────────────

bot_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_app
    db.init_db()
    bot_app = build_bot()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    asyncio.create_task(monitor_transactions(bot_app))
    logger.info("🚀 TIKBIT Bot + Monitor running!")
    yield
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("miniapp"):
    app.mount("/miniapp", StaticFiles(directory="miniapp", html=True), name="miniapp")

class VerifyRequest(BaseModel):
    tx_signature: str
    wallet: str
    user_id: str
    username: str | None = None

@app.get("/")
def root():
    return {"status": "TIKBIT Presale API running", "monitor": "active"}

@app.get("/presale/info")
def presale_info():
    total_sol, total_tokens, unique_buyers = db.get_presale_stats()
    total_sol = total_sol or 0
    total_tokens = total_tokens or 0
    progress = (total_sol / config.HARD_CAP_SOL) * 100
    return {
        "token_name": config.TOKEN_NAME,
        "token_symbol": config.TOKEN_SYMBOL,
        "price_sol": config.PRESALE_PRICE_SOL,
        "tokens_per_sol": int(1 / config.PRESALE_PRICE_SOL),
        "hard_cap_sol": config.HARD_CAP_SOL,
        "soft_cap_sol": config.SOFT_CAP_SOL,
        "min_buy_sol": config.MIN_BUY_SOL,
        "max_buy_sol": config.MAX_BUY_SOL,
        "presale_wallet": config.PRESALE_WALLET,
        "token_mint": config.TOKEN_MINT,
        "presale_active": config.PRESALE_ACTIVE,
        "total_raised_sol": round(total_sol, 4),
        "total_tokens_sold": int(total_tokens),
        "unique_buyers": unique_buyers,
        "progress_percent": round(progress, 2),
    }

@app.post("/presale/verify")
def verify_payment(req: VerifyRequest):
    if not solana_utils.is_valid_solana_address(req.wallet):
        raise HTTPException(status_code=400, detail="Invalid Solana wallet address")
    if db.tx_exists(req.tx_signature):
        raise HTTPException(status_code=409, detail="Transaction already verified")

    result = solana_utils.verify_payment(req.tx_signature, req.wallet)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    amount_sol = result["amount_sol"]
    tokens = amount_sol / config.PRESALE_PRICE_SOL
    saved = db.add_contribution(req.user_id, req.username, req.wallet, amount_sol, req.tx_signature)
    if not saved:
        raise HTTPException(status_code=500, detail="Could not save contribution")

    # Send tokens automatically
    token_result = solana_utils.send_tokens(req.wallet, tokens)

    return {
        "success": True,
        "amount_sol": amount_sol,
        "tokens_allocated": int(tokens),
        "token_symbol": config.TOKEN_SYMBOL,
        "wallet": req.wallet,
        "tokens_sent": token_result["success"],
        "token_tx": token_result.get("tx_signature"),
        "message": f"Payment verified! {int(tokens):,} {config.TOKEN_SYMBOL} {'sent to your wallet!' if token_result['success'] else 'queued for airdrop.'}"
    }

@app.get("/presale/stats/{user_id}")
def user_stats(user_id: str):
    total_sol, total_tokens, tx_count = db.get_user_stats(user_id)
    wallet = db.get_wallet(user_id)
    return {
        "user_id": user_id,
        "wallet": wallet,
        "total_sol": round(total_sol or 0, 4),
        "total_tokens": int(total_tokens or 0),
        "tx_count": tx_count or 0,
        "token_symbol": config.TOKEN_SYMBOL,
    }