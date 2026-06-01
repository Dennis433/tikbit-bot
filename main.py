from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
import config, db, solana_utils, os, asyncio, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

def _clean_url(val):
    while val and not val.startswith("http"):
        val = val.split("=",1)[1] if "=" in val else ""
    return val.strip()

WEBAPP_URL = _clean_url(os.getenv("WEBAPP_URL", "https://tikbit-bot.onrender.com/miniapp"))
REGISTER_WALLET, VERIFY_TX = range(2)

def is_admin(uid): return uid in config.ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💰 Buy via Chat", callback_data="buy"),
         InlineKeyboardButton("📊 Presale Status", callback_data="status")],
        [InlineKeyboardButton("👛 Register Wallet", callback_data="register"),
         InlineKeyboardButton("📋 My Stats", callback_data="mystats")],
        [InlineKeyboardButton("ℹ️ How to Buy", callback_data="howtobuy")],
        [InlineKeyboardButton("📱 Connect Wallet Guide", callback_data="connect_guide")],
        [InlineKeyboardButton("👥 Community", url="https://t.me/tikbitcoincommunity"),
         InlineKeyboardButton("🐦 Twitter/X", url="https://x.com/TikBitcoin")],
        [InlineKeyboardButton("🎵 TikTok", url="https://www.tiktok.com/@tikbitcoin")],
    ])

def connect_guide_text():
    url = WEBAPP_URL
    return (
        "📱 *How to Connect Your Wallet*\n\n"
        "Telegram cannot access wallet extensions directly.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *On Mobile (Android / iOS)*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Option A — Phantom Wallet* ⭐ (recommended)\n"
        "1️⃣ Open the *Phantom* app\n"
        "2️⃣ Tap the *Explore* tab (bottom bar)\n"
        "3️⃣ Tap the URL bar at the top\n"
        f"4️⃣ Paste: `{url}`\n"
        "5️⃣ The presale page opens inside Phantom\n"
        "6️⃣ Tap *Phantom* → *Connect* ✅\n\n"
        "*Option B — Solflare Wallet*\n"
        "1️⃣ Open *Solflare* app\n"
        "2️⃣ Tap *Browser* tab\n"
        f"3️⃣ Paste: `{url}`\n"
        "4️⃣ Tap *Solflare* → *Connect* ✅\n\n"
        "*Option C — Any wallet (easiest)*\n"
        "1️⃣ Tap *Open Presale App* button\n"
        "2️⃣ Scroll to *paste your wallet address*\n"
        "3️⃣ Paste your Solana address → tap *Use*\n"
        "4️⃣ Send SOL — auto-detected & credited! ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💻 *On Desktop Telegram*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ Copy: `{url}`\n"
        "2️⃣ Open Chrome / Brave with Phantom extension\n"
        "3️⃣ Paste URL → connect wallet ✅\n\n"
        "💡 *Quickest:* Paste wallet address in the app — no extension needed!"
    )

async def start(update, context):
    db.init_db()
    u = update.effective_user
    tps = int(1 / config.PRESALE_PRICE_SOL)
    await update.message.reply_text(
        f"👋 Welcome *{u.first_name}* to the *{config.TOKEN_NAME} Presale!*\n\n"
        f"TikTok + Bitcoin on Solana ⚡💎\n"
        f"Viral coins + Real utility = Next 1000x 🚀\n\n"
        f"🪙 *{config.TOKEN_NAME}* (${config.TOKEN_SYMBOL})\n"
        f"💵 Price: *{config.PRESALE_PRICE_SOL} SOL* per token\n"
        f"📊 Rate: *{tps:,} {config.TOKEN_SYMBOL}* per SOL\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* | Max: *{config.MAX_BUY_SOL} SOL*\n"
        f"🎯 Hard Cap: *{config.HARD_CAP_SOL} SOL*\n\n"
        f"📱 New here? Tap *Connect Wallet Guide* below!\n"
        f"📲 Just register your wallet, send SOL, and tokens arrive automatically!\n\n"
        f"👇 Use the menu to get started!",
        parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )

