import uuid
import random
import time
import requests
from datetime import datetime
from database import SessionLocal, Transaction, Order, AgentLog
from pine_labs_auth import get_headers, PINE_LABS_BASE_URL, is_pine_labs_available

def pl_ref():
    return "PL" + uuid.uuid4().hex[:10].upper()

def route_payment(amount: float, persona_id: int, order_id: int = None,
                  bin_number: str = None, issuer_bank: str = None,
                  triggered_by: str = "agent"):

    db   = SessionLocal()
    hour = datetime.utcnow().hour + 5

    if issuer_bank == "Axis Bank" and 14 <= hour <= 16:
        method = "UPI";    reason = "Axis Bank cards unstable 2-4 PM IST → UPI selected"
    elif issuer_bank == "HDFC" and hour < 9:
        method = "Card";   reason = "HDFC card auth fastest in morning → Card selected"
    elif bin_number and bin_number.startswith("5234"):
        method = "EMI";    reason = "Mastercard premium BIN → EMI offer applied"
    elif bin_number and bin_number.startswith("4111"):
        method = "Card";   reason = "Visa BIN detected → Card selected"
    elif amount < 100:
        method = "UPI";    reason = "Amount < ₹100 → UPI optimal"
    elif amount <= 500:
        method = "Card";   reason = "Amount ₹100-500 → Card selected"
    elif amount <= 10000:
        method = "EMI";    reason = "High value → EMI to reduce burden"
    else:
        method = "Mandate"; reason = "Recurring high value → Mandate"

    pine_ref = pl_ref(); pine_order_id = None; checkout_url = None; pine_labs_live = False

    try:
        from pine_labs_api import create_order
        result = create_order(amount=amount, customer_name=f"Persona {persona_id}",
                              mobile="9999999999", merchant_ref=f"BA{int(uuid.uuid4().int % 10**8)}")
        if result and result.get("success"):
            pine_order_id = result.get("order_id"); checkout_url = result.get("checkout_url")
            pine_ref = f"PL{pine_order_id}" if pine_order_id else pine_ref
            pine_labs_live = True
            print(f"✅ Real Pine Labs order: {pine_order_id}")
    except Exception as e:
        print(f"⚠️ Pine Labs order error: {e}")

    status = "success" if random.random() < 0.85 else "failed"
    txn = Transaction(persona_id=persona_id, order_id=order_id, amount_inr=amount,
                      payment_method=method, payment_rail=f"pine_labs_{method.lower()}",
                      status=status, retry_count=0,
                      bin_number=bin_number or random.choice(["411111","523456","401200"]),
                      issuer_bank=issuer_bank or random.choice(["HDFC","ICICI","Axis Bank","SBI"]),
                      pine_labs_ref_id=pine_ref, payment_link=checkout_url,
                      triggered_by=triggered_by, created_at=datetime.utcnow())
    db.add(txn)
    live_tag = "🟢 LIVE Pine Labs" if pine_labs_live else "🔵 SIM"
    db.add(AgentLog(persona_id=persona_id, event_type="payment",
                    message=f"{'✅' if status=='success' else '❌'} [{live_tag}] ₹{amount:.2f} via {method} | Ref: {pine_ref} | {reason}",
                    amount_inr=amount, status=status))
    db.commit(); db.refresh(txn); db.close()
    return {"transaction_id": txn.id, "pine_labs_ref": pine_ref, "pine_order_id": pine_order_id,
            "checkout_url": checkout_url, "method": method, "status": status,
            "amount": amount, "reason": reason, "live_pine_labs": pine_labs_live}


def smart_retry(transaction_id: int):
    db = SessionLocal()
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn: db.close(); return {"error": "Transaction not found"}
    if txn.status == "success": db.close(); return {"error": "Already successful"}

    txn.retry_count += 1; retry_num = txn.retry_count; original = txn.payment_method
    txn_amount  = txn.amount_inr
    txn_persona = txn.persona_id
    if retry_num == 1:   new_method = "UPI" if original in ["Card","EMI","NetBanking"] else "Card"; wait = 2
    elif retry_num == 2: new_method = "NetBanking"; wait = 3
    else:
        txn.status = "failed_final"
        db.add(AgentLog(persona_id=txn_persona, event_type="retry",
                        message=f"❌ All retries exhausted for ₹{txn_amount:.2f}", amount_inr=txn_amount, status="failed_final"))
        db.commit(); db.close()
        return {"status": "failed_final"}

    time.sleep(wait)
    new_pine_ref = pl_ref(); pine_labs_live = False; pine_order_id = None

    try:
        from pine_labs_api import create_order
        result = create_order(amount=txn.amount_inr, customer_name="Retry Customer",
                              mobile="9999999999", merchant_ref=f"RT{int(uuid.uuid4().int % 10**8)}")
        if result and result.get("success"):
            pine_order_id = result.get("order_id")
            new_pine_ref = f"PL{pine_order_id}" if pine_order_id else new_pine_ref
            pine_labs_live = True
    except Exception as e:
        print(f"⚠️ Pine Labs retry error: {e}")

    new_status = "recovered" if random.random() < 0.80 else "failed"
    txn.payment_method = new_method; txn.payment_rail = f"pine_labs_{new_method.lower()}"
    txn.status = new_status; txn.pine_labs_ref_id = new_pine_ref

    # Store values before commit/close
    txn_amount   = txn.amount_inr
    txn_persona  = txn.persona_id

    live_tag = "🟢 LIVE" if pine_labs_live else "🔵 SIM"
    db.add(AgentLog(persona_id=txn_persona, event_type="retry",
                    message=f"{'✅' if new_status=='recovered' else '❌'} [{live_tag}] Retry {retry_num}: {original} → {new_method} | ₹{txn_amount:.2f} | {new_status.upper()} | Ref: {new_pine_ref}",
                    amount_inr=txn_amount, status=new_status))
    db.commit(); db.close()
    return {"transaction_id": transaction_id, "retry_count": retry_num, "original_method": original,
            "new_method": new_method, "status": new_status, "pine_labs_ref": new_pine_ref,
            "amount": txn_amount, "live_pine_labs": pine_labs_live}


