code = '''from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
import config
import db
import solana_utils

REGISTER_WALLET, VERIFY_TX = range(2)

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Buy Tokens", callback_data="buy")],
        [InlineKeyboardButton("📋 My Stats", callback_data="mystats"),
         InlineKeyboardButton("📊 Presale Status", callback_data="status")],
        [InlineKeyboardButton("👛 Register Wallet", callback_data="register")],
        [InlineKeyboardButton("ℹ️ How to Buy", callback_data="howtobuy")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.init_db()
    user = update.effective_user
    text = (
        f"👋 Welcome *{user.first_name}* to the *{config.TOKEN_NAME} Presale!*\\n\\n"
        f"🪙 Token: *{config.TOKEN_NAME}* (${config.TOKEN_SYMBOL})\\n"
        f"💵 Price: *{config.PRESALE_PRICE_SOL} SOL* per token\\n"
        f"🎯 Hard Cap: *{config.HARD_CAP_SOL} SOL*\\n"
        f"📉 Soft Cap: *{config.SOFT_CAP_SOL} SOL*\\n"
        f"📦 Min Buy: *{config.MIN_BUY_SOL} SOL*\\n"
        f"📦 Max Buy: *{config.MAX_BUY_SOL} SOL*\\n\\n"
        f"Use the menu below to get started 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=main_menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Available Commands*\\n\\n"
        "/start - Main menu\\n"
        "/buy - Buy tokens\\n"
        "/verify - Verify your payment\\n"
        "/mystats - Your contribution stats\\n"
        "/status - Presale progress\\n"
        "/register - Register your wallet\\n"
        "/help - Show this message\\n\\n"
        "👑 *Admin Only*\\n"
        "/adminpanel - Admin controls"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "👛 *Register Your Solana Wallet*\\n\\n"
            "Please send your Solana wallet address below.\\n"
            "This is where your tokens will be airdropped after presale ends.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "👛 *Register Your Solana Wallet*\\n\\n"
            "Please send your Solana wallet address below.",
            parse_mode="Markdown"
        )
    return REGISTER_WALLET

async def register_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    user = update.effective_user
    if not solana_utils.is_valid_solana_address(wallet):
        await update.message.reply_text("❌ Invalid Solana address. Please send a valid wallet address.")
        return REGISTER_WALLET
    db.register_wallet(user.id, user.username, wallet)
    await update.message.reply_text(
        f"✅ *Wallet Registered Successfully!*\\n\\n"
        f"`{wallet}`\\n\\n"
        f"You can now proceed to buy tokens.",
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
            "⚠️ You have not registered a wallet yet!\\n\\n"
            "Use /register to register your Solana wallet first."
        )
        return
    text = (
        f"💰 *How to Buy {config.TOKEN_NAME}*\\n\\n"
        f"1️⃣ Send SOL to this presale wallet:\\n"
        f"`{config.PRESALE_WALLET}`\\n\\n"
        f"2️⃣ Minimum: *{config.MIN_BUY_SOL} SOL*\\n"
        f"   Maximum: *{config.MAX_BUY_SOL} SOL*\\n\\n"
        f"3️⃣ After sending, use /verify to confirm your payment\\n\\n"
        f"📌 Your registered wallet:\\n`{wallet}`"
    )
    await message.reply_text(text, parse_mode="Markdown")

async def verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if not wallet:
        await update.message.reply_text("⚠️ Please register your wallet first using /register")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔍 *Verify Your Payment*\\n\\n"
        "Please paste your *transaction signature* below.\\n\\n"
        "You can find it in your Solana wallet after sending.",
        parse_mode="Markdown"
    )
    return VERIFY_TX

async def verify_tx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_sig = update.message.text.strip()
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if db.tx_exists(tx_sig):
        await update.message.reply_text("⚠️ This transaction has already been verified and recorded.")
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
        f"🎉 *Payment Verified!*\\n\\n"
        f"💵 Amount: *{amount_sol:.4f} SOL*\\n"
        f"🪙 Tokens Allocated: *{tokens:,.0f} {config.TOKEN_SYMBOL}*\\n"
        f"👛 Wallet: `{wallet}`\\n\\n"
        f"✅ Your tokens will be airdropped after presale ends!",
        parse_mode="Markdown",
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
    text = (
        f"📋 *Your Presale Stats*\\n\\n"
        f"👛 Wallet: `{wallet}`\\n"
        f"💵 Total Contributed: *{total_sol:.4f} SOL*\\n"
        f"🪙 Tokens Allocated: *{total_tokens:,.0f} {config.TOKEN_SYMBOL}*\\n"
        f"🔁 Transactions: *{tx_count}*"
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
    progress = (total_sol / config.HARD_CAP_SOL) * 100
    bars = int(progress / 5)
    bar = "🟩" * bars + "⬜" * (20 - bars)
    text = (
        f"📊 *{config.TOKEN_NAME} Presale Status*\\n\\n"
        f"{bar}\\n"
        f"💰 Raised: *{total_sol:.2f} / {config.HARD_CAP_SOL} SOL*\\n"
        f"📈 Progress: *{progress:.1f}%*\\n"
        f"🎯 Soft Cap: *{config.SOFT_CAP_SOL} SOL*\\n"
        f"👥 Participants: *{unique_buyers}*\\n"
        f"🪙 Tokens Sold: *{total_tokens:,.0f} {config.TOKEN_SYMBOL}*\\n\\n"
        f"{'✅ Soft cap reached!' if total_sol >= config.SOFT_CAP_SOL else '⏳ Presale in progress...'}"
    )
    await message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def how_to_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        f"📖 *How to Buy {config.TOKEN_NAME} Tokens*\\n\\n"
        f"1️⃣ Register your Solana wallet using /register\\n\\n"
        f"2️⃣ Send SOL to the presale wallet:\\n"
        f"`{config.PRESALE_WALLET}`\\n\\n"
        f"3️⃣ Min: *{config.MIN_BUY_SOL} SOL* | Max: *{config.MAX_BUY_SOL} SOL*\\n\\n"
        f"4️⃣ Copy your transaction signature from your wallet\\n\\n"
        f"5️⃣ Use /verify and paste the tx signature\\n\\n"
        f"6️⃣ Tokens will be airdropped to your wallet after presale! 🎉"
    )
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    total_sol, total_tokens, unique_buyers = db.get_presale_stats()
    balance = solana_utils.get_presale_wallet_balance()
    text = (
        f"👑 *Admin Panel*\\n\\n"
        f"💰 Total Raised: *{total_sol:.4f} SOL*\\n"
        f"🏦 Wallet Balance: *{balance:.4f} SOL*\\n"
        f"🪙 Tokens Allocated: *{total_tokens:,.0f} {config.TOKEN_SYMBOL}*\\n"
        f"👥 Unique Buyers: *{unique_buyers}*\\n\\n"
        f"Presale Active: *{'✅ Yes' if config.PRESALE_ACTIVE else '⏸ Paused'}*"
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
        fallbacks=[]
    )
    verify_conv = ConversationHandler(
        entry_points=[CommandHandler("verify", verify_start)],
        states={
            VERIFY_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_tx)]
        },
        fallbacks=[]
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
    print(f"🚀 {config.TOKEN_NAME} Presale Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
'''

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("bot.py written successfully!")