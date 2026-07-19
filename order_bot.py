"""
ShardUp — Bot d'automatisation des commandes (Système Vouchère)
"""

import sqlite3
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shardup-bot")

app = Flask(__name__)
DB_PATH = "orders.db"

SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FROM_EMAIL    = os.environ.get("FROM_EMAIL", "")
ADMIN_KEY     = os.environ.get("ADMIN_KEY", "changeme123")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            server TEXT NOT NULL,
            amount INTEGER NOT NULL,
            price REAL NOT NULL,
            email TEXT,
            voucher_code TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            fulfilled_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            amount INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            used_at TEXT,
            order_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

def create_order(player_id, server, amount, price, email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO orders (player_id, server, amount, price, email, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (player_id, server, amount, price, email, datetime.utcnow().isoformat())
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id

def update_order_status(order_id, status, voucher_code=None):
    conn = sqlite3.connect(DB_PATH)
    if voucher_code:
        conn.execute(
            "UPDATE orders SET status=?, voucher_code=?, fulfilled_at=? WHERE id=?",
            (status, voucher_code, datetime.utcnow().isoformat(), order_id)
        )
    elif status == "fulfilled":
        conn.execute(
            "UPDATE orders SET status=?, fulfilled_at=? WHERE id=?",
            (status, datetime.utcnow().isoformat(), order_id)
        )
    else:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

def get_order(order_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_available_voucher(amount):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM vouchers WHERE amount=? AND used=0 LIMIT 1", (amount,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def mark_voucher_used(voucher_id, order_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE vouchers SET used=1, used_at=?, order_id=? WHERE id=?",
        (datetime.utcnow().isoformat(), order_id, voucher_id)
    )
    conn.commit()
    conn.close()def send_voucher_email(email, order_id, voucher_code, amount):
    if not SMTP_USER or not SMTP_PASSWORD:
        log.warning("[EMAIL] SMTP non configuré")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ShardUp — Votre code vouchère #{order_id}"
        msg["From"] = FROM_EMAIL
        msg["To"] = email
        html = f"""<html><body style="font-family:Arial;background:#0A0E1F;color:#EDEFFA;padding:30px;">
          <h2 style="color:#3DE8E0;">ShardUp 💎</h2>
          <p>Merci pour votre commande <strong>#{order_id}</strong>!</p>
          <p>Voici votre code pour <strong>{amount} diamants</strong>:</p>
          <div style="background:#161D3D;padding:20px;border-radius:10px;text-align:center;margin:20px 0;">
            <span style="font-size:24px;font-weight:bold;color:#3DE8E0;letter-spacing:4px;">{voucher_code}</span>
          </div>
          <p>Allez sur shop.garena.com, connectez-vous et entrez ce code.</p>
        </body></html>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, email, msg.as_string())
        log.info(f"[EMAIL] Code envoyé à {email}")
        return True
    except Exception as e:
        log.error(f"[EMAIL] Erreur: {e}")
        return False

def process_order(order_id):
    order = get_order(order_id)
    if not order:
        return
    voucher = get_available_voucher(order["amount"])
    if not voucher:
        update_order_status(order_id, "stock_epuise")
        return
    mark_voucher_used(voucher["id"], order_id)
    if order["email"]:
        send_voucher_email(order["email"], order_id, voucher["code"], order["amount"])
    update_order_status(order_id, "fulfilled", voucher["code"])

@app.route("/order", methods=["POST"])
def create_order_endpoint():
    data = request.get_json(force=True)
    if not all(k in data for k in ["player_id","server","amount","price"]):
        return jsonify({"error": "champs manquants"}), 400
    order_id = create_order(data["player_id"],data["server"],data["amount"],data["price"],data.get("email"))
    return jsonify({"order_id": order_id, "status": "pending"}), 201

@app.route("/webhook/payment-confirmed", methods=["POST"])
def payment_confirmed():
    data = request.get_json(force=True)
    order_id = data.get("order_id")
    if not order_id:
        return jsonify({"error": "order_id manquant"}), 400
    update_order_status(order_id, "paid")
    process_order(order_id)
    return jsonify({"status": "ok"}), 200

@app.route("/order/<int:order_id>", methods=["GET"])
def order_status(order_id):
    order = get_order(order_id)
    if not order:
        return jsonify({"error": "introuvable"}), 404
    return jsonify(order), 200

@app.route("/admin/vouchers", methods=["POST"])
def add_vouchers():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "non autorisé"}), 401
    data = request.get_json(force=True)
    codes = data.get("codes", [])
    amount = data.get("amount")
    if not codes or not amount:
        return jsonify({"error": "codes et amount requis"}), 400
    conn = sqlite3.connect(DB_PATH)
    added = 0
    for code in codes:
        try:
            conn.execute("INSERT INTO vouchers (code, amount) VALUES (?, ?)", (code.strip(), int(amount)))
            added += 1
        except:
            pass
    conn.commit()
    conn.close()
    return jsonify({"added": added}), 200

@app.route("/admin/stock", methods=["GET"])
def check_stock():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "non autorisé"}), 401
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT amount, COUNT(*) as total, SUM(CASE WHEN used=0 THEN 1 ELSE 0 END) as available FROM vouchers GROUP BY amount").fetchall()
    conn.close()
    return jsonify({"stock": [dict(r) for r in rows]}), 200

@app.route("/admin/orders", methods=["GET"])
def list_orders():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "non autorisé"}), 401
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify({"orders": [dict(r) for r in rows]}), 200

if __name__ == "__main__":
    init_db()
    log.info("Bot ShardUp démarré")
    app.run(host="0.0.0.0", port=5000)
