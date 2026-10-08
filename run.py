"""
PayRail — Main runner script.
Starts Bank A, Bank B, and the Payment Switch in parallel.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))


def run_bank(bank_name, port):
    """Start a bank service in a thread."""
    from bank_service.app import create_bank_app
    app = create_bank_app(bank_name, port)
    print(f"[{bank_name.upper()}] Starting on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_switch():
    """Start the payment switch."""
    time.sleep(1)  # Wait for banks to start
    from payment_switch.app import app
    print("[SWITCH] Starting on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


def main():
    print("=" * 60)
    print("  PayRail — Mini UPI Payment System")
    print("=" * 60)
    print()
    print("  Bank A:          http://127.0.0.1:5001")
    print("  Bank B:          http://127.0.0.1:5002")
    print("  Payment Switch:  http://127.0.0.1:5000  (Dashboard)")
    print()
    print("=" * 60)
    print()

    # Start Bank A
    t1 = threading.Thread(target=run_bank, args=("bankA", 5001), daemon=True)
    t1.start()

    # Start Bank B
    t2 = threading.Thread(target=run_bank, args=("bankB", 5002), daemon=True)
    t2.start()

    # Start Payment Switch (main thread will block here)
    run_switch()


if __name__ == "__main__":
    main()
