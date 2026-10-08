"""
PayRail — Individual bank service application factory.
Each bank runs as a separate Flask instance with its own database.
"""

import os
from flask import Flask
from flask_cors import CORS
from bank_service.models import db, Account
from bank_service.routes import bank_bp


def create_bank_app(bank_name: str, port: int = 5001):
    """
    Create a Flask app for a specific bank.

    Args:
        bank_name: Identifier for this bank (e.g., 'bankA', 'bankB')
        port: Port to run on
    """
    app = Flask(__name__)
    CORS(app)

    # Each bank gets its own SQLite database
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", f"{bank_name}.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath(db_path)}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["BANK_NAME"] = bank_name
    app.config["BANK_PORT"] = port

    db.init_app(app)
    app.register_blueprint(bank_bp)

    with app.app_context():
        db.create_all()
        _seed_accounts(bank_name)

    return app


def _seed_accounts(bank_name: str):
    """Seed default accounts if the database is empty."""
    if Account.query.count() > 0:
        return

    if bank_name == "bankA":
        accounts = [
            {"upi_id": "asha@bankA", "name": "Asha Patel", "balance": 50000.0},
            {"upi_id": "ravi@bankA", "name": "Ravi Kumar", "balance": 25000.0},
            {"upi_id": "priya@bankA", "name": "Priya Singh", "balance": 75000.0},
        ]
    elif bank_name == "bankB":
        accounts = [
            {"upi_id": "neha@bankB", "name": "Neha Sharma", "balance": 40000.0},
            {"upi_id": "amit@bankB", "name": "Amit Verma", "balance": 60000.0},
            {"upi_id": "sita@bankB", "name": "Sita Devi", "balance": 30000.0},
        ]
    else:
        accounts = [
            {"upi_id": f"user1@{bank_name}", "name": "User One", "balance": 10000.0},
            {"upi_id": f"user2@{bank_name}", "name": "User Two", "balance": 20000.0},
        ]

    for acc_data in accounts:
        acc = Account(**acc_data)
        db.session.add(acc)

    db.session.commit()
