"""
PayRail — Payment Switch (the central routing brain).
Routes payments between independent banks using UPI-style IDs.

Payment Flow:
  1. Parse sender@bankX and receiver@bankY
  2. Route to correct bank services
  3. Debit sender's bank
  4. Credit receiver's bank
  5. If credit fails → auto-reverse the debit
"""

import os
import sys
import uuid
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Configuration ────────────────────────────────────────────────────────
app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), "..", "dashboard", "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "..", "dashboard", "static"))
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SWITCH] %(message)s")
logger = logging.getLogger(__name__)

# Bank registry — maps bank suffix to its service URL
BANK_REGISTRY = {
    "bankA": os.environ.get("BANK_A_URL", "http://127.0.0.1:5001"),
    "bankB": os.environ.get("BANK_B_URL", "http://127.0.0.1:5002"),
}

# In-memory store for switch-level transaction tracking
switch_transactions = []

# Failure injection flag (for demo)
INJECT_CREDIT_FAILURE = False


# ── Helpers ──────────────────────────────────────────────────────────────

def parse_upi_id(upi_id: str):
    """Parse 'user@bank' into (user, bank_key)."""
    if "@" not in upi_id:
        return None, None
    parts = upi_id.split("@", 1)
    return parts[0], parts[1]


def get_bank_url(bank_key: str):
    """Resolve bank key to its service URL."""
    return BANK_REGISTRY.get(bank_key)


def record_switch_txn(txn_data):
    """Record transaction at switch level for dashboard."""
    txn_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    switch_transactions.insert(0, txn_data)
    # Keep last 200 transactions
    if len(switch_transactions) > 200:
        switch_transactions.pop()


# ── Payment Endpoint ────────────────────────────────────────────────────

@app.route("/pay", methods=["POST"])
def pay():
    """
    Execute a payment from sender to receiver across banks.

    Request JSON:
        {
            "sender": "asha@bankA",
            "receiver": "neha@bankB",
            "amount": 1000,
            "idempotency_key": "optional-unique-key"
        }

    The switch:
    1. Debits sender's bank
    2. Credits receiver's bank
    3. If credit fails → reverses the debit
    """
    data = request.get_json()
    if not data or "sender" not in data or "receiver" not in data or "amount" not in data:
        return jsonify({"error": "Missing sender, receiver, or amount"}), 400

    sender = data["sender"]
    receiver = data["receiver"]
    amount = float(data["amount"])
    idempotency_key = data.get("idempotency_key", str(uuid.uuid4()))
    txn_id = str(uuid.uuid4())

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    # Parse UPI IDs
    _, sender_bank = parse_upi_id(sender)
    _, receiver_bank = parse_upi_id(receiver)

    if not sender_bank or not get_bank_url(sender_bank):
        return jsonify({"error": f"Unknown sender bank: {sender_bank}"}), 400
    if not receiver_bank or not get_bank_url(receiver_bank):
        return jsonify({"error": f"Unknown receiver bank: {receiver_bank}"}), 400

    sender_url = get_bank_url(sender_bank)
    receiver_url = get_bank_url(receiver_bank)

    logger.info(f"Payment: {sender} → {receiver}, ₹{amount} [txn:{txn_id}]")

    # ── Step 1: Debit sender ────────────────────────────────────────
    try:
        debit_res = requests.post(f"{sender_url}/debit", json={
            "upi_id": sender,
            "amount": amount,
            "idempotency_key": idempotency_key,
            "transaction_id": txn_id,
            "receiver_upi": receiver,
        }, timeout=10)

        if debit_res.status_code != 200:
            reason = debit_res.json().get("reason", "Debit failed")
            logger.warning(f"Debit failed: {reason}")
            record_switch_txn({
                "id": txn_id, "sender": sender, "receiver": receiver,
                "amount": amount, "status": "failed", "step": "debit",
                "reason": reason,
            })
            return jsonify({
                "transaction_id": txn_id,
                "status": "failed",
                "step": "debit",
                "reason": reason,
            }), 400
    except requests.exceptions.RequestException as e:
        logger.error(f"Debit request failed: {e}")
        record_switch_txn({
            "id": txn_id, "sender": sender, "receiver": receiver,
            "amount": amount, "status": "failed", "step": "debit",
            "reason": f"Bank service unreachable: {sender_bank}",
        })
        return jsonify({
            "transaction_id": txn_id,
            "status": "failed",
            "step": "debit",
            "reason": f"Sender bank ({sender_bank}) is unreachable",
        }), 503

    logger.info(f"Debit successful for {sender}")

    # ── Step 2: Credit receiver ─────────────────────────────────────
    try:
        credit_payload = {
            "upi_id": receiver,
            "amount": amount,
            "transaction_id": txn_id,
            "sender_upi": sender,
        }

        # Failure injection for demo
        if INJECT_CREDIT_FAILURE:
            credit_payload["simulate_failure"] = True

        credit_res = requests.post(f"{receiver_url}/credit", json=credit_payload, timeout=10)

        if credit_res.status_code != 200:
            reason = credit_res.json().get("reason", "Credit failed")
            logger.warning(f"Credit failed: {reason} — initiating reversal")

            # ── Step 3: Reverse debit ───────────────────────────────
            _reverse_debit(sender_url, txn_id, reason)

            record_switch_txn({
                "id": txn_id, "sender": sender, "receiver": receiver,
                "amount": amount, "status": "reversed", "step": "credit_failed",
                "reason": reason,
            })
            return jsonify({
                "transaction_id": txn_id,
                "status": "reversed",
                "step": "credit_failed_and_reversed",
                "reason": reason,
            }), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"Credit request failed: {e} — initiating reversal")
        _reverse_debit(sender_url, txn_id, f"Receiver bank unreachable: {receiver_bank}")

        record_switch_txn({
            "id": txn_id, "sender": sender, "receiver": receiver,
            "amount": amount, "status": "reversed", "step": "credit_failed",
            "reason": f"Receiver bank ({receiver_bank}) unreachable",
        })
        return jsonify({
            "transaction_id": txn_id,
            "status": "reversed",
            "step": "credit_failed_and_reversed",
            "reason": f"Receiver bank ({receiver_bank}) is unreachable",
        }), 200

    # ── Success ─────────────────────────────────────────────────────
    logger.info(f"Payment completed: {sender} → {receiver}, ₹{amount}")
    record_switch_txn({
        "id": txn_id, "sender": sender, "receiver": receiver,
        "amount": amount, "status": "completed", "step": "done",
        "reason": None,
    })

    return jsonify({
        "transaction_id": txn_id,
        "status": "completed",
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
    }), 200


def _reverse_debit(sender_url, txn_id, reason):
    """Call sender bank's reverse endpoint."""
    try:
        rev_res = requests.post(f"{sender_url}/reverse", json={
            "transaction_id": txn_id,
            "reason": reason,
        }, timeout=10)
        logger.info(f"Reversal result: {rev_res.json()}")
    except Exception as e:
        logger.error(f"Reversal failed: {e} — MANUAL INTERVENTION REQUIRED")


# ── Failure Injection (Dashboard Control) ───────────────────────────────

@app.route("/inject-failure", methods=["POST"])
def inject_failure():
    """Toggle credit failure injection for demo."""
    global INJECT_CREDIT_FAILURE
    data = request.get_json()
    INJECT_CREDIT_FAILURE = data.get("enabled", not INJECT_CREDIT_FAILURE)
    logger.info(f"Failure injection: {'ENABLED' if INJECT_CREDIT_FAILURE else 'DISABLED'}")
    return jsonify({"failure_injection": INJECT_CREDIT_FAILURE}), 200


@app.route("/inject-failure", methods=["GET"])
def get_failure_status():
    """Get current failure injection status."""
    return jsonify({"failure_injection": INJECT_CREDIT_FAILURE}), 200


# ── Dashboard & Status ──────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serve the dashboard web page."""
    return render_template("index.html")


@app.route("/transactions", methods=["GET"])
def get_transactions():
    """Get switch-level transaction history."""
    return jsonify(switch_transactions), 200


@app.route("/banks", methods=["GET"])
def get_banks():
    """Get registered banks and their status."""
    banks = []
    for bank_key, url in BANK_REGISTRY.items():
        try:
            res = requests.get(f"{url}/accounts", timeout=3)
            banks.append({
                "bank": bank_key,
                "url": url,
                "status": "online" if res.status_code == 200 else "degraded",
                "accounts": res.json() if res.status_code == 200 else [],
            })
        except Exception:
            banks.append({
                "bank": bank_key,
                "url": url,
                "status": "offline",
                "accounts": [],
            })
    return jsonify(banks), 200


@app.route("/reconcile", methods=["GET"])
def reconcile():
    """Run reconciliation across all banks."""
    results = {}
    for bank_key, url in BANK_REGISTRY.items():
        try:
            res = requests.get(f"{url}/ledger/balance-check", timeout=5)
            results[bank_key] = res.json()
        except Exception as e:
            results[bank_key] = {"status": "unreachable", "error": str(e)}
    return jsonify(results), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "healthy", "service": "PayRail Switch"}), 200


# ── Main ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("SWITCH_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
