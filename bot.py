from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
import config
import db
import solana_utils
import os

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-render-url.onrender.com/miniapp")

# Conversation states
REGISTER_WALLET, VERIFY_TX = range(2)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🚀 Open Presale App",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )],
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

# ─────────────────────────────────────────
# START
# ─────────────────────────────────────────

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
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

# ─────────────────────────────────────────
# HELP
# ─────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *TIKBIT Presale — Help*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *Option 1 — Mini App (Recommended)*\n"
        "Tap *Open Presale App* → Connect Phantom → Enter amount → Done!\n\n"
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
        "/mystats — Your contributions\n"
        "/help — This message\n\n"
        "💬 Support: @tikbitcoincommunity"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )

# ─────────────────────────────────────────
# REGISTER WALLET
# ─────────────────────────────────────────

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "👛 *Register Your Solana Wallet*\n\n"
            "Please send your Solana wallet address below.\n"
            "This is where your *TIKBIT tokens* will be airdropped after presale ends.\n\n"
            "💡 Tip: Copy your address from Phantom wallet app.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "👛 *Register Your Solana Wallet*\n\n"
            "Please send your Solana wallet address below.\n"
            "This is where your *TIKBIT tokens* will be airdropped.",
            parse_mode="Markdown"
        )
    return REGISTER_WALLET

async def register_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    user = update.effective_user
    if not solana_utils.is_valid_solana_address(wallet):
        await update.message.reply_text(
            "❌ Invalid Solana address.\n\n"
            "Please send a valid Solana wallet address.\n"
            "It should be 32-44 characters long."
        )
        return REGISTER_WALLET
    db.register_wallet(user.id, user.username, wallet)
    await update.message.reply_text(
        f"✅ *Wallet Registered Successfully!*\n\n"
        f"`{wallet}`\n\n"
        f"You can now buy tokens using /buy or the presale app!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# ─────────────────────────────────────────
# BUY
# ─────────────────────────────────────────

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
            "⚠️ You haven't registered a wallet yet!\n\n"
            "Use /register first to register your Solana wallet.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👛 Register Wallet", callback_data="register")]
            ])
        )
        return

    tokens_per_sol = int(1 / config.PRESALE_PRICE_SOL)
    text = (
        f"💰 *How to Buy {config.TOKEN_NAME}*\n\n"
        f"Send SOL to this presale wallet:\n"
        f"`{config.PRESALE_WALLET}`\n\n"
        f"💱 *Rate: {tokens_per_sol:,} {config.TOKEN_SYMBOL} per SOL*\n\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* = {int(config.MIN_BUY_SOL / config.PRESALE_PRICE_SOL):,} tokens\n"
        f"📦 Max: *{config.MAX_BUY_SOL} SOL* = {int(config.MAX_BUY_SOL / config.PRESALE_PRICE_SOL):,} tokens\n\n"
        f"After sending, use /verify to confirm your payment.\n\n"
        f"📌 Your registered wallet:\n`{wallet}`"
    )
    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Buy via App Instead", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔍 Verify Payment", callback_data="verify")]
        ])
    )

# ─────────────────────────────────────────
# VERIFY PAYMENT
# ─────────────────────────────────────────

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
        await message.reply_text(
            "⚠️ Please register your wallet first using /register"
        )
        return ConversationHandler.END

    await message.reply_text(
        "🔍 *Verify Your Payment*\n\n"
        "Please paste your *transaction signature* (tx hash) below.\n\n"
        "📌 You can find it in your Solana wallet after sending.\n"
        "It looks like a long string of letters and numbers.",
        parse_mode="Markdown"
    )
    return VERIFY_TX

async def verify_tx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_sig = update.message.text.strip()
    user = update.effective_user
    wallet = db.get_wallet(user.id)

    if db.tx_exists(tx_sig):
        await update.message.reply_text(
            "⚠️ This transaction has already been verified and recorded.",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END

    await update.message.reply_text("⏳ Verifying your transaction on-chain...")

    result = solana_utils.verify_payment(tx_sig, wallet)

    if not result["success"]:
        await update.message.reply_text(
            result["message"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Try Again", callback_data="verify")]
            ])
        )
        return ConversationHandler.END

    amount_sol = result["amount_sol"]
    tokens = amount_sol / config.PRESALE_PRICE_SOL

    saved = db.add_contribution(user.id, user.username, wallet, amount_sol, tx_sig)

    if not saved:
        await update.message.reply_text("⚠️ Could not save contribution. Contact admin.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"🎉 *Payment Verified!*\n\n"
        f"💵 Amount: *{amount_sol:.4f} SOL*\n"
        f"🪙 Tokens Allocated: *{tokens:,.0f} {config.TOKEN_SYMBOL}*\n"
        f"💱 Rate: *{int(1 / config.PRESALE_PRICE_SOL):,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"👛 Wallet: `{wallet}`\n\n"
        f"✅ Your tokens will be airdropped after presale ends on *June 6, 2026*!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# ─────────────────────────────────────────
# MY STATS
# ─────────────────────────────────────────

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
    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

# ─────────────────────────────────────────
# PRESALE STATUS
# ─────────────────────────────────────────

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
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Join Presale Now", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
        ])
    )

# ─────────────────────────────────────────
# HOW TO BUY
# ─────────────────────────────────────────

async def how_to_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens_per_sol = int(1 / config.PRESALE_PRICE_SOL)
    text = (
        f"📖 *How to Buy {config.TOKEN_NAME} Tokens*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Option 1 — Mini App (Easy)*\n\n"
        f"1️⃣ Tap *Open Presale App* below\n"
        f"2️⃣ Tap *Connect Phantom Wallet*\n"
        f"3️⃣ Enter SOL amount\n"
        f"4️⃣ Tap *Send SOL & Get Tokens*\n"
        f"5️⃣ Approve in Phantom — Done! ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 *Option 2 — Chat Commands*\n\n"
        f"1️⃣ /register — Register your wallet\n"
        f"2️⃣ /buy — Get presale wallet address\n"
        f"3️⃣ Send SOL to the address shown\n"
        f"4️⃣ /verify — Paste your tx signature\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💱 Rate: *{tokens_per_sol:,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* | Max: *{config.MAX_BUY_SOL} SOL*\n"
        f"🪂 Tokens airdropped after *June 6, 2026*"
    )
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
        ])
    )

# ─────────────────────────────────────────
# ADMIN PANEL
# ─────────────────────────────────────────

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
        f"💱 Rate: *{int(1 / config.PRESALE_PRICE_SOL):,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"🏷 Mint: `{config.TOKEN_MINT}`\n"
        f"👛 Presale Wallet: `{config.PRESALE_WALLET}`\n\n"
        f"Presale Active: *{'✅ Yes' if config.PRESALE_ACTIVE else '⏸ Paused'}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ─────────────────────────────────────────
# CALLBACK ROUTER
# ─────────────────────────────────────────

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
        await query.message.reply_text(
            "Main menu 👇",
            reply_markup=main_menu_keyboard()
        )

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    register_conv = ConversationHandler(
        entry_points=[
            CommandHandler("register", register_start),
            CallbackQueryHandler(register_start, pattern="^register$")
        ],
        states={
            REGISTER_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_wallet)]
        },
        fallbacks=[],
        per_message=False
    )

    verify_conv = ConversationHandler(
        entry_points=[
            CommandHandler("verify", verify_start),
            CallbackQueryHandler(verify_start, pattern="^verify$")
        ],
        states={
            VERIFY_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_tx)]
        },
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

    print(f"🚀 {config.TOKEN_NAME} Bot is running — Mini App + Chat Commands active!")
    app.run_polling()

if __name__ == "__main__":
    main()