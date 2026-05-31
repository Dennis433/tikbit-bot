from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import config
import db
import solana_utils
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve mini app static files
if os.path.exists("miniapp"):
    app.mount("/miniapp", StaticFiles(directory="miniapp"), name="miniapp")

# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────

class VerifyRequest(BaseModel):
    tx_signature: str
    wallet: str
    user_id: str
    username: str | None = None

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.on_event("startup")
def startup():
    db.init_db()

@app.get("/")
def root():
    return {"status": "TIKBIT Presale API running"}

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

    saved = db.add_contribution(
        req.user_id,
        req.username,
        req.wallet,
        amount_sol,
        req.tx_signature
    )

    if not saved:
        raise HTTPException(status_code=500, detail="Could not save contribution")

    return {
        "success": True,
        "amount_sol": amount_sol,
        "tokens_allocated": int(tokens),
        "token_symbol": config.TOKEN_SYMBOL,
        "wallet": req.wallet,
        "message": f"Payment verified! {int(tokens):,} {config.TOKEN_SYMBOL} allocated."
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

@app.get("/miniapp")
def serve_miniapp():
    return FileResponse("miniapp/index.html")