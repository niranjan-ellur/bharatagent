"""
REAL Pine Labs API Integration
All endpoints use actual Pine Labs UAT APIs
Base URL: https://pluraluat.v2.pinepg.in
"""
import uuid
import requests
from datetime import datetime
from pine_labs_auth import get_headers, PINE_LABS_BASE_URL

BASE = PINE_LABS_BASE_URL

def request_headers():
    h = get_headers()
    if not h:
        return None
    h["Request-ID"]        = str(uuid.uuid4())
    h["Request-Timestamp"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return h

# ─── CUSTOMERS ────────────────────────────────────────

def create_customer(name: str, mobile: str, email: str = None):
    """POST /api/v1/customer"""
    h = request_headers()
    if not h:
        return None
    try:
        parts = name.split()
        payload = {
            "first_name":    parts[0],
            "last_name":     parts[-1] if len(parts) > 1 else "User",
            "mobile_number": mobile.replace("+91", "").replace("-", "").strip(),
            "country_code":  "91",
            "email_id":      email or f"{parts[0].lower()}@bharatagent.com"
        }
        r = requests.post(f"{BASE}/api/v1/customer", json=payload, headers=h, timeout=10)
        print(f"[Pine Labs] Create Customer: {r.status_code} {r.text[:200]}")
        if r.status_code in [200, 201]:
            return r.json()
        return None
    except Exception as e:
        print(f"[Pine Labs] Create Customer error: {e}")
        return None

def get_customer(customer_id: str):
    """GET /api/v1/customer/{customer_id}"""
    h = request_headers()
    if not h:
        return None
    try:
        r = requests.get(f"{BASE}/api/v1/customer/{customer_id}", headers=h, timeout=10)
        print(f"[Pine Labs] Get Customer: {r.status_code}")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[Pine Labs] Get Customer error: {e}")
        return None

# ─── ORDERS ───────────────────────────────────────────

def create_order(amount: float, customer_name: str, mobile: str = "9999999999",
                 merchant_ref: str = None, payment_mode: str = "LINK"):
    """
    POST /api/pay/v1/orders
    Creates a real Pine Labs order and returns checkout URL
    """
    h = request_headers()
    if not h:
        return None

    if not merchant_ref:
        merchant_ref = str(int(uuid.uuid4().int % 10**9))

    try:
        parts = customer_name.split()
        payload = {
            "merchant_order_reference": merchant_ref,
            "order_amount": {
                "value":    int(amount * 100),  # convert to paise
                "currency": "INR"
            },
            "pre_auth": False,
            "purchase_details": {
                "customer": {
                    "first_name":    parts[0],
                    "last_name":     parts[-1] if len(parts) > 1 else "Customer",
                    "mobile_number": mobile.replace("+91","").replace("-","").strip(),
                    "country_code":  "91",
                    "email_id":      f"{parts[0].lower()}@bharatagent.com"
                },
                "merchant_metadata": {
                    "key1": "BharatAgent",
                    "key2": f"Order for {customer_name}"
                }
            }
        }

        r = requests.post(
            f"{BASE}/api/pay/v1/orders",
            json=payload, headers=h, timeout=10
        )
        print(f"[Pine Labs] Create Order: {r.status_code} {r.text[:300]}")

        if r.status_code in [200, 201]:
            data    = r.json()
            # Pine Labs wraps response in "data" key
            payload = data.get("data", data)
            order_id = payload.get("order_id")
            # Checkout URL can be in multiple places
            checkout_url = (
                payload.get("redirect_url") or
                payload.get("checkout_url") or
                payload.get("payment_links", {}).get("web") or
                payload.get("payment_links", {}).get("mobile") or
                f"https://checkout.pinelabs.com/pay/{order_id}"
            )
            print(f"[Pine Labs] Order ID: {order_id} | Checkout: {checkout_url}")
            return {
                "success":      True,
                "order_id":     order_id,
                "merchant_ref": merchant_ref,
                "checkout_url": checkout_url,
                "amount":       amount,
                "raw":          payload
            }
        else:
            print(f"[Pine Labs] Order failed: {r.text}")
            return {"success": False, "error": r.text, "status_code": r.status_code}

    except Exception as e:
        print(f"[Pine Labs] Create Order error: {e}")
        return {"success": False, "error": str(e)}

def get_order(order_id: str):
    """GET /api/pay/v1/orders/{order_id}"""
    h = request_headers()
    if not h:
        return None
    try:
        r = requests.get(f"{BASE}/api/pay/v1/orders/{order_id}", headers=h, timeout=10)
        print(f"[Pine Labs] Get Order {order_id}: {r.status_code}")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[Pine Labs] Get Order error: {e}")
        return None

def get_order_by_ref(merchant_ref: str):
    """GET /api/pay/v1/orders/reference/{merchant_order_reference}"""
    h = request_headers()
    if not h:
        return None
    try:
        r = requests.get(f"{BASE}/api/pay/v1/orders/reference/{merchant_ref}", headers=h, timeout=10)
        print(f"[Pine Labs] Get Order by Ref {merchant_ref}: {r.status_code}")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[Pine Labs] Get Order by Ref error: {e}")
        return None

def cancel_order(order_id: str):
    """PUT /api/pay/v1/orders/{order_id}/cancel"""
    h = request_headers()
    if not h:
        return None
    try:
        r = requests.put(f"{BASE}/api/pay/v1/orders/{order_id}/cancel", headers=h, timeout=10)
        print(f"[Pine Labs] Cancel Order {order_id}: {r.status_code}")
        return r.json() if r.status_code in [200, 201] else None
    except Exception as e:
        print(f"[Pine Labs] Cancel Order error: {e}")
        return None

# ─── UPI PAYMENT ──────────────────────────────────────

def create_upi_collect(order_id: str, upi_id: str = "success@razorpay"):
    """
    POST /api/pay/v1/orders/{order_id}/payments
    UPI Collect Payment
    """
    h = request_headers()
    if not h:
        return None
    try:
        payload = {
            "payments": {
                "payment_mode": "UPI",
                "payment_data": {
                    "upi_data": {
                        "txn_mode": "COLLECT",
                        "upi_id":   upi_id
                    }
                }
            }
        }
        r = requests.post(
            f"{BASE}/api/pay/v1/orders/{order_id}/payments",
            json=payload, headers=h, timeout=10
        )
        print(f"[Pine Labs] UPI Collect {order_id}: {r.status_code} {r.text[:200]}")
        return r.json() if r.status_code in [200, 201] else None
    except Exception as e:
        print(f"[Pine Labs] UPI Collect error: {e}")
        return None

def create_upi_intent(order_id: str):
    """
    POST /api/pay/v1/orders/{order_id}/payments
    UPI Intent Payment (generates QR / deep link)
    """
    h = request_headers()
    if not h:
        return None
    try:
        payload = {
            "payments": {
                "payment_mode": "UPI",
                "payment_data": {
                    "upi_data": {
                        "txn_mode": "INTENT"
                    }
                }
            }
        }
        r = requests.post(
            f"{BASE}/api/pay/v1/orders/{order_id}/payments",
            json=payload, headers=h, timeout=10
        )
        print(f"[Pine Labs] UPI Intent {order_id}: {r.status_code} {r.text[:200]}")
        if r.status_code in [200, 201]:
            data = r.json()
            return {
                "success":    True,
                "payment_id": data.get("payment_id"),
                "qr_code":    data.get("payment_data", {}).get("upi_data", {}).get("qr_code"),
                "intent_url": data.get("payment_data", {}).get("upi_data", {}).get("intent_link"),
                "raw":        data
            }
        return None
    except Exception as e:
        print(f"[Pine Labs] UPI Intent error: {e}")
        return None

# ─── REFUNDS ──────────────────────────────────────────

def create_refund(order_id: str, amount: float, reason: str = "Customer request"):
    """
    POST /api/pay/v1/refunds/{order_id}
    Real Pine Labs refund
    """
    h = request_headers()
    if not h:
        return None
    try:
        payload = {
            "merchant_refund_reference": str(int(uuid.uuid4().int % 10**9)),
            "refund_amount":             int(amount * 100),  # paise
            "refund_reason":             reason
        }
        r = requests.post(
            f"{BASE}/api/pay/v1/refunds/{order_id}",
            json=payload, headers=h, timeout=10
        )
        print(f"[Pine Labs] Create Refund for {order_id}: {r.status_code} {r.text[:200]}")
        if r.status_code in [200, 201]:
            data = r.json()
            return {
                "success":   True,
                "refund_id": data.get("refund_id"),
                "status":    data.get("status"),
                "amount":    amount,
                "raw":       data
            }
        return {"success": False, "error": r.text}
    except Exception as e:
        print(f"[Pine Labs] Refund error: {e}")
        return None

# ─── TEST FUNCTION ────────────────────────────────────

def test_pine_labs_connection():
    print("\n🧪 Testing Pine Labs API connection...")
    result = create_order(amount=1.00, customer_name="Test User",
                          mobile="9999999999", merchant_ref=f"TEST{int(uuid.uuid4().int % 10**6)}")
    if result and result.get("success"):
        print(f"✅ Pine Labs ORDER API WORKS!")
        print(f"   Order ID:     {result.get('order_id')}")
        print(f"   Checkout URL: {result.get('checkout_url')}")
        print(f"   Full raw:     {result.get('raw')}")
        return True
    else:
        print(f"❌ Pine Labs Order API failed: {result}")
        return False

if __name__ == "__main__":
    test_pine_labs_connection()