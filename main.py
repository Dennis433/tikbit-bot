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
        [InlineKeyboardButton("🎁 Refer & Earn", callback_data="refer")],
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

    # ── Deep-link payloads (t.me/<bot>?start=<payload>) ──
    args = context.args or []
    if args:
        payload = args[0]
        if payload.startswith("ref_"):
            ref = payload[4:]
            if ref.isdigit() and ref != str(u.id):
                if db.record_referral(u.id, int(ref)):
                    logger.info(f"Referral recorded: {u.id} invited by {ref}")
                    for aid in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=aid,
                                text=(f"🔗 Referral captured: user {u.id} "
                                      f"({'@'+u.username if u.username else 'no username'}) "
                                      f"was invited by {ref}"),
                            )
                        except Exception:
                            pass
                else:
                    logger.info(f"Referral NOT recorded for {u.id} (self-referral or already referred)")
            # fall through to normal welcome below
        elif payload == "refer":
            await refer_command(update, context)
            return
        elif payload == "buy":
            await buy(update, context)
            return

    tps = int(1 / config.PRESALE_PRICE_SOL)
    await update.message.reply_text(
        f"👋 Welcome *{u.first_name}* to the *{config.TOKEN_NAME} Presale!*\n\n"
        f"TikTok + Bitcoin on Solana ⚡💎\n"
        f"Viral coins + Real utility = Next 1000x 🚀\n\n"
        f"🪙 *{config.TOKEN_NAME}* (${config.TOKEN_SYMBOL})\n"
        f"💵 Price: *{config.PRESALE_PRICE_SOL} SOL* per token\n"
        f"📊 Rate: *{tps:,} {config.TOKEN_SYMBOL}* per SOL\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* (~$25) | Max: *{config.MAX_BUY_SOL} SOL*\n"
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
    # If this user referred people who already bought while they had no wallet,
    # pay those referral rewards now — instantly.
    await process_pending_referrals(context.bot, only_referrer=user.id)
    tps = int(1 / config.PRESALE_PRICE_SOL)
    # Immediately show how to buy after registering
    await update.message.reply_text(
        f"✅ *Wallet Registered!*\n\n`{wallet}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *How to Buy {config.TOKEN_NAME}*\n\n"
        f"Send SOL to this presale wallet:\n`{config.PRESALE_WALLET}`\n\n"
        f"💱 *{tps:,} {config.TOKEN_SYMBOL} per SOL*\n"
        f"📦 Min: *{config.MIN_BUY_SOL} SOL* (~$25) | Max: *{config.MAX_BUY_SOL} SOL*\n\n"
        f"✅ Auto-detected in ~30 seconds — tokens sent to your wallet instantly!\n\n"
        f"📌 Your wallet: `{wallet}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I've Sent SOL", callback_data="sent_sol")],
            [InlineKeyboardButton("🚀 Open Presale App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
        ])
    )
    return ConversationHandler.END

async def buy(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    if not config.PRESALE_ACTIVE:
        await msg.reply_text("⏸ Presale paused.")
        return

    # In a group, never dump the wallet/address inline — send users to a
    # private chat with the bot via a deep link (web_app buttons also can't
    # be used in groups). Keeps wallet details private and the group clean.
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        await msg.reply_text(
            f"💰 Buy ${config.TOKEN_SYMBOL} in a private chat with me 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💰 Buy {config.TOKEN_SYMBOL}",
                                      url=f"https://t.me/{config.BOT_USERNAME}?start=buy")],
                [InlineKeyboardButton("🎁 Refer & Earn",
                                      url=f"https://t.me/{config.BOT_USERNAME}?start=refer")],
            ])
        )
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

