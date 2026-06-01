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
REGISTER_WALLET, VERIFY_TX, SENT_WAIT = range(3)

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
            [InlineKeyboardButton("✅ I've Sent SOL", callback_data="sent_sol")],
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
        "sent_sol": sent_sol_callback,
    }
    if data in handlers:
        await handlers[data](update, context)
    elif data == "menu":
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Main menu 👇", reply_markup=main_menu_keyboard())


async def sent_sol_callback(update, context):
    """User tapped 'I've Sent SOL' — trigger an immediate wallet scan."""
    q = update.callback_query
    await q.answer("Checking your wallet now... ⏳")
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if not wallet:
        await q.message.reply_text(
            "⚠️ You haven't registered a wallet yet!\n"
            "Use /register first, then send SOL.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👛 Register Wallet", callback_data="register")]
            ])
        )
        return
    await q.message.reply_text(
        f"🔍 *Scanning your wallet...*\n\n"
        f"Looking for incoming SOL from:\n`{wallet}`\n\n"
        f"This takes a few seconds...",
        parse_mode="Markdown"
    )
    result = await check_wallet_for_payment(user.id, user.username, wallet)
    if result["found"]:
        await q.message.reply_text(
            f"🎉 *Payment Found & Processed!*\n\n"
            f"💵 *{result['amount_sol']:.4f} SOL* received\n"
            f"🪙 *{int(result['tokens']):,} {config.TOKEN_SYMBOL}* allocated\n"
            f"👛 `{wallet}`\n"
            f"🔗 TX: `{result['tx_sig'][:20]}...`\n\n"
            f"{'✅ Tokens sent to your wallet!' if result.get('sent') else '📋 Tokens queued for airdrop!'}",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    elif result["already_recorded"]:
        sol, tokens, count = db.get_user_stats(str(user.id))
        await q.message.reply_text(
            f"✅ *Your payment is already recorded!*\n\n"
            f"💵 Total contributed: *{sol:.4f} SOL*\n"
            f"🪙 Tokens allocated: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n\n"
            f"Use /mystats to see your full history.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    else:
        await q.message.reply_text(
            f"⏳ *No payment detected yet.*\n\n"
            f"✅ *Step 1:* Your registered wallet:\n`{wallet}`\n\n"
            f"✅ *Step 2:* Send SOL *from that wallet* to:\n`{config.PRESALE_WALLET}`\n\n"
            f"✅ *Step 3:* Tap *Check Again* below\n\n"
            f"⚠️ *Common mistakes:*\n"
            f"• Sending from a *different* wallet than registered\n"
            f"• Sending less than *{config.MIN_BUY_SOL} SOL* (minimum)\n"
            f"• Transaction not confirmed yet (wait 30s)\n\n"
            f"💡 Tap *Check Again* after sending — we'll scan your full history.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again", callback_data="sent_sol")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
            ])
        )


async def check_wallet_for_payment(user_id, username, wallet: str) -> dict:
    """
    Scan for payments from a user's wallet to the presale wallet.
    Strategy:
      1. Check DB first — already recorded?
      2. Scan last 100 txs on presale wallet (covers old transactions)
      3. Also scan sender wallet's own tx history for any tx to presale wallet
    """
    result = {"found": False, "already_recorded": False,
              "amount_sol": 0, "tokens": 0, "tx_sig": "", "sent": False}
    try:
        # Step 1: Check if already in DB by wallet
        import sqlite3
        conn = sqlite3.connect("presale.db")
        row = conn.execute(
            "SELECT tx_signature, amount_sol, tokens_allocated FROM contributions WHERE wallet=?",
            (wallet,)
        ).fetchone()
        conn.close()
        if row:
            result["already_recorded"] = True
            result["tx_sig"] = row[0]
            result["amount_sol"] = row[1]
            result["tokens"] = row[2]
            return result

        # Step 2: Scan last 100 txs on presale wallet
        sigs_to_check = []
        recent = solana_utils.get_recent_transactions(100)
        for tx_info in recent:
            sigs_to_check.append(tx_info["signature"])

        # Step 3: Also scan the SENDER's own tx history
        # This catches old transactions the monitor missed
        try:
            sender_txs = solana_utils._rpc({
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [wallet, {"limit": 20}]
            })
            if sender_txs and sender_txs.get("result"):
                for tx_info in sender_txs["result"]:
                    sig = tx_info["signature"]
                    if sig not in sigs_to_check:
                        sigs_to_check.append(sig)
        except Exception as e:
            logger.warning(f"Sender tx scan failed: {e}")

        # Process all collected signatures
        for sig in sigs_to_check:
            if db.tx_exists(sig):
                # Check if it's this user's tx
                import sqlite3
                conn = sqlite3.connect("presale.db")
                row = conn.execute(
                    "SELECT amount_sol, tokens_allocated FROM contributions WHERE tx_signature=? AND wallet=?",
                    (sig, wallet)
                ).fetchone()
                conn.close()
                if row:
                    result["already_recorded"] = True
                    result["tx_sig"] = sig
                    result["amount_sol"] = row[0]
                    result["tokens"] = row[1]
                    return result
                continue

            parsed = solana_utils.get_sender_from_tx(sig)
            if not parsed["success"]:
                continue
            if parsed["sender"] != wallet:
                continue

            # Found matching payment — process it
            amount_sol = parsed["amount_sol"]
            tokens = amount_sol / config.PRESALE_PRICE_SOL

            saved = db.add_contribution(str(user_id), username, wallet, amount_sol, sig)
            if not saved:
                result["already_recorded"] = True
                return result

            logger.info(f"Manual check found TX {sig[:20]} | {amount_sol} SOL | {int(tokens):,} TKB")

            tr = solana_utils.send_tokens(wallet, tokens)
            if not tr["success"]:
                # Retry once
                import asyncio
                await asyncio.sleep(3)
                tr = solana_utils.send_tokens(wallet, tokens)

            result["found"] = True
            result["amount_sol"] = amount_sol
            result["tokens"] = tokens
            result["tx_sig"] = sig
            result["sent"] = tr["success"]
            return result

    except Exception as e:
        logger.error(f"check_wallet_for_payment error: {e}")
    return result

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
    """
    Bulletproof transaction monitor.
    - Polls every 20s (faster than before)
    - Double-checks every tx with db.tx_exists BEFORE and AFTER add_contribution
    - Retries token send up to 3 times on failure
    - Logs every step for auditability
    - Never processes same tx twice
    - Handles unregistered wallets (saves contribution, no Telegram notify)
    """
    logger.info("TX monitor started — polling every 20s")
    seen = set()

    # Pre-load ALL existing tx signatures from DB + recent chain
    # This prevents reprocessing on restart
    try:
        conn = __import__("sqlite3").connect("presale.db")
        rows = conn.execute("SELECT tx_signature FROM contributions").fetchall()
        conn.close()
        for r in rows:
            seen.add(r[0])
        logger.info(f"Loaded {len(seen)} existing tx signatures from DB")
    except Exception as e:
        logger.error(f"DB pre-load error: {e}")

    try:
        for tx in solana_utils.get_recent_transactions(50):
            seen.add(tx["signature"])
        logger.info(f"Total seen after chain pre-load: {len(seen)}")
    except Exception as e:
        logger.error(f"Chain pre-load error: {e}")

    while True:
        try:
            await asyncio.sleep(20)
            recent = solana_utils.get_recent_transactions(25)

            for tx_info in recent:
                sig = tx_info["signature"]

                # Fast check: already in seen set
                if sig in seen:
                    continue

                # Add to seen immediately to prevent parallel processing
                seen.add(sig)

                # Double-check DB (handles restart race conditions)
                if db.tx_exists(sig):
                    logger.info(f"TX {sig[:20]} already in DB, skipping")
                    continue

                # Parse the transaction
                parsed = solana_utils.get_sender_from_tx(sig)
                if not parsed["success"]:
                    logger.debug(f"TX {sig[:20]} not a valid presale payment")
                    continue

                sender = parsed["sender"]
                amount_sol = parsed["amount_sol"]
                tokens = amount_sol / config.PRESALE_PRICE_SOL

                logger.info(
                    f"NEW PAYMENT | TX: {sig[:20]} | "
                    f"Wallet: {sender[:12]} | "
                    f"Amount: {amount_sol:.4f} SOL | "
                    f"Tokens: {int(tokens):,} TKB"
                )

                # Look up registered user
                user_id = db.get_user_id_by_wallet(sender)
                username = db.get_username_by_wallet(sender) if user_id else "unregistered"

                # Save to DB — this is the authoritative record
                # add_contribution uses UNIQUE constraint on tx_signature
                # so even if called twice, only one record is created
                saved = db.add_contribution(
                    user_id or sender,
                    username,
                    sender,
                    amount_sol,
                    sig
                )
                if not saved:
                    logger.warning(
                        f"TX {sig[:20]} could not be saved — "
                        f"likely a race condition duplicate, skipping token send"
                    )
                    continue

                logger.info(f"TX {sig[:20]} saved to DB ✅")

                # Send tokens — retry up to 3 times
                tr = {"success": False, "tx_signature": None, "message": "Not attempted"}
                for attempt in range(1, 4):
                    tr = solana_utils.send_tokens(sender, tokens)
                    if tr["success"]:
                        logger.info(
                            f"Tokens sent ✅ | Attempt {attempt} | "
                            f"Token TX: {tr.get('tx_signature','QUEUED')}"
                        )
                        break
                    else:
                        logger.warning(
                            f"Token send attempt {attempt}/3 failed: {tr['message']}"
                        )
                        if attempt < 3:
                            await asyncio.sleep(5)

                if not tr["success"]:
                    logger.error(
                        f"ALL 3 TOKEN SEND ATTEMPTS FAILED for {sig[:20]} | "
                        f"Wallet: {sender} | Tokens: {int(tokens):,} | "
                        f"Error: {tr['message']} | "
                        f"MANUAL AIRDROP REQUIRED"
                    )

                # Notify buyer via Telegram (if registered)
                if user_id:
                    try:
                        if tr["success"] and tr.get("tx_signature") not in (None, "QUEUED"):
                            msg = (
                                f"🎉 *Payment Confirmed!*\n\n"
                                f"💵 Received: *{amount_sol:.4f} SOL*\n"
                                f"🪙 Sent: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                                f"👛 To: `{sender}`\n"
                                f"🔗 Token TX: `{tr['tx_signature'][:30]}...`\n\n"
                                f"✅ Tokens are in your wallet!"
                            )
                        elif tr.get("tx_signature") == "QUEUED":
                            msg = (
                                f"✅ *Payment Confirmed!*\n\n"
                                f"💵 Received: *{amount_sol:.4f} SOL*\n"
                                f"🪙 Allocated: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                                f"👛 Wallet: `{sender}`\n\n"
                                f"📋 Your tokens are recorded and will be airdropped after presale ends!"
                            )
                        else:
                            msg = (
                                f"⚠️ *Payment Received — Token Send Issue*\n\n"
                                f"💵 We received your *{amount_sol:.4f} SOL* ✅\n"
                                f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* is allocated to you.\n\n"
                                f"Our team will manually send your tokens shortly.\n"
                                f"Contact @tikbitcoincommunity if needed.\n"
                                f"TX: `{sig[:30]}...`"
                            )
                        await bot_app.bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            parse_mode="Markdown",
                            reply_markup=main_menu_keyboard()
                        )
                        logger.info(f"Notified user {user_id} ✅")
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id}: {e}")
                else:
                    logger.info(
                        f"Unregistered wallet {sender[:12]} sent {amount_sol:.4f} SOL — "
                        f"contribution recorded, no Telegram notification"
                    )

                # Always notify admins — regardless of token send status
                admin_msg = (
                    f"💰 *New Contribution!*\n\n"
                    f"👤 User: {user_id or 'UNREGISTERED'}\n"
                    f"💵 Amount: *{amount_sol:.4f} SOL*\n"
                    f"🪙 Tokens: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
                    f"👛 Wallet: `{sender}`\n"
                    f"🔗 SOL TX: `{sig}`\n"
                    f"📤 Token TX: `{tr.get('tx_signature', 'FAILED — MANUAL REQUIRED')}`\n"
                    f"Status: {'✅ Sent' if tr['success'] else '❌ FAILED — CHECK LOGS'}"
                )
                for aid in config.ADMIN_IDS:
                    try:
                        await bot_app.bot.send_message(
                            chat_id=aid,
                            text=admin_msg,
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {aid}: {e}")

        except Exception as e:
            logger.error(f"Monitor loop error: {e}", exc_info=True)
            await asyncio.sleep(20)

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

@app.get("/presale/check")
async def check_wallet_payment(wallet: str):
    """
    Called by mini app + bot when user taps I've Sent SOL.
    Scans BOTH presale wallet history AND sender wallet history.
    Works for old and new transactions.
    """
    if not solana_utils.is_valid_solana_address(wallet):
        raise HTTPException(400, "Invalid wallet address")

    try:
        import sqlite3 as _sqlite3

        # Step 1: check DB by wallet address first
        conn = _sqlite3.connect("presale.db")
        row = conn.execute(
            "SELECT tx_signature, amount_sol, tokens_allocated FROM contributions WHERE wallet=?",
            (wallet,)
        ).fetchone()
        conn.close()
        if row:
            return {
                "found": False,
                "already_recorded": True,
                "tx_signature": row[0],
                "amount_sol": row[1],
                "tokens_allocated": int(row[2]),
                "token_symbol": config.TOKEN_SYMBOL,
            }

        # Step 2: collect sigs from presale wallet (100) + sender wallet (20)
        sigs = []
        try:
            for tx in solana_utils.get_recent_transactions(100):
                sigs.append(tx["signature"])
        except Exception as e:
            logger.warning(f"Presale wallet scan failed: {e}")

        try:
            sender_data = solana_utils._rpc({
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [wallet, {"limit": 25}]
            })
            if sender_data and sender_data.get("result"):
                for tx in sender_data["result"]:
                    if tx["signature"] not in sigs:
                        sigs.append(tx["signature"])
        except Exception as e:
            logger.warning(f"Sender wallet scan failed: {e}")

        logger.info(f"check_wallet_payment: scanning {len(sigs)} txs for {wallet[:12]}")

        # Step 3: process each sig
        for sig in sigs:
            if db.tx_exists(sig):
                # Check if belongs to this wallet
                conn = _sqlite3.connect("presale.db")
                row = conn.execute(
                    "SELECT amount_sol, tokens_allocated FROM contributions WHERE tx_signature=? AND wallet=?",
                    (sig, wallet)
                ).fetchone()
                conn.close()
                if row:
                    return {
                        "found": False, "already_recorded": True,
                        "tx_signature": sig, "amount_sol": row[0],
                        "tokens_allocated": int(row[1]),
                        "token_symbol": config.TOKEN_SYMBOL,
                    }
                continue

            parsed = solana_utils.get_sender_from_tx(sig)
            if not parsed["success"] or parsed["sender"] != wallet:
                continue

            # Found — process it
            amount_sol = parsed["amount_sol"]
            tokens = amount_sol / config.PRESALE_PRICE_SOL
            user_id = db.get_user_id_by_wallet(wallet)
            username = db.get_username_by_wallet(wallet) if user_id else "unknown"

            saved = db.add_contribution(user_id or wallet, username, wallet, amount_sol, sig)
            if not saved:
                return {"found": False, "already_recorded": True,
                        "tx_signature": sig, "amount_sol": amount_sol,
                        "tokens_allocated": int(tokens), "token_symbol": config.TOKEN_SYMBOL}

            logger.info(f"check_wallet_payment FOUND: {sig[:20]} | {amount_sol} SOL | {int(tokens):,} TKB")

            # Send tokens with retry
            tr = {"success": False}
            for attempt in range(3):
                tr = solana_utils.send_tokens(wallet, tokens)
                if tr["success"]:
                    break
                import asyncio as _asyncio
                await _asyncio.sleep(3)

            if not tr["success"]:
                logger.error(f"Token send failed after 3 attempts for {sig[:20]}")

            # Notify Telegram
            if user_id and bot_app_global:
                try:
                    if tr["success"] and tr.get("tx_signature") not in (None, "QUEUED"):
                        msg = (f"🎉 *Payment Confirmed!*\n\n"
                               f"💵 *{amount_sol:.4f} SOL* received\n"
                               f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* sent to your wallet!\n"
                               f"🔗 TX: `{tr['tx_signature'][:30]}...`")
                    else:
                        msg = (f"✅ *Payment Confirmed!*\n\n"
                               f"💵 *{amount_sol:.4f} SOL* received\n"
                               f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* allocated\n"
                               f"📋 Tokens airdropped after presale ends!")
                    await bot_app_global.bot.send_message(
                        chat_id=user_id, text=msg,
                        parse_mode="Markdown", reply_markup=main_menu_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Telegram notify failed: {e}")

            # Notify admins
            for aid in config.ADMIN_IDS:
                try:
                    if bot_app_global:
                        await bot_app_global.bot.send_message(
                            chat_id=aid, parse_mode="Markdown",
                            text=(f"💰 *New Contribution!*\n"
                                  f"👤 {user_id or 'UNREGISTERED'}\n"
                                  f"💵 {amount_sol:.4f} SOL → {int(tokens):,} TKB\n"
                                  f"👛 `{wallet}`\n🔗 `{sig}`\n"
                                  f"Token TX: `{tr.get('tx_signature','FAILED')}`"))
                except Exception as e:
                    logger.error(f"Admin notify failed: {e}")

            return {
                "found": True,
                "amount_sol": amount_sol,
                "tokens_allocated": int(tokens),
                "token_symbol": config.TOKEN_SYMBOL,
                "tx_signature": sig,
                "tokens_sent": tr["success"],
                "already_recorded": False,
            }

        return {"found": False, "already_recorded": False}

    except Exception as e:
        logger.error(f"check_wallet_payment error: {e}", exc_info=True)
        raise HTTPException(500, f"Server error: {str(e)}")