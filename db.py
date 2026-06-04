import sqlite3
import config

def init_db():
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        wallet TEXT NOT NULL,
        amount_sol REAL NOT NULL,
        tx_signature TEXT UNIQUE NOT NULL,
        tokens_allocated REAL NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS wallets (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        wallet TEXT NOT NULL,
        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    # Referrals: each referee is locked to ONE referrer.
    # rewarded: 0 = recorded (referee not yet bought), 2 = paying (lock),
    #           3 = qualified but awaiting referrer wallet, 1 = paid
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        referee_id TEXT PRIMARY KEY,
        referrer_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        rewarded INTEGER NOT NULL DEFAULT 0
    )""")
    # ── Migration: token delivery tracking on existing DBs ──
    # token_sent: 0 = not yet delivered, 1 = delivered (confirmed on-chain)
    # token_tx:   the delivery signature (set even while still confirming, so
    #             a retry can CHECK it before resending — prevents double-sends)
    # delivery_attempts: how many times we've tried, to cap runaway retries
    for ddl in (
        "ALTER TABLE contributions ADD COLUMN token_sent INTEGER DEFAULT 0",
        "ALTER TABLE contributions ADD COLUMN token_tx TEXT",
        "ALTER TABLE contributions ADD COLUMN delivery_attempts INTEGER DEFAULT 0",
    ):
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()

def register_wallet(user_id, username, wallet):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("""INSERT INTO wallets (user_id, username, wallet)
                 VALUES (?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET wallet=excluded.wallet""",
              (str(user_id), username, wallet))
    conn.commit()
    conn.close()

def get_wallet(user_id):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT wallet FROM wallets WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_id_by_wallet(wallet):
    """Find user_id from wallet address — used by transaction monitor"""
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM wallets WHERE wallet=?", (wallet,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_username_by_wallet(wallet):
    """Find username from wallet address"""
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT username FROM wallets WHERE wallet=?", (wallet,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def add_contribution(user_id, username, wallet, amount_sol, tx_signature):
    tokens = amount_sol / config.PRESALE_PRICE_SOL
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO contributions
                     (user_id, username, wallet, amount_sol, tx_signature, tokens_allocated)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (str(user_id), username, wallet, amount_sol, tx_signature, tokens))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("""SELECT SUM(amount_sol), SUM(tokens_allocated), COUNT(*)
                 FROM contributions WHERE user_id=?""", (str(user_id),))
    row = c.fetchone()
    conn.close()
    return row if row else (0, 0, 0)

def get_presale_stats():
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount_sol), SUM(tokens_allocated), COUNT(DISTINCT user_id) FROM contributions")
    row = c.fetchone()
    conn.close()
    return row if row else (0, 0, 0)

def tx_exists(tx_signature):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT id FROM contributions WHERE tx_signature=?", (tx_signature,))
    row = c.fetchone()
    conn.close()
    return row is not None

# ─────────────────────────────────────────
# REFERRALS
# ─────────────────────────────────────────

def record_referral(referee_id, referrer_id):
    """
    Attribute `referee_id` to `referrer_id`. Returns True if newly recorded.
    Rejects self-referral and any referee that already has a referrer
    (locked to the first one — can't be overwritten).
    """
    if str(referee_id) == str(referrer_id):
        return False
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO referrals (referee_id, referrer_id) VALUES (?, ?)",
                  (str(referee_id), str(referrer_id)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def claim_referral(referee_id, from_states=(0, 3)):
    """
    Atomically lock this referee's reward for payout: move it from any of
    `from_states` -> 2 (paying). Returns the referrer_id if WE won the lock,
    else None (already paid, being paid, or not referred). Guarantees a
    referral pays out at most once across all callers.

    Default claims from 0 (referee just made their first buy) OR 3 (referee
    already qualified earlier but the referrer had no wallet at the time).
    """
    states = tuple(from_states)
    placeholders = ",".join("?" * len(states))
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute(
        f"UPDATE referrals SET rewarded=2 WHERE referee_id=? AND rewarded IN ({placeholders})",
        (str(referee_id), *states),
    )
    conn.commit()
    if c.rowcount == 0:
        conn.close()
        return None
    c.execute("SELECT referrer_id FROM referrals WHERE referee_id=?", (str(referee_id),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def mark_referral_paid(referee_id):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE referrals SET rewarded=1 WHERE referee_id=?", (str(referee_id),))
    conn.commit()
    conn.close()

def hold_referral_qualified(referee_id):
    """
    Referee HAS qualified (made a buy) but we couldn't pay the referrer yet
    (no wallet, or a transient send issue): move 2 -> 3. The periodic pass
    and the referrer's wallet-registration both retry state-3 referrals.
    """
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE referrals SET rewarded=3 WHERE referee_id=? AND rewarded=2",
              (str(referee_id),))
    conn.commit()
    conn.close()

def release_referral(referee_id):
    """Return a claimed referral to pending (2 -> 0). Rarely needed now."""
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE referrals SET rewarded=0 WHERE referee_id=? AND rewarded=2",
              (str(referee_id),))
    conn.commit()
    conn.close()

def get_qualified_pending_referrals(referrer_id=None):
    """
    Referrals where the referee already qualified (bought) but the reward is
    still unpaid (state 3). Optionally filtered to one referrer.
    Returns list of {"referee_id", "referrer_id"}.
    """
    conn = sqlite3.connect("presale.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if referrer_id is None:
        c.execute("SELECT referee_id, referrer_id FROM referrals WHERE rewarded=3")
    else:
        c.execute("SELECT referee_id, referrer_id FROM referrals WHERE rewarded=3 AND referrer_id=?",
                  (str(referrer_id),))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_referral_count(referrer_id):
    """Number of successfully-rewarded referrals for this referrer."""
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND rewarded=1",
              (str(referrer_id),))
    n = c.fetchone()[0]
    conn.close()
    return n


# ─────────────────────────────────────────
# TOKEN DELIVERY TRACKING
# ─────────────────────────────────────────

def mark_token_sent(tx_signature, token_tx):
    """Mark a contribution's tokens as delivered (confirmed on-chain)."""
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE contributions SET token_sent=1, token_tx=? WHERE tx_signature=?",
              (token_tx, tx_signature))
    conn.commit()
    conn.close()

def set_pending_token_tx(tx_signature, token_tx):
    """
    Record a delivery signature that was submitted but not yet confirmed.
    Keeps token_sent=0 so the redelivery pass will re-CHECK this signature
    (not blindly resend) on the next loop.
    """
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE contributions SET token_tx=? WHERE tx_signature=?",
              (token_tx, tx_signature))
    conn.commit()
    conn.close()

def bump_delivery_attempts(tx_signature):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute("UPDATE contributions SET delivery_attempts = COALESCE(delivery_attempts,0) + 1 "
              "WHERE tx_signature=?", (tx_signature,))
    conn.commit()
    conn.close()

def get_undelivered_contributions(max_attempts=10):
    """
    Contributions whose tokens haven't been confirmed delivered yet
    (and haven't exhausted the retry cap). Returns dict rows.
    """
    conn = sqlite3.connect("presale.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT user_id, username, wallet, amount_sol, tokens_allocated, "
        "tx_signature, token_tx, COALESCE(delivery_attempts,0) AS delivery_attempts "
        "FROM contributions "
        "WHERE COALESCE(token_sent,0)=0 AND COALESCE(delivery_attempts,0) < ? "
        "ORDER BY id ASC",
        (max_attempts,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows