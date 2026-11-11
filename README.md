# ACID Financial Ledger & Transaction Engine (PostgreSQL + Python)

A high-concurrency, double-entry financial ledger and transaction processing engine engineered with PostgreSQL 18 and Python (Psycopg 3). Designed to enforce strict ACID compliance, guarantee zero balance drift under high load, and provide immutable audit records for fintech applications.

---

## 🏛️ Core Architectural Principles

* **Double-Entry Bookkeeping**: Every transaction requires balanced credit and debit entries netting to zero. Account types (`ASSET`, `LIABILITY`, `EQUITY`, `REVENUE`, `EXPENSE`) follow standard financial accounting invariants.
* **Pessimistic Concurrency Control**: Uses explicit `SELECT ... FOR UPDATE` row locks to serialize high-volume concurrent access to the same account balances.
* **Deterministic Deadlock Prevention**: Account row locks are acquired in sorted lexical order by UUID, preventing circular wait conditions across concurrent worker threads.
* **Idempotency Protection**: Transactions are bound to unique client idempotency keys, guaranteeing that network retries never produce duplicate debits or double spends.
* **Defensive Immutability (Append-Only)**: A PostgreSQL PL/pgSQL trigger intercepts and blocks direct `UPDATE` or `DELETE` mutations on `ledger_entries`, guaranteeing an immutable ledger audit trail.

---

## 📊 Concurrency Stress Test Results

Simulated high-frequency concurrent traffic via a `ThreadPoolExecutor` (50 simultaneous threads attempting to transfer 50.00 GHS from a 2,000.00 GHS pool):

```text
============================================================
  AUDIT & CONSISTENCY VERIFICATION REPORT
============================================================
Successful Transfers  : 40 (Expected: 40)
Blocked Overdrafts    : 10 (Expected: 10)
Final Sender Balance  : 0.00 GHS (Expected: 0.00 GHS)
Final Receiver Balance: 2000.00 GHS (Expected: 2,000.00 GHS)
System Balance Drift  : 0.0000 GHS

[✓] VERIFIED: Perfect ACID isolation, zero race conditions, zero deadlocks.