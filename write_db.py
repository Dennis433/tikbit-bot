content = open('db.py', 'w', encoding='utf-8')
content.write("""import sqlite3
import config

def init_db():
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        wallet TEXT NOT NULL,
        amount_sol REAL NOT NULL,
        tx_signature TEXT UNIQUE NOT NULL,
        tokens_allocated REAL NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS wallets (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        wallet TEXT NOT NULL,
        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def register_wallet(user_id, username, wallet):
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    c.execute('''INSERT INTO wallets (user_id, username, wallet)
                 VALUES (?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET wallet=excluded.wallet''',
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

def add_contribution(user_id, username, wallet, amount_sol, tx_signature):
    tokens = amount_sol / config.PRESALE_PRICE_SOL
    conn = sqlite3.connect("presale.db")
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO contributions
                     (user_id, username, wallet, amount_sol, tx_signature, tokens_allocated)
                     VALUES (?, ?, ?, ?, ?, ?)''',
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
    c.execute('''SELECT SUM(amount_sol), SUM(tokens_allocated), COUNT(*)
                 FROM contributions WHERE user_id=?''', (str(user_id),))
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
""")
content.close()
print("db.py written successfully!")