def create_payment_link(amount: float, customer_name: str, persona_id: int):
    pine_ref = pl_ref(); link = f"https://pay.pinelabs.com/link/{pine_ref}"; pine_labs_live = False

    try:
        from pine_labs_api import create_order
        result = create_order(amount=amount, customer_name=customer_name,
                              mobile="9999999999", merchant_ref=f"LK{int(uuid.uuid4().int % 10**8)}")
        if result and result.get("success"):
            order_id = result.get("order_id"); checkout_url = result.get("checkout_url")
            if checkout_url: link = checkout_url
            pine_ref = f"PL{order_id}" if order_id else pine_ref
            pine_labs_live = True
            print(f"✅ Real Pine Labs payment link: {link}")
    except Exception as e:
        print(f"⚠️ Pine Labs payment link error: {e}")

    db = SessionLocal()
    txn = Transaction(persona_id=persona_id, amount_inr=amount, payment_method="UPI",
                      payment_rail="pine_labs_payment_link", status="pending",
                      pine_labs_ref_id=pine_ref, payment_link=link, triggered_by="agent")
    db.add(txn)
    live_tag = "🟢 LIVE Pine Labs" if pine_labs_live else "🔵 SIM"
    db.add(AgentLog(persona_id=persona_id, event_type="payment",
                    message=f"💳 [{live_tag}] Payment link for {customer_name}: ₹{amount:.2f} | {link}",
                    amount_inr=amount, status="pending"))
    db.commit(); db.refresh(txn); db.close()
    return {"link": link, "pine_labs_ref": pine_ref, "amount": amount,
            "transaction_id": txn.id, "live": pine_labs_live}


def process_refund(transaction_id: int):
    db = SessionLocal()
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn: db.close(); return {"error": "Transaction not found"}

    refund_ref = pl_ref(); pine_labs_live = False
    pine_order_id = txn.pine_labs_ref_id.replace("PL","") if txn.pine_labs_ref_id else None

    if pine_order_id:
        try:
            from pine_labs_api import create_refund
            result = create_refund(order_id=pine_order_id, amount=txn.amount_inr,
                                   reason="Customer refund via BharatAgent")
            if result and result.get("success"):
                refund_ref = result.get("refund_id") or refund_ref
                pine_labs_live = True
                print(f"✅ Real Pine Labs refund: {refund_ref}")
        except Exception as e:
            print(f"⚠️ Pine Labs refund error: {e}")

    refund_txn = Transaction(persona_id=txn.persona_id, order_id=txn.order_id,
                             amount_inr=-txn.amount_inr, payment_method=txn.payment_method,
                             payment_rail="pine_labs_refund", status="refunded",
                             pine_labs_ref_id=str(refund_ref), triggered_by="agent")
    txn.status = "refunded"; db.add(refund_txn)
    live_tag = "🟢 LIVE Pine Labs" if pine_labs_live else "🔵 SIM"
    db.add(AgentLog(persona_id=txn.persona_id, event_type="refund",
                    message=f"🔄 [{live_tag}] Refund ₹{txn.amount_inr:.2f} | Ref: {refund_ref} | 2-4 hours",
                    amount_inr=txn.amount_inr, status="refunded"))
    db.commit(); db.close()
    return {"refund_ref": str(refund_ref), "amount": txn.amount_inr,
            "status": "refunded", "timeline": "2-4 hours", "live_pine_labs": pine_labs_live}


def simulate_price_spike(product_id: int):
    from database import Product
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: db.close(); return {"error": "Product not found"}

    product_name = product.name; supplier_price = product.supplier_price; persona_id = product.persona_id
    spiked_price = round(supplier_price * random.uniform(1.5, 2.0), 2)
    is_spike = spiked_price > supplier_price * 1.2
    savings = round(spiked_price - supplier_price, 2)

    if is_spike:
        db.add(AgentLog(persona_id=persona_id, event_type="spike",
                        message=f"⚠️ Price spike on {product_name}! Normal: ₹{supplier_price} | Spiked: ₹{spiked_price} | BLOCKED! Saved ₹{savings}",
                        amount_inr=savings, status="blocked_spike"))
        db.commit()
    db.close()
    return {"product": product_name, "normal_price": supplier_price,
            "spiked_price": spiked_price, "is_spike": is_spike, "savings": savings}