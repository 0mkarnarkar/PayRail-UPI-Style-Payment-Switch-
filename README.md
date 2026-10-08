# PayRail 🚄

> Mini UPI-style payment system across independent banks, with automatic failure handling, idempotency, double-entry ledger, and real-time dashboard.

## Architecture

```
┌────────────┐      ┌──────────────────┐      ┌────────────┐
│            │      │                  │      │            │
│  Bank A    │◄────►│  Payment Switch  │◄────►│  Bank B    │
│  :5001     │      │  :5000           │      │  :5002     │
│            │      │                  │      │            │
│ asha@bankA │      │  POST /pay       │      │ neha@bankB │
│ ravi@bankA │      │  • Route by UPI  │      │ amit@bankB │
│ priya@bankA│      │  • Debit → Credit│      │ sita@bankB │
│            │      │  • Auto-reverse  │      │            │
│ SQLite DB  │      │  • Dashboard     │      │ SQLite DB  │
└────────────┘      └──────────────────┘      └────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Bank** | Two independent banks, each with own database and API |
| **UPI-Style Routing** | `asha@bankA` → `neha@bankB` cross-bank payments |
| **Automatic Reversals** | If credit fails, debit is reversed automatically |
| **Idempotency Keys** | Prevents double-debits on retry |
| **Double-Entry Ledger** | Every transaction creates matching DEBIT/CREDIT entries |
| **Reconciliation** | Balance-check job verifies DB matches ledger |
| **Failure Injection** | Dashboard toggle to simulate credit failures |
| **Real-Time Dashboard** | Monitor payments, banks, and run reconciliation |

## Quick Start

### Run Everything

```bash
# Install dependencies
pip install -r requirements.txt

# Start all services (Bank A, Bank B, Payment Switch)
python run.py
```

This starts:
- **Bank A** on `http://127.0.0.1:5001`
- **Bank B** on `http://127.0.0.1:5002`
- **Dashboard** on `http://127.0.0.1:5000`

### Docker

```bash
docker-compose up --build
```

### API Usage

```bash
# Send a payment
curl -X POST http://localhost:5000/pay \
  -H "Content-Type: application/json" \
  -d '{"sender": "asha@bankA", "receiver": "neha@bankB", "amount": 1000}'

# With idempotency key (safe retries)
curl -X POST http://localhost:5000/pay \
  -H "Content-Type: application/json" \
  -d '{"sender": "asha@bankA", "receiver": "amit@bankB", "amount": 500, "idempotency_key": "pay-001"}'

# Enable failure injection (demo reversals)
curl -X POST http://localhost:5000/inject-failure \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Send payment (will be auto-reversed)
curl -X POST http://localhost:5000/pay \
  -H "Content-Type: application/json" \
  -d '{"sender": "ravi@bankA", "receiver": "sita@bankB", "amount": 2000}'

# Run reconciliation
curl http://localhost:5000/reconcile

# Check bank accounts
curl http://localhost:5001/accounts
curl http://localhost:5002/accounts

# View ledger
curl http://localhost:5001/ledger
```

## Payment Flow

```
1. User sends POST /pay { sender: "asha@bankA", receiver: "neha@bankB", amount: 1000 }

2. Switch parses UPI IDs → routes to correct bank services

3. Switch calls Bank A: POST /debit
   ├─ Success → proceed to step 4
   └─ Failure → return error (no money moved)

4. Switch calls Bank B: POST /credit
   ├─ Success → payment complete ✅
   └─ Failure → Switch calls Bank A: POST /reverse 🔄
                 (money returned to sender)
```

## Running Tests

```bash
pytest tests/ -v
```

## Pre-seeded Accounts

| Bank A | Bank B |
|--------|--------|
| asha@bankA (₹50,000) | neha@bankB (₹40,000) |
| ravi@bankA (₹25,000) | amit@bankB (₹60,000) |
| priya@bankA (₹75,000) | sita@bankB (₹30,000) |

## Project Structure

```
PayRail/
├── run.py                          # Starts all services
├── bank_service/
│   ├── app.py                      # Bank app factory
│   ├── models.py                   # Account, Transaction, Ledger models
│   └── routes.py                   # Debit, Credit, Reverse, Ledger APIs
├── payment_switch/
│   └── app.py                      # Central routing + failure injection
├── dashboard/
│   ├── templates/index.html        # Dashboard UI
│   └── static/
│       ├── style.css               # Dark theme
│       └── script.js               # Frontend logic
├── tests/
│   └── test_payments.py            # Comprehensive tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .github/workflows/ci.yml
```

## License

MIT
