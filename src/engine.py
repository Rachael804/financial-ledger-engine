from decimal import Decimal
import psycopg
from src.db import get_connection

class InsufficientFundsError(Exception):
    pass

class DuplicateTransactionError(Exception):
    pass

class LedgerEngine:
    def create_account(self, account_number: str, account_name: str, account_type: str, currency: str = "GHS") -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO accounts (account_number, account_name, account_type, currency)
                    VALUES (%s, %s, %s, %s)
                    RETURNING account_id;
                    """,
                    (account_number, account_name, account_type, currency)
                )
                acc_id = cur.fetchone()[0]
                conn.commit()
                return str(acc_id)

    def get_account_balance(self, account_id: str) -> Decimal:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT account_type FROM accounts WHERE account_id = %s;", (account_id,))
                res = cur.fetchone()
                if not res:
                    raise ValueError("Account does not exist.")
                acc_type = res[0]

                cur.execute(
                    """
                    SELECT 
                        COALESCE(SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END), 0) AS total_debit,
                        COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0) AS total_credit
                    FROM ledger_entries
                    WHERE account_id = %s;
                    """,
                    (account_id,)
                )
                debit, credit = cur.fetchone()

                if acc_type in ('ASSET', 'EXPENSE'):
                    return Decimal(debit) - Decimal(credit)
                else:
                    return Decimal(credit) - Decimal(debit)

    def transfer(self, idempotency_key: str, from_account_id: str, to_account_id: str, amount: Decimal, description: str):
        if amount <= Decimal("0.00"):
            raise ValueError("Transfer amount must be strictly greater than zero.")

        # Deadlock prevention: Lock accounts in deterministic lexical order
        sorted_account_ids = sorted([from_account_id, to_account_id])

        with get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    # 1. Idempotency check
                    cur.execute(
                        "SELECT status FROM transactions WHERE idempotency_key = %s;", 
                        (idempotency_key,)
                    )
                    existing = cur.fetchone()
                    if existing:
                        raise DuplicateTransactionError(f"Transaction with key '{idempotency_key}' already processed.")

                    # 2. Acquire row locks
                    cur.execute(
                        """
                        SELECT account_id FROM accounts 
                        WHERE account_id = ANY(%s)
                        FOR UPDATE;
                        """,
                        (sorted_account_ids,)
                    )
                    locked = cur.fetchall()
                    if len(locked) < 2:
                        raise ValueError("One or both accounts do not exist.")

                    # 3. Balance verification
                    cur.execute(
                        """
                        SELECT 
                            COALESCE(SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END), 0) -
                            COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0)
                        FROM ledger_entries
                        WHERE account_id = %s;
                        """,
                        (from_account_id,)
                    )
                    current_balance = Decimal(cur.fetchone()[0])
                    if current_balance < amount:
                        raise InsufficientFundsError(
                            f"Insufficient funds: available {current_balance}, requested {amount}."
                        )

                    # 4. Insert transaction envelope
                    cur.execute(
                        """
                        INSERT INTO transactions (idempotency_key, description, status)
                        VALUES (%s, %s, 'COMMITTED')
                        RETURNING transaction_id;
                        """,
                        (idempotency_key, description)
                    )
                    tx_id = cur.fetchone()[0]

                    # 5. Insert double-entry rows
                    cur.execute(
                        """
                        INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount)
                        VALUES (%s, %s, 'CREDIT', %s);
                        """,
                        (tx_id, from_account_id, amount)
                    )
                    cur.execute(
                        """
                        INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount)
                        VALUES (%s, %s, 'DEBIT', %s);
                        """,
                        (tx_id, to_account_id, amount)
                    )

                conn.commit()
                return tx_id

            except Exception:
                conn.rollback()
                raise