"""
ShardUp — Bot d'automatisation des commandes
"""

import sqlite3
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shardup-bot")

app = Flask(__name__)
DB_PATH = "orders.db"


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
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            fulfilled_at TEXT
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


def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_PATH)
    if status == "fulfilled":
        conn.execute(
            "UPDATE orders SET status = ?, fulfilled_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), order_id)
        )
    else:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()


def get_order(order_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if None else None
  def deliver_diamonds(player_id: str, server: str, amount: int) -> bool:
    """
    Cette fonction doit appeler l'API de ton fournisseur de diamants
    pour livrer réellement la recharge sur le compte du joueur.
    Pour l'instant, cette fonction est simulée : elle ne livre rien de réel.
    """
    log.info(f"[SIMULATION] Livraison de {amount} diamants à {player_id} ({server})")
    time.sleep(1)
    return True


def notify_customer(email: str, order_id: int, status: str):
    if not email:
        return
    log.info(f"[EMAIL SIMULÉ] à {email} — commande #{order_id} : statut = {status}")


def process_order(order_id: int):
    order = get_order(order_id)
    if not order:
        log.error(f"Commande {order_id} introuvable")
        return

    log.info(f"Traitement de la commande #{order_id} ({order['amount']} diamants)")
    success = deliver_diamonds(order["player_id"], order["server"], order["amount"])

    if success:
        update_order_status(order_id, "fulfilled")
        notify_customer(order["email"], order_id, "livrée")
        log.info(f"Commande #{order_id} livrée avec succès")
    else:
        update_order_status(order_id, "failed")
        notify_customer(order["email"], order_id, "échec — support à contacter")
        log.warning(f"Échec de la commande #{order_id}")


@app.route("/order", methods=["POST"])
def create_order_endpoint():
    data = request.get_json(force=True)
    required = ["player_id", "server", "amount", "price"]
    if not all(k in data for k in required):
        return jsonify({"error": "champs manquants"}), 400

    order_id = create_order(
        player_id=data["player_id"],
        server=data["server"],
        amount=data["amount"],
        price=data["price"],
        email=data.get("email"),
    )
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


if __name__ == "__main__":
    init_db()
    log.info("Bot de commandes démarré")
    app.run(host="0.0.0.0", port=5000)