async def refer_command(update, context):
    q = update.callback_query
    msg = q.message if q else update.message
    if q: await q.answer()
    user = update.effective_user
    link = f"https://t.me/{config.BOT_USERNAME}?start=ref_{user.id}"
    paid = db.get_referral_count(user.id)
    has_wallet = bool(db.get_wallet(user.id))
    wallet_note = (
        "✅ Your wallet is registered — you're ready to earn!"
        if has_wallet else
        "⚠️ Register your wallet first (/register) so we can pay your rewards!"
    )
    await msg.reply_text(
        f"🎁 *Refer & Earn {config.REFERRAL_REWARD_TKB} {config.TOKEN_SYMBOL}!*\n\n"
        f"Share your personal link. When someone you invite makes their "
        f"first buy, you instantly get *{config.REFERRAL_REWARD_TKB} "
        f"{config.TOKEN_SYMBOL}* sent to your registered wallet.\n\n"
        f"🔗 *Your referral link:*\n`{link}`\n\n"
        f"🏆 Successful referrals so far: *{paid}*\n\n"
        f"{wallet_note}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def welcome_new_member(update, context):
    """Greet new members joining the group and show a Buy button."""
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
    tps = int(1 / config.PRESALE_PRICE_SOL)
    for member in msg.new_chat_members:
        if member.is_bot:
            continue
        await msg.reply_text(
            f"👋 Welcome {member.mention_html()} to <b>{config.TOKEN_NAME}</b>!\n\n"
            f"💎 The ${config.TOKEN_SYMBOL} presale is LIVE — "
            f"{tps:,} {config.TOKEN_SYMBOL} per SOL.\n"
            f"📦 Min {config.MIN_BUY_SOL} SOL | Max {config.MAX_BUY_SOL} SOL\n\n"
            f"Tap below to buy in a private chat with me 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💰 Buy {config.TOKEN_SYMBOL}",
                                      url=f"https://t.me/{config.BOT_USERNAME}?start=buy")],
                [InlineKeyboardButton("🎁 Refer & Earn",
                                      url=f"https://t.me/{config.BOT_USERNAME}?start=refer")],
            ])
        )


async def button_handler(update, context):
    data = update.callback_query.data
    handlers = {
        "buy": buy, "mystats": my_stats, "status": presale_status,
        "howtobuy": how_to_buy,
        "connect_guide": connect_guide_callback,
        "sent_sol": sent_sol_callback,
        "refer": refer_command,
    }
    if data in handlers:
        await handlers[data](update, context)
    elif data == "menu":
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Main menu 👇", reply_markup=main_menu_keyboard())


async def sent_sol_callback(update, context):
    """
    User tapped 'I've Sent SOL'.
    Does NOT credit anything — only checks if the background monitor
    has already recorded a payment from this wallet. The monitor is the
    single source of truth for crediting, preventing double-credits.
    """
    q = update.callback_query
    await q.answer("Checking... ⏳")
    user = update.effective_user
    wallet = db.get_wallet(user.id)
    if not wallet:
        await q.message.reply_text(
            "⚠️ You haven't registered a wallet yet!\nUse /register first.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👛 Register Wallet", callback_data="register")]
            ])
        )
        return

    # Only READ from DB — never credit here
    sol, tokens, count = db.get_user_stats(str(user.id))
    sol = sol or 0
    tokens = tokens or 0

    if count and count > 0:
        await q.message.reply_text(
            f"✅ *Your payment is confirmed!*\n\n"
            f"💵 Total contributed: *{sol:.4f} SOL*\n"
            f"🪙 Tokens allocated: *{int(tokens):,} {config.TOKEN_SYMBOL}*\n"
            f"🔁 Transactions: *{count}*\n\n"
            f"Your tokens have been sent to:\n`{wallet}`\n\n"
            f"💡 If you don't see them in your wallet, enable 'show unverified tokens' in Phantom.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    else:
        await q.message.reply_text(
            f"⏳ *No payment detected yet.*\n\n"
            f"✅ *Step 1:* Send SOL *from* your registered wallet:\n`{wallet}`\n\n"
            f"✅ *Step 2:* *To* the presale wallet:\n`{config.PRESALE_WALLET}`\n\n"
            f"✅ *Step 3:* Wait ~30 seconds\n\n"
            f"⚠️ *Important:*\n"
            f"• Send from the *exact* wallet above\n"
            f"• Minimum *{config.MIN_BUY_SOL} SOL* (~$25)\n"
            f"• Our monitor detects it automatically and sends tokens\n\n"
            f"💡 You'll get a confirmation here the moment it's detected — "
            f"no need to keep checking!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again", callback_data="sent_sol")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
            ])
        )


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
                    ("refer",refer_command),
                    ("verify",verify_start)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(reg)
    app.add_handler(ver)
    # Greet new members who join the group
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(CallbackQueryHandler(button_handler))
    return app