async def help_command(update, context):
    await update.message.reply_text(
        "📖 *TIKBIT — Help*\n\n"
        "/start — Main menu\n/register — Register wallet\n"
        "/buy — Get payment address\n"
        "/mystats — Your stats\n/status — Presale status\n"
        "/connectguide — Wallet connection help\n\n"
        "💬 Support: @tikbitcoincommunity",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("📱 Connect Wallet Guide", callback_data="connect_guide")],
        ])
    )

async def connect_guide_command(update, context):
    await update.message.reply_text(
        connect_guide_text(), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Back", callback_data="menu")],
        ])
    )

async def register_start(update, context):
    q = update.callback_query
    target = q.message if q else update.message
    if q: await q.answer()
    await target.reply_text(
        "👛 *Register Your Solana Wallet*\n\n"
        "Send your Solana wallet address below.\n"
        "This is where your TKB tokens will be sent!\n\n"
        "💡 Copy your address from Phantom or Solflare.",
        parse_mode="Markdown"
    )
    return REGISTER_WALLET

async def register_wallet_handler(update, context):
    wallet = update.message.text.strip()
    user = update.effective_user
    if not solana_utils.is_valid_solana_address(wallet):
        await update.message.reply_text("❌ Invalid address. Try again.")
        return REGISTER_WALLET
    db.register_wallet(user.id, user.username, wallet)
    await update.message.reply_text(
        f"✅ *Wallet Registered!*\n\n`{wallet}`\n\n"
        "🎯 TKB tokens will be sent here automatically after payment!",
        parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def buy(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    if not config.PRESALE_ACTIVE:
        await msg.reply_text("⏸ Presale paused.")
        return
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    tps = int(1 / config.PRESALE_PRICE_SOL)
    if not wallet:
        await msg.reply_text(
            "⚠️ Register your wallet first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
                [InlineKeyboardButton("👛 Register Wallet", callback_data="register")],
            ])
        )
        return
    await msg.reply_text(
        f"💰 *How to Buy {config.TOKEN_NAME}*\n\n"
        f"Send SOL to:\n`{config.PRESALE_WALLET}`\n\n"
        f"💱 *{tps:,} {config.TOKEN_SYMBOL} per SOL*\n\n"
        f"📦 Min: *{config.MIN_BUY_SOL}* | Max: *{config.MAX_BUY_SOL} SOL*\n\n"
        f"✅ Auto-detected in ~30 seconds — tokens sent to your wallet instantly!\n\n"
        f"📌 Your wallet: `{wallet}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Buy via App Instead", web_app=WebAppInfo(url=WEBAPP_URL))],
        ])
    )

async def verify_start(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    user = update.effective_user
    if not db.get_wallet(user.id):
        await msg.reply_text("⚠️ Register your wallet first: /register")
        return ConversationHandler.END
    await msg.reply_text(
        "🔍 *Verify Payment*\n\nPaste your *transaction signature*:\n\n"
        "💡 Only needed if auto-detection missed your payment.",
        parse_mode="Markdown"
    )
    return VERIFY_TX

async def verify_tx_handler(update, context):
    sig = update.message.text.strip()
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if db.tx_exists(sig):
        await update.message.reply_text("⚠️ Already verified.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("⏳ Verifying on-chain...")
    result = solana_utils.verify_payment(sig, wallet)
    if not result["success"]:
        await update.message.reply_text(result["message"])
        return ConversationHandler.END
    sol = result["amount_sol"]
    tokens = sol / config.PRESALE_PRICE_SOL
    if not db.add_contribution(user.id, user.username, wallet, sol, sig):
        await update.message.reply_text("⚠️ Save failed. Contact admin.")
        return ConversationHandler.END
    await update.message.reply_text(
        f"✅ *{sol:.4f} SOL* verified → *{int(tokens):,} {config.TOKEN_SYMBOL}*\n⏳ Sending...",
        parse_mode="Markdown"
    )
    tr = solana_utils.send_tokens(wallet, tokens)
    if tr["success"]:
        tx_line = f"🔗 `{tr['tx_signature']}`" if tr.get("tx_signature") != "QUEUED" else "📋 Queued for airdrop"
        await update.message.reply_text(
            f"🎉 *{int(tokens):,} {config.TOKEN_SYMBOL} Sent!*\n👛 `{wallet}`\n{tx_line}",
            parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            f"⚠️ Send failed.\n{tr['message']}", reply_markup=main_menu_keyboard()
        )
    return ConversationHandler.END

async def my_stats(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    user = update.effective_user
    sol, tokens, count = db.get_user_stats(user.id)
    wallet = db.get_wallet(user.id) or "Not registered"
    sol = sol or 0; tokens = tokens or 0
    await msg.reply_text(
        f"📋 *Your Stats*\n\n👛 `{wallet}`\n"
        f"💵 *{sol:.4f} SOL* contributed\n"
        f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* allocated\n"
        f"🔁 {count} transaction(s)\n\n"
        f"{'🎉 You are in the presale!' if sol > 0 else '⏳ No contributions yet.'}",
        parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )

async def presale_status(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    sol, tokens, buyers = db.get_presale_stats()
    sol = sol or 0; tokens = tokens or 0
    pct = (sol / config.HARD_CAP_SOL) * 100
    bar = "🟩" * int(pct/5) + "⬜" * (20-int(pct/5))
    await msg.reply_text(
        f"📊 *{config.TOKEN_NAME} Presale*\n\n{bar}\n"
        f"💰 *{sol:.2f} / {config.HARD_CAP_SOL} SOL*\n"
        f"📈 {pct:.1f}% | 👥 {buyers} buyers\n"
        f"🪙 {int(tokens):,} {config.TOKEN_SYMBOL} sold\n\n"
        f"{'✅ Soft cap reached!' if sol >= config.SOFT_CAP_SOL else '⏳ In progress...'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Join Now", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ])
    )

async def how_to_buy(update, context):
    q = update.callback_query
    await q.answer()
    tps = int(1/config.PRESALE_PRICE_SOL)
    await q.message.reply_text(
        f"📖 *How to Buy {config.TOKEN_NAME}*\n\n"
        f"*Option 1 — Mini App*\n"
        f"Open app → connect wallet → buy ✅\n\n"
        f"*Option 2 — Chat*\n"
        f"1️⃣ /register — save your wallet address\n"
        f"2️⃣ /buy — get the presale wallet address\n"
        f"3️⃣ Send SOL from your registered wallet\n"
        f"4️⃣ Tokens arrive automatically within ~30s ✅\n\n"
        f"💱 *{tps:,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"Min: *{config.MIN_BUY_SOL}* | Max: *{config.MAX_BUY_SOL} SOL*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("📱 Connect Wallet Guide", callback_data="connect_guide")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ])
    )

async def connect_guide_callback(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        connect_guide_text(), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ])
    )

async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    sol, tokens, buyers = db.get_presale_stats()
    sol = sol or 0; tokens = tokens or 0
    presale_bal = solana_utils.get_presale_wallet_balance()
    airdrop_bal = solana_utils.get_airdrop_wallet_balance()
    airdrop_tkb = solana_utils.get_token_balance(config.AIRDROP_WALLET)
    key_ok = "✅ Set" if config.AIRDROP_PRIVATE_KEY else "❌ NOT SET"
    await update.message.reply_text(
        f"👑 *Admin Panel*\n\n"
        f"💰 {sol:.4f} SOL raised ({(sol/config.HARD_CAP_SOL*100):.1f}%)\n"
        f"👥 {buyers} buyers | 🪙 {int(tokens):,} TKB sold\n\n"
        f"*Presale wallet* (receives SOL)\n`{config.PRESALE_WALLET}`\nBalance: {presale_bal:.4f} SOL\n\n"
        f"*Airdrop wallet* (sends TKB)\n`{config.AIRDROP_WALLET}`\n"
        f"SOL: {airdrop_bal:.4f} | TKB: {airdrop_tkb:,.0f}\n"
        f"Private Key: {key_ok}\n\n"
        f"Mint: `{config.TOKEN_MINT}`\n"
        f"Status: {'✅ Active' if config.PRESALE_ACTIVE else '⏸ Paused'}",
        parse_mode="Markdown"
    )

async def button_handler(update, context):
    data = update.callback_query.data
    handlers = {
        "buy": buy, "mystats": my_stats, "status": presale_status,
        "howtobuy": how_to_buy,
        "connect_guide": connect_guide_callback,
    }
    if data in handlers:
        await handlers[data](update, context)
    elif data == "menu":
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Main menu 👇", reply_markup=main_menu_keyboard())

def build_bot():
    app = Application.builder().token(config.BOT_TOKEN).build()
    reg = ConversationHandler(
        entry_points=[CommandHandler("register", register_start),
                      CallbackQueryHandler(register_start, pattern="^register$")],
        states={REGISTER_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_wallet_handler)]},
        fallbacks=[], per_message=False, per_chat=True, per_user=True,
    )
    ver = ConversationHandler(
        entry_points=[CommandHandler("verify", verify_start),
                      CallbackQueryHandler(verify_start, pattern="^verify$")],
        states={VERIFY_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_tx_handler)]},
        fallbacks=[], per_message=False, per_chat=True, per_user=True,
    )
    for cmd, fn in [("start",start),("help",help_command),("buy",buy),
                    ("mystats",my_stats),("status",presale_status),
                    ("adminpanel",admin_panel),("connectguide",connect_guide_command),
                    ("verify",verify_start)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(reg)
    app.add_handler(ver)
    app.add_handler(CallbackQueryHandler(button_handler))
    return app

async def monitor_transactions(bot_app):
    logger.info("TX monitor started")
    seen = set()
    try:
        for tx in solana_utils.get_recent_transactions(50): seen.add(tx["signature"])
        logger.info(f"Pre-loaded {len(seen)} signatures")
    except Exception as e: logger.error(f"Pre-load: {e}")

    while True:
        try:
            await asyncio.sleep(30)
            for tx_info in solana_utils.get_recent_transactions(20):
                sig = tx_info["signature"]
                if sig in seen: continue
                seen.add(sig)
                parsed = solana_utils.get_sender_from_tx(sig)
                if not parsed["success"]: continue
                sender = parsed["sender"]
                amount_sol = parsed["amount_sol"]
                tokens = amount_sol / config.PRESALE_PRICE_SOL
                if db.tx_exists(sig): continue
                user_id = db.get_user_id_by_wallet(sender)
                username = db.get_username_by_wallet(sender) if user_id else "unknown"
                if not db.add_contribution(user_id or sender, username, sender, amount_sol, sig): continue
                tr = solana_utils.send_tokens(sender, tokens)
                logger.info(f"TX {sig[:16]}: {amount_sol} SOL → {int(tokens):,} TKB to {sender[:8]}")
                if user_id:
                    try:
                        if tr["success"] and tr.get("tx_signature") != "QUEUED":
                            note = (f"🎉 *Payment Confirmed!*\n\n"
                                    f"💵 *{amount_sol:.4f} SOL* received\n"
                                    f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* sent!\n"
                                    f"🔗 TX: `{tr['tx_signature']}`")
                        else:
                            note = (f"✅ *Payment Confirmed!*\n\n"
                                    f"💵 *{amount_sol:.4f} SOL* received\n"
                                    f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* allocated\n"
                                    f"📋 Tokens airdropped after presale ends!")
                        await bot_app.bot.send_message(
                            chat_id=user_id, text=note,
                            parse_mode="Markdown", reply_markup=main_menu_keyboard()
                        )
                    except Exception as e: logger.error(f"Notify {user_id}: {e}")
                for aid in config.ADMIN_IDS:
                    try:
                        await bot_app.bot.send_message(chat_id=aid, parse_mode="Markdown",
                            text=(f"💰 *New Contribution!*\n"
                                  f"👤 {user_id or 'unregistered'}\n"
                                  f"💵 {amount_sol:.4f} SOL → {int(tokens):,} TKB\n"
                                  f"👛 `{sender}`\n🔗 `{sig}`\n"
                                  f"Token TX: `{tr.get('tx_signature','N/A')}`"))
                    except Exception as e: logger.error(f"Notify admin {aid}: {e}")
        except Exception as e:
            logger.error(f"Monitor: {e}")
            await asyncio.sleep(30)

bot_app_global = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_app_global
    db.init_db()
    bot_app_global = build_bot()
    await bot_app_global.initialize()
    await bot_app_global.start()
    await bot_app_global.updater.start_polling()
    asyncio.create_task(monitor_transactions(bot_app_global))
    logger.info("TIKBIT Bot running!")
    yield
    await bot_app_global.updater.stop()
    await bot_app_global.stop()
    await bot_app_global.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if os.path.exists("miniapp"):
    app.mount("/miniapp", StaticFiles(directory="miniapp", html=True), name="miniapp")

class VerifyRequest(BaseModel):
    tx_signature: str
    wallet: str
    user_id: str
    username: str | None = None

@app.get("/")
def root():
    return {"status": "TIKBIT API running",
            "presale_wallet": config.PRESALE_WALLET,
            "airdrop_wallet": config.AIRDROP_WALLET}

@app.get("/presale/info")
def presale_info():
    sol, tokens, buyers = db.get_presale_stats()
    sol = sol or 0; tokens = tokens or 0
    return {
        "token_name": config.TOKEN_NAME, "token_symbol": config.TOKEN_SYMBOL,
        "price_sol": config.PRESALE_PRICE_SOL, "tokens_per_sol": int(1/config.PRESALE_PRICE_SOL),
        "hard_cap_sol": config.HARD_CAP_SOL, "soft_cap_sol": config.SOFT_CAP_SOL,
        "min_buy_sol": config.MIN_BUY_SOL, "max_buy_sol": config.MAX_BUY_SOL,
        "presale_wallet": config.PRESALE_WALLET, "airdrop_wallet": config.AIRDROP_WALLET,
        "token_mint": config.TOKEN_MINT, "presale_active": config.PRESALE_ACTIVE,
        "total_raised_sol": round(sol, 4), "total_tokens_sold": int(tokens),
        "unique_buyers": buyers, "progress_percent": round((sol/config.HARD_CAP_SOL)*100, 2),
    }

@app.post("/presale/verify")
def verify_payment_endpoint(req: VerifyRequest):
    if not solana_utils.is_valid_solana_address(req.wallet):
        raise HTTPException(400, "Invalid wallet address")
    if db.tx_exists(req.tx_signature):
        raise HTTPException(409, "Transaction already verified")
    result = solana_utils.verify_payment(req.tx_signature, req.wallet)
    if not result["success"]:
        raise HTTPException(400, result["message"])
    sol = result["amount_sol"]
    tokens = sol / config.PRESALE_PRICE_SOL
    if not db.add_contribution(req.user_id, req.username, req.wallet, sol, req.tx_signature):
        raise HTTPException(500, "Could not save")
    tr = solana_utils.send_tokens(req.wallet, tokens)
    return {"success": True, "amount_sol": sol, "tokens_allocated": int(tokens),
            "token_symbol": config.TOKEN_SYMBOL, "wallet": req.wallet,
            "tokens_sent": tr["success"], "token_tx": tr.get("tx_signature"),
            "message": f"{int(tokens):,} {config.TOKEN_SYMBOL} {'sent!' if tr['success'] else 'queued.'}"}

@app.get("/presale/stats/{user_id}")
def user_stats(user_id: str):
    sol, tokens, count = db.get_user_stats(user_id)
    return {"user_id": user_id, "wallet": db.get_wallet(user_id),
            "total_sol": round(sol or 0, 4), "total_tokens": int(tokens or 0),
            "tx_count": count or 0, "token_symbol": config.TOKEN_SYMBOL}