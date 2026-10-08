"""Tests for PayRail payment system."""

import sys
import os
import json
import uuid
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bank_service.app import create_bank_app
from bank_service.models import db


@pytest.fixture
def bank_a():
    """Create a test Bank A client."""
    app = create_bank_app("testBankA_" + str(uuid.uuid4())[:8])
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestBankService:
    def test_list_accounts(self, bank_a):
        res = bank_a.get("/accounts")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) >= 2  # Seeded accounts

    def test_create_account(self, bank_a):
        res = bank_a.post("/accounts", json={
            "upi_id": "test@testbank",
            "name": "Test User",
            "balance": 5000
        })
        assert res.status_code == 201
        data = json.loads(res.data)
        assert data["upi_id"] == "test@testbank"
        assert data["balance"] == 5000

    def test_duplicate_upi_id(self, bank_a):
        bank_a.post("/accounts", json={"upi_id": "dup@bank", "name": "User"})
        res = bank_a.post("/accounts", json={"upi_id": "dup@bank", "name": "User2"})
        assert res.status_code == 409

    def test_debit_success(self, bank_a):
        # Create account first
        bank_a.post("/accounts", json={
            "upi_id": "debit_test@bank", "name": "Debit User", "balance": 10000
        })
        txn_id = str(uuid.uuid4())
        res = bank_a.post("/debit", json={
            "upi_id": "debit_test@bank",
            "amount": 2000,
            "idempotency_key": f"idem-{txn_id}",
            "transaction_id": txn_id,
            "receiver_upi": "other@bank",
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "debited"
        assert data["balance"] == 8000

    def test_debit_insufficient_balance(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "poor@bank", "name": "Poor User", "balance": 100
        })
        res = bank_a.post("/debit", json={
            "upi_id": "poor@bank",
            "amount": 5000,
            "idempotency_key": str(uuid.uuid4()),
            "transaction_id": str(uuid.uuid4()),
        })
        assert res.status_code == 400

    def test_idempotency(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "idem@bank", "name": "Idem User", "balance": 10000
        })
        idem_key = f"idem-{uuid.uuid4()}"
        txn_id = str(uuid.uuid4())
        payload = {
            "upi_id": "idem@bank",
            "amount": 500,
            "idempotency_key": idem_key,
            "transaction_id": txn_id,
        }

        # First request
        res1 = bank_a.post("/debit", json=payload)
        assert res1.status_code == 200

        # Duplicate request — should return same result, not double-debit
        res2 = bank_a.post("/debit", json=payload)
        assert res2.status_code == 200
        data2 = json.loads(res2.data)
        assert "Duplicate" in data2.get("message", "")

    def test_credit_success(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "credit_test@bank", "name": "Credit User", "balance": 5000
        })
        res = bank_a.post("/credit", json={
            "upi_id": "credit_test@bank",
            "amount": 3000,
            "transaction_id": str(uuid.uuid4()),
            "sender_upi": "other@bank",
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "credited"
        assert data["balance"] == 8000

    def test_reversal(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "rev@bank", "name": "Rev User", "balance": 10000
        })
        txn_id = str(uuid.uuid4())

        # Debit first
        bank_a.post("/debit", json={
            "upi_id": "rev@bank",
            "amount": 2000,
            "idempotency_key": f"rev-idem-{txn_id}",
            "transaction_id": txn_id,
        })

        # Reverse
        res = bank_a.post("/reverse", json={
            "transaction_id": txn_id,
            "reason": "Credit failed"
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "reversed"
        assert data["balance"] == 10000  # Restored

    def test_balance_check(self, bank_a):
        res = bank_a.get("/ledger/balance-check")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] in ["ok", "mismatches_found"]

    def test_ledger_entries(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "ledger@bank", "name": "Ledger User", "balance": 5000
        })
        txn_id = str(uuid.uuid4())
        bank_a.post("/debit", json={
            "upi_id": "ledger@bank",
            "amount": 1000,
            "idempotency_key": f"ledger-{txn_id}",
            "transaction_id": txn_id,
        })

        res = bank_a.get("/ledger")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) >= 1
        assert data[0]["entry_type"] == "DEBIT"

    def test_simulated_credit_failure(self, bank_a):
        bank_a.post("/accounts", json={
            "upi_id": "fail@bank", "name": "Fail User", "balance": 5000
        })
        res = bank_a.post("/credit", json={
            "upi_id": "fail@bank",
            "amount": 1000,
            "transaction_id": str(uuid.uuid4()),
            "simulate_failure": True,
        })
        assert res.status_code == 500
