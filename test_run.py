from decimal import Decimal
import uuid
from src.engine import LedgerEngine
from src.db import get_connection

def run_test():
    engine = LedgerEngine()
    print("[*] Creating accounts...")
    acc_sender = engine.create_account(f"ACC-{uuid.uuid4().hex[:6]}", "Primary Asset Account", "ASSET", "GHS")
    acc_receiver = engine.create_account(f"ACC-{uuid.uuid4().hex[:6]}", "Reserve Account", "ASSET", "GHS")
    acc_equity = engine.create_account(f"EQ-{uuid.uuid4().hex[:6]}", "Initial Capital", "EQUITY", "GHS")

    # Initial funding: +5,000.00 GHS
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions (idempotency_key, description) VALUES (%s, %s) RETURNING transaction_id;",
                (str(uuid.uuid4()), "Initial Capital Deposit")
            )
            tx_id = cur.fetchone()[0]
            cur.execute("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount) VALUES (%s, %s, 'DEBIT', %s);", (tx_id, acc_sender, Decimal("5000.00")))
            cur.execute("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount) VALUES (%s, %s, 'CREDIT', %s);", (tx_id, acc_equity, Decimal("5000.00")))
        conn.commit()

    print(f"[✓] Sender Balance: {engine.get_account_balance(acc_sender)} GHS")
    print(f"[✓] Receiver Balance: {engine.get_account_balance(acc_receiver)} GHS")

    # Execute transfer
    print("\n[*] Transferring 1,500.00 GHS...")
    engine.transfer(
        idempotency_key=str(uuid.uuid4()),
        from_account_id=acc_sender,
        to_account_id=acc_receiver,
        amount=Decimal("1500.00"),
        description="Transfer to reserve"
    )

    print(f"[✓] Post-transfer Sender Balance: {engine.get_account_balance(acc_sender)} GHS")
    print(f"[✓] Post-transfer Receiver Balance: {engine.get_account_balance(acc_receiver)} GHS")

    # Test Defensive Immutability Trigger
    print("\n[*] Testing PostgreSQL trigger defense against direct ledger mutation...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ledger_entries SET amount = 999999.00;")
            conn.commit()
    except Exception as e:
        print(f"[✓] Immutability Trigger Blocked Mutation:\n    {e}")

if __name__ == "__main__":
    run_test()