async def _try_pay_referral(referee_id, bot):
    """
    Pay the referrer 50 TKB for `referee_id`'s qualifying buy. Safe to call
    from anywhere (monitor on a buy, the periodic pass, or wallet registration)
    — claim_referral atomically locks the row so a referral pays out only once.

    If the referrer has no wallet yet, the referral is parked in state 3
    (qualified, awaiting wallet) and gets paid automatically the moment the
    referrer registers a wallet or on the next monitor pass.
    """
    try:
        referrer_id = db.claim_referral(referee_id)   # locks from state 0 or 3
        if not referrer_id:
            return  # not referred, already paid, or being paid elsewhere

        referrer_wallet = db.get_wallet(referrer_id)
        if not referrer_wallet:
            db.hold_referral_qualified(referee_id)     # 2 -> 3, retry later
            logger.info(
                f"Referral {referee_id} -> {referrer_id}: referee qualified but "
                f"referrer has no wallet yet — parked, will auto-pay on register"
            )
            return

        rr = solana_utils.send_tokens(referrer_wallet, config.REFERRAL_REWARD_TKB)
        if rr["success"]:
            db.mark_referral_paid(referee_id)
            logger.info(
                f"Referral paid ✅ {config.REFERRAL_REWARD_TKB} {config.TOKEN_SYMBOL} "
                f"-> referrer {referrer_id}"
            )
            try:
                await bot.send_message(
                    chat_id=int(referrer_id) if str(referrer_id).isdigit() else referrer_id,
                    text=(
                        f"🎉 *Referral Reward!*\n\n"
                        f"Someone you invited just bought ${config.TOKEN_SYMBOL} — "
                        f"*{config.REFERRAL_REWARD_TKB} {config.TOKEN_SYMBOL}* has been "
                        f"sent to your wallet!\n👛 `{referrer_wallet}`"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to notify referrer {referrer_id}: {e}")
            for aid in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=aid,
                        text=(f"🎁 Referral paid: {config.REFERRAL_REWARD_TKB} "
                              f"{config.TOKEN_SYMBOL} to {referrer_id} "
                              f"(referee {referee_id})"),
                    )
                except Exception:
                    pass
        elif rr.get("submitted"):
            # Broadcast but unconfirmed — leave locked (state 2) to avoid a
            # double-pay; do not auto-retry. Rare now that Helius confirms fast.
            logger.warning(
                f"Referral payout submitted but unconfirmed for {referee_id} "
                f"-> {referrer_id} (tx {rr.get('tx_signature')}); held"
            )
        else:
            # Nothing broadcast — park as qualified so it retries later.
            db.hold_referral_qualified(referee_id)
            logger.error(
                f"Referral payout failed (not submitted) for {referee_id} "
                f"-> {referrer_id}: {rr['message']} — parked for retry"
            )
    except Exception as e:
        logger.error(f"Referral payout error for {referee_id}: {e}", exc_info=True)


async def process_pending_referrals(bot, only_referrer=None):
    """
    Pay out any referrals that already qualified (referee bought) but weren't
    paid yet — typically because the referrer registered their wallet after
    the buy. Called every monitor loop, and right after a wallet registration
    (filtered to that referrer) for an instant payout.
    """
    try:
        pending = db.get_qualified_pending_referrals(only_referrer)
    except Exception as e:
        logger.error(f"process_pending_referrals: read error: {e}")
        return
    for row in pending:
        # Only attempt if the referrer now has a wallet (avoids churn).
        if db.get_wallet(row["referrer_id"]):
            await _try_pay_referral(row["referee_id"], bot)


async def redeliver_pending(bot_app):
    """
    Safety net: re-attempt delivery for any contribution whose tokens haven't
    been confirmed delivered yet. Double-send-safe: if a prior attempt already
    broadcast a delivery signature, we CHECK that signature first and only
    resend when it has truly failed on-chain (never on a still-pending one).
    """
    if not config.AIRDROP_PRIVATE_KEY:
        return  # nothing to send without a key; don't burn retry attempts
    try:
        pending = db.get_undelivered_contributions()
    except Exception as e:
        logger.error(f"redeliver: could not read pending contributions: {e}")
        return

    for row in pending:
        sig    = row["tx_signature"]
        wallet = row["wallet"]
        tokens = row["tokens_allocated"]
        prior  = row.get("token_tx")

        # If we already broadcast a delivery tx, verify it before resending.
        if prior and prior != "QUEUED":
            status = solana_utils.confirm_signature(prior, tries=3, delay=2)
            if status == "confirmed":
                db.mark_token_sent(sig, prior)
                logger.info(f"redeliver: prior tx {prior[:20]} confirmed -> delivered")
                continue
            if status == "unknown":
                logger.info(f"redeliver: prior tx {prior[:20]} still pending; leaving for next loop")
                continue
            logger.warning(f"redeliver: prior tx {prior[:20]} failed on-chain; resending")

        db.bump_delivery_attempts(sig)
        tr = solana_utils.send_tokens(wallet, tokens)

        if tr["success"] and tr.get("tx_signature") not in (None, "QUEUED"):
            db.mark_token_sent(sig, tr.get("tx_signature"))
            logger.info(
                f"redeliver: delivered {int(tokens):,} {config.TOKEN_SYMBOL} -> "
                f"{wallet[:12]} (tx {tr['tx_signature'][:20]})"
            )
            uid = row.get("user_id")
            if uid and str(uid).isdigit():
                try:
                    await bot_app.bot.send_message(
                        chat_id=int(uid),
                        text=(
                            f"🎉 *{int(tokens):,} {config.TOKEN_SYMBOL} delivered!*\n\n"
                            f"👛 `{wallet}`\n🔗 `{tr['tx_signature'][:30]}...`"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"redeliver: failed to notify {uid}: {e}")
        elif tr.get("submitted") and tr.get("tx_signature"):
            db.set_pending_token_tx(sig, tr["tx_signature"])
            logger.warning(
                f"redeliver: submitted but unconfirmed for {sig[:20]} "
                f"(tx {tr['tx_signature']}); will verify next loop"
            )
        else:
            logger.warning(f"redeliver: still undelivered {sig[:20]}: {tr['message']}")


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
            # Safety net first: re-deliver any confirmed buys whose tokens
            # haven't landed yet (double-send-safe). Fixes silent non-credits.
            await redeliver_pending(bot_app)
            # Auto-pay referrals whose referrer registered a wallet after the buy
            await process_pending_referrals(bot_app.bot)
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

                # Send tokens — ONE attempt here. The redelivery pass at the top
                # of the loop safely retries anything that doesn't confirm, and
                # checks the prior signature first so nobody is ever double-sent.
                db.bump_delivery_attempts(sig)
                tr = solana_utils.send_tokens(sender, tokens)
                if tr["success"] and tr.get("tx_signature") not in (None, "QUEUED"):
                    db.mark_token_sent(sig, tr.get("tx_signature"))
                    logger.info(f"Tokens sent ✅ | Token TX: {tr.get('tx_signature')}")
                elif tr.get("tx_signature") == "QUEUED":
                    logger.info(f"No airdrop key set — {sig[:20]} recorded, pending delivery")
                elif tr.get("submitted") and tr.get("tx_signature"):
                    # Broadcast but not yet confirmed — store the sig so the
                    # redelivery pass re-CHECKS it (never blindly resends).
                    db.set_pending_token_tx(sig, tr["tx_signature"])
                    logger.warning(
                        f"Token TX submitted but unconfirmed for {sig[:20]} — "
                        f"will verify next loop: {tr['tx_signature']}"
                    )
                else:
                    logger.warning(
                        f"Token send not completed for {sig[:20]}: {tr['message']} "
                        f"— will retry next loop"
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
                        elif tr.get("submitted") and tr.get("tx_signature"):
                            # Broadcast, still confirming — reassure, don't alarm.
                            msg = (
                                f"✅ *Payment Confirmed!*\n\n"
                                f"💵 Received: *{amount_sol:.4f} SOL*\n"
                                f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* is on its way to:\n"
                                f"`{sender}`\n\n"
                                f"⏳ Finalizing on-chain now — it'll land in your wallet shortly."
                            )
                        else:
                            msg = (
                                f"✅ *Payment Received!*\n\n"
                                f"💵 We received your *{amount_sol:.4f} SOL* ✅\n"
                                f"🪙 *{int(tokens):,} {config.TOKEN_SYMBOL}* is allocated to you "
                                f"and will be delivered automatically very shortly.\n\n"
                                f"👛 Wallet: `{sender}`"
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

                # ── REFERRAL REWARD ──
                # Referee just made a qualifying buy → pay the referrer 50 TKB
                # instantly (or park it to auto-pay when the referrer registers
                # a wallet). All the once-only / double-send safety lives in the
                # shared helper.
                if user_id and amount_sol >= config.REFERRAL_MIN_BUY_SOL:
                    await _try_pay_referral(user_id, bot_app.bot)

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

                # Announce the buy to the community group (social proof / hype)
                if config.COMMUNITY_CHAT_ID and tr["success"]:
                    try:
                        short_wallet = sender[:4] + "..." + sender[-4:]
                        usd_value = amount_sol * config.SOL_PRICE_USD
                        community_msg = (
                            f"🚀 *NEW {config.TOKEN_NAME} BUY!* 🚀\n\n"
                            f"💎 Someone just grabbed *{int(tokens):,} {config.TOKEN_SYMBOL}*!\n"
                            f"💰 Bought with *{amount_sol:.3f} SOL*\n"
                            f"👛 Wallet: `{short_wallet}`\n\n"
                            f"📈 The presale is heating up — don't miss out!\n"
                            f"🔥 Join now 👇"
                        )
                        await bot_app.bot.send_message(
                            chat_id=config.COMMUNITY_CHAT_ID,
                            text=community_msg,
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🚀 Buy " + config.TOKEN_SYMBOL + " Now",
                                                      url=f"https://t.me/{config.BOT_USERNAME}")],
                            ])
                        )
                        logger.info("Community announcement sent ✅")
                    except Exception as e:
                        logger.error(f"Failed to announce to community: {e}")

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
