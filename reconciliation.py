import random
from datetime import datetime, timedelta
from database import SessionLocal, Transaction, Order, ReconciliationRecord, AgentLog

def run_reconciliation(persona_id: int):
    db      = SessionLocal()
    today   = datetime.utcnow().date()
    results = {"matched": 0, "mismatched": 0, "disputes": [],
               "total_settled": 0, "total_expected": 0, "anomalies": []}

    txns = db.query(Transaction).filter(
        Transaction.persona_id == persona_id,
        Transaction.status.in_(["success", "recovered"]),
        Transaction.created_at >= datetime.utcnow() - timedelta(days=1)
    ).all()

    # ── Group by order_id ─────────────────────────────
    order_groups = {}
    for txn in txns:
        key = txn.order_id or f"standalone_{txn.id}"
        if key not in order_groups:
            order_groups[key] = []
        order_groups[key].append(txn)

    for key, group_txns in order_groups.items():
        settled = sum(t.amount_inr for t in group_txns)
        results["total_settled"] += settled

        if str(key).startswith("standalone"):
            results["matched"] += 1
            results["total_expected"] += settled
            continue

        order = db.query(Order).filter(Order.id == key).first()
        expected = order.total_amount if order else settled
        results["total_expected"] += expected

        diff = abs(settled - expected)
        if diff > 1:  # Allow ₹1 tolerance
            results["mismatched"] += 1
            dispute = {
                "order_id":  key,
                "expected":  expected,
                "settled":   settled,
                "diff":      diff,
                "pine_ref":  group_txns[0].pine_labs_ref_id
            }
            results["disputes"].append(dispute)
            db.add(AgentLog(
                persona_id  = persona_id,
                event_type  = "reconcile",
                message     = f"⚠️ Mismatch Order #{key}: Expected ₹{expected:.2f} | Settled ₹{settled:.2f} | Diff ₹{diff:.2f} | Dispute auto-raised",
                amount_inr  = diff,
                status      = "disputed"
            ))
        else:
            results["matched"] += 1

    # ── Anomaly Detection ─────────────────────────────
    all_txns = db.query(Transaction).filter(
        Transaction.persona_id == persona_id,
        Transaction.created_at >= datetime.utcnow() - timedelta(days=7)
    ).all()

    total     = len(all_txns)
    failed    = len([t for t in all_txns if t.status in ["failed", "failed_final"]])
    fail_rate = (failed / total * 100) if total > 0 else 0

    if fail_rate > 30:
        results["anomalies"].append({
            "severity": "high",
            "message":  f"🔴 High failure rate: {fail_rate:.1f}% in last 7 days ({failed}/{total} transactions)"
        })
    elif fail_rate > 15:
        results["anomalies"].append({
            "severity": "medium",
            "message":  f"🟡 Elevated failure rate: {fail_rate:.1f}% in last 7 days"
        })

    # ── Check for same card multiple failures ─────────
    bin_failures = {}
    for txn in all_txns:
        if txn.status in ["failed", "failed_final"] and txn.bin_number:
            bin_failures[txn.bin_number] = bin_failures.get(txn.bin_number, 0) + 1

    for bin_num, count in bin_failures.items():
        if count >= 3:
            results["anomalies"].append({
                "severity": "high",
                "message":  f"🔴 BIN {bin_num}: {count} failed attempts — possible fraud or card issue"
            })

    # ── Save reconciliation record ─────────────────────
    rec = ReconciliationRecord(
        persona_id         = persona_id,
        date               = str(today),
        total_orders       = results["matched"] + results["mismatched"],
        total_expected_inr = results["total_expected"],
        total_settled_inr  = results["total_settled"],
        mismatches_count   = results["mismatched"],
        dispute_raised     = results["mismatched"] > 0,
        anomalies          = str(results["anomalies"]),
        status             = "disputed" if results["mismatched"] > 0 else "matched"
    )
    db.add(rec)
    db.commit()
    db.close()

    return results