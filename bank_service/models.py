"""
PayRail — Database models for individual bank services.
Each bank runs its own instance with its own SQLite database.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import uuid

db = SQLAlchemy()


class Account(db.Model):
    """Bank account with balance tracking."""
    __tablename__ = "accounts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upi_id = db.Column(db.String(100), unique=True, nullable=False, index=True)  # e.g. asha@bankA
    name = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), default="INR")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    ledger_entries = db.relationship("LedgerEntry", backref="account", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "upi_id": self.upi_id,
            "name": self.name,
            "balance": self.balance,
            "currency": self.currency,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class Transaction(db.Model):
    """Payment transaction record."""
    __tablename__ = "transactions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    sender_upi = db.Column(db.String(100), nullable=False)
    receiver_upi = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default="INR")
    status = db.Column(db.String(20), nullable=False, default="pending")
    # Status flow: pending → debited → completed | failed → reversed
    failure_reason = db.Column(db.String(500))
    is_reversal = db.Column(db.Boolean, default=False)
    original_txn_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "idempotency_key": self.idempotency_key,
            "sender_upi": self.sender_upi,
            "receiver_upi": self.receiver_upi,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "is_reversal": self.is_reversal,
            "original_txn_id": self.original_txn_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class LedgerEntry(db.Model):
    """
    Double-entry ledger. Every balance change creates TWO entries:
    - DEBIT on sender account
    - CREDIT on receiver account
    """
    __tablename__ = "ledger"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = db.Column(db.String(36), nullable=False, index=True)
    account_id = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=False)
    entry_type = db.Column(db.String(10), nullable=False)  # DEBIT or CREDIT
    amount = db.Column(db.Float, nullable=False)
    balance_before = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "account_id": self.account_id,
            "entry_type": self.entry_type,
            "amount": self.amount,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }
