"""
PayRail — Bank service REST routes.
Each bank instance exposes these endpoints for the payment switch to call.
"""

from flask import Blueprint, request, jsonify
from bank_service.models import db, Account, Transaction, LedgerEntry
import uuid

bank_bp = Blueprint("bank", __name__)


# ── Account Management ──────────────────────────────────────────────────

@bank_bp.route("/accounts", methods=["POST"])
def create_account():
    """Create a new bank account with a UPI ID."""
    data = request.get_json()
    if not data or "upi_id" not in data or "name" not in data:
        return jsonify({"error": "Missing upi_id or name"}), 400

    if Account.query.filter_by(upi_id=data["upi_id"]).first():
        return jsonify({"error": "UPI ID already exists"}), 409

    account = Account(
        upi_id=data["upi_id"],
        name=data["name"],
        balance=data.get("balance", 10000.0),  # Default opening balance
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(account.to_dict()), 201


@bank_bp.route("/accounts", methods=["GET"])
def list_accounts():
    """List all accounts in this bank."""
    accounts = Account.query.all()
    return jsonify([a.to_dict() for a in accounts]), 200


@bank_bp.route("/accounts/<upi_id>", methods=["GET"])
def get_account(upi_id):
    """Get account details by UPI ID."""
    account = Account.query.filter_by(upi_id=upi_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(account.to_dict()), 200


# ── Debit (called by payment switch) ────────────────────────────────────

@bank_bp.route("/debit", methods=["POST"])
def debit():
    """
    Debit an account. Called by the payment switch.
    Supports idempotency — same key returns same result.
    """
    data = request.get_json()
    required = ["upi_id", "amount", "idempotency_key", "transaction_id"]
    if not data or not all(k in data for k in required):
        return jsonify({"error": f"Missing fields: {required}"}), 400

    # Idempotency check
    existing = Transaction.query.filter_by(idempotency_key=data["idempotency_key"]).first()
    if existing:
        return jsonify({
            "status": existing.status,
            "transaction_id": existing.id,
            "message": "Duplicate request — returning original result"
        }), 200

    account = Account.query.filter_by(upi_id=data["upi_id"]).first()
    if not account:
        txn = _create_failed_txn(data, "Account not found")
        return jsonify({"status": "failed", "reason": "Account not found"}), 404

    if not account.is_active:
        txn = _create_failed_txn(data, "Account is inactive")
        return jsonify({"status": "failed", "reason": "Account is inactive"}), 403

    amount = float(data["amount"])
    if account.balance < amount:
        txn = _create_failed_txn(data, "Insufficient balance")
        return jsonify({"status": "failed", "reason": "Insufficient balance"}), 400

    # Perform debit
    balance_before = account.balance
    account.balance -= amount

    txn = Transaction(
        id=data["transaction_id"],
        idempotency_key=data["idempotency_key"],
        sender_upi=data["upi_id"],
        receiver_upi=data.get("receiver_upi", ""),
        amount=amount,
        status="debited",
    )
    db.session.add(txn)

    # Ledger entry
    ledger = LedgerEntry(
        transaction_id=data["transaction_id"],
        account_id=account.id,
        entry_type="DEBIT",
        amount=amount,
        balance_before=balance_before,
        balance_after=account.balance,
        description=f"Payment to {data.get('receiver_upi', 'unknown')}",
    )
    db.session.add(ledger)
    db.session.commit()

    return jsonify({"status": "debited", "transaction_id": txn.id, "balance": account.balance}), 200


# ── Credit (called by payment switch) ───────────────────────────────────

@bank_bp.route("/credit", methods=["POST"])
def credit():
    """
    Credit an account. Called by the payment switch.
    Supports failure injection for demo purposes.
    """
    data = request.get_json()
    required = ["upi_id", "amount", "transaction_id"]
    if not data or not all(k in data for k in required):
        return jsonify({"error": f"Missing fields: {required}"}), 400

    # Check for simulated failure
    if data.get("simulate_failure"):
        return jsonify({"status": "failed", "reason": "Simulated credit failure for demo"}), 500

    account = Account.query.filter_by(upi_id=data["upi_id"]).first()
    if not account:
        return jsonify({"status": "failed", "reason": "Receiver account not found"}), 404

    if not account.is_active:
        return jsonify({"status": "failed", "reason": "Receiver account is inactive"}), 403

    amount = float(data["amount"])
    balance_before = account.balance
    account.balance += amount

    # Ledger entry
    ledger = LedgerEntry(
        transaction_id=data["transaction_id"],
        account_id=account.id,
        entry_type="CREDIT",
        amount=amount,
        balance_before=balance_before,
        balance_after=account.balance,
        description=f"Payment from {data.get('sender_upi', 'unknown')}",
    )
    db.session.add(ledger)
    db.session.commit()

    return jsonify({"status": "credited", "balance": account.balance}), 200


# ── Reversal (called by payment switch on credit failure) ───────────────

@bank_bp.route("/reverse", methods=["POST"])
def reverse():
    """
    Reverse a debit. Called when credit fails.
    """
    data = request.get_json()
    if not data or "transaction_id" not in data:
        return jsonify({"error": "Missing transaction_id"}), 400

    txn = Transaction.query.filter_by(id=data["transaction_id"]).first()
    if not txn:
        return jsonify({"error": "Transaction not found"}), 404

    if txn.status == "reversed":
        return jsonify({"status": "already_reversed"}), 200

    account = Account.query.filter_by(upi_id=txn.sender_upi).first()
    if not account:
        return jsonify({"error": "Sender account not found for reversal"}), 404

    # Reverse the debit
    balance_before = account.balance
    account.balance += txn.amount
    txn.status = "reversed"
    txn.failure_reason = data.get("reason", "Credit failed — auto-reversed")

    # Reversal ledger entry
    ledger = LedgerEntry(
        transaction_id=txn.id,
        account_id=account.id,
        entry_type="CREDIT",
        amount=txn.amount,
        balance_before=balance_before,
        balance_after=account.balance,
        description=f"REVERSAL: {txn.failure_reason}",
    )
    db.session.add(ledger)

    # Create reversal transaction record
    reversal_txn = Transaction(
        idempotency_key=f"rev-{txn.idempotency_key}",
        sender_upi=txn.receiver_upi,
        receiver_upi=txn.sender_upi,
        amount=txn.amount,
        status="completed",
        is_reversal=True,
        original_txn_id=txn.id,
    )
    db.session.add(reversal_txn)
    db.session.commit()

    return jsonify({"status": "reversed", "balance": account.balance}), 200


# ── Transactions & Ledger ───────────────────────────────────────────────

@bank_bp.route("/transactions", methods=["GET"])
def list_transactions():
    """List all transactions for this bank."""
    txns = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return jsonify([t.to_dict() for t in txns]), 200


@bank_bp.route("/ledger", methods=["GET"])
def list_ledger():
    """Get the full ledger for this bank."""
    entries = LedgerEntry.query.order_by(LedgerEntry.created_at.desc()).all()
    return jsonify([e.to_dict() for e in entries]), 200


@bank_bp.route("/ledger/balance-check", methods=["GET"])
def balance_check():
    """
    Reconciliation: verify account balances match ledger entries.
    Returns mismatches if any.
    """
    accounts = Account.query.all()
    mismatches = []

    for acc in accounts:
        entries = LedgerEntry.query.filter_by(account_id=acc.id).all()
        ledger_balance = 10000.0  # Opening balance

        for entry in sorted(entries, key=lambda e: e.created_at):
            if entry.entry_type == "CREDIT":
                ledger_balance += entry.amount
            elif entry.entry_type == "DEBIT":
                ledger_balance -= entry.amount

        if abs(ledger_balance - acc.balance) > 0.01:
            mismatches.append({
                "account": acc.upi_id,
                "db_balance": acc.balance,
                "ledger_balance": round(ledger_balance, 2),
                "difference": round(acc.balance - ledger_balance, 2),
            })

    return jsonify({
        "status": "ok" if not mismatches else "mismatches_found",
        "checked": len(accounts),
        "mismatches": mismatches,
    }), 200


# ── Helpers ──────────────────────────────────────────────────────────────

def _create_failed_txn(data, reason):
    """Create a failed transaction record."""
    txn = Transaction(
        id=data.get("transaction_id", str(uuid.uuid4())),
        idempotency_key=data["idempotency_key"],
        sender_upi=data["upi_id"],
        receiver_upi=data.get("receiver_upi", ""),
        amount=float(data["amount"]),
        status="failed",
        failure_reason=reason,
    )
    db.session.add(txn)
    db.session.commit()
    return txn
