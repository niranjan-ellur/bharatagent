from database import SessionLocal, Persona, Product, Order, Transaction, ChatMessage, AgentLog, ReconciliationRecord
from datetime import datetime, timedelta
import uuid
import random

def pl_ref():
    return "PL" + uuid.uuid4().hex[:10].upper()

def seed():
    db = SessionLocal()
    if db.query(Persona).count() > 0:
        print("✅ Data already seeded")
        db.close()
        return

    print("🌱 Seeding database...")

    # ─── PERSONAS ─────────────────────────────────────────
    suresh = Persona(name="Suresh Kumar", business_name="Suresh Medical Store",
                     business_type="medical", phone="+91-98765-43210",
                     monthly_budget=50000, avatar_emoji="👨‍⚕️",
                     description="Medical & grocery store in Jayanagar, Bangalore")

    priya = Persona(name="Priya Sharma", business_name="Priya's Homemade Pickles",
                    business_type="d2c", phone="+91-87654-32109",
                    monthly_budget=20000, avatar_emoji="👩‍💻",
                    description="D2C pickle brand selling on Instagram & WhatsApp")

    ravi = Persona(name="Ravi Verma", business_name="Ravi's Unisex Salon",
                   business_type="salon", phone="+91-76543-21098",
                   monthly_budget=30000, avatar_emoji="💆",
                   description="Unisex salon in Koramangala, Bangalore")

    meena = Persona(name="Meena Patel", business_name="Customer",
                    business_type="customer", phone="+91-65432-10987",
                    monthly_budget=5000, avatar_emoji="🛍️",
                    description="Regular customer of Suresh Medical Store")

    db.add_all([suresh, priya, ravi, meena])
    db.commit()
    db.refresh(suresh); db.refresh(priya); db.refresh(ravi); db.refresh(meena)

    # ─── PRODUCTS ─────────────────────────────────────────
    suresh_products = [
        Product(persona_id=suresh.id, name="Dolo 650mg", category="medicine",
                price_inr=30, stock_qty=15, reorder_level=20,
                supplier_name="Shree Pharma", supplier_price=7.20, auto_reorder=True),
        Product(persona_id=suresh.id, name="Telma 40mg", category="medicine",
                price_inr=180, stock_qty=45, reorder_level=10,
                supplier_name="MedPlus Wholesale", supplier_price=140, auto_reorder=True),
        Product(persona_id=suresh.id, name="Dettol Handwash 250ml", category="household",
                price_inr=85, stock_qty=8, reorder_level=10,
                supplier_name="Wholesale Hub", supplier_price=65, auto_reorder=True),
        Product(persona_id=suresh.id, name="Disprin Tablets", category="medicine",
                price_inr=18, stock_qty=180, reorder_level=50,
                supplier_name="Shree Pharma", supplier_price=12, auto_reorder=True),
        Product(persona_id=suresh.id, name="Vicks VapoRub 25g", category="medicine",
                price_inr=95, stock_qty=35, reorder_level=10,
                supplier_name="MedPlus Wholesale", supplier_price=72, auto_reorder=True),
    ]

    priya_products = [
        Product(persona_id=priya.id, name="Mango Pickle 500g", category="food",
                price_inr=280, stock_qty=40, reorder_level=8,
                supplier_name="Self Made", supplier_price=120, auto_reorder=False),
        Product(persona_id=priya.id, name="Mixed Veg Pickle 250g", category="food",
                price_inr=180, stock_qty=25, reorder_level=5,
                supplier_name="Self Made", supplier_price=80, auto_reorder=False),
        Product(persona_id=priya.id, name="Lemon Pickle 500g", category="food",
                price_inr=240, stock_qty=20, reorder_level=5,
                supplier_name="Self Made", supplier_price=100, auto_reorder=False),
        Product(persona_id=priya.id, name="Coconut Chutney Powder 200g", category="food",
                price_inr=150, stock_qty=55, reorder_level=10,
                supplier_name="Self Made", supplier_price=60, auto_reorder=False),
    ]

    ravi_products = [
        Product(persona_id=ravi.id, name="Haircut (Men)", category="service",
                price_inr=200, stock_qty=999, reorder_level=0,
                supplier_name="NA", supplier_price=0, auto_reorder=False),
        Product(persona_id=ravi.id, name="Haircut (Women)", category="service",
                price_inr=400, stock_qty=999, reorder_level=0,
                supplier_name="NA", supplier_price=0, auto_reorder=False),
        Product(persona_id=ravi.id, name="Hair Color", category="service",
                price_inr=800, stock_qty=999, reorder_level=0,
                supplier_name="NA", supplier_price=0, auto_reorder=False),
        Product(persona_id=ravi.id, name="Facial", category="service",
                price_inr=600, stock_qty=999, reorder_level=0,
                supplier_name="NA", supplier_price=0, auto_reorder=False),
        Product(persona_id=ravi.id, name="Beard Trim", category="service",
                price_inr=100, stock_qty=999, reorder_level=0,
                supplier_name="NA", supplier_price=0, auto_reorder=False),
    ]

    db.add_all(suresh_products + priya_products + ravi_products)
    db.commit()

    # ─── HISTORICAL TRANSACTIONS ──────────────────────────
    methods = ["UPI", "Card", "EMI", "Mandate", "NetBanking"]
    issuers = ["HDFC", "ICICI", "Axis Bank", "SBI", "Kotak"]
    statuses = ["success", "success", "success", "success", "failed", "recovered"]

    for persona in [suresh, priya, ravi]:
        for i in range(12):
            amount = round(random.uniform(100, 5000), 2)
            method = random.choice(methods)
            status = random.choice(statuses)
            created = datetime.utcnow() - timedelta(days=random.randint(0, 30))
            txn = Transaction(
                persona_id=persona.id,
                amount_inr=amount,
                payment_method=method,
                payment_rail=f"pine_labs_{method.lower()}",
                status=status,
                retry_count=1 if status == "recovered" else 0,
                bin_number=random.choice(["411111", "523456", "401200"]),
                issuer_bank=random.choice(issuers),
                pine_labs_ref_id=pl_ref(),
                triggered_by=random.choice(["agent", "manual"]),
                created_at=created
            )
            db.add(txn)

    db.commit()

    # ─── CHAT MESSAGES ────────────────────────────────────
    suresh_chats = [
        ("user",  "Order 50 strips of Dolo 650 under ₹8/strip"),
        ("agent", "🔍 Checking distributors...\n✅ Found: Shree Pharma @ ₹7.20/strip\n📦 Total: 50 strips = ₹360\n💳 Routing via Pine Labs UPI (best for <₹500)\n✅ Payment done! Ref: PL7F3A9C2B1E\n📬 Order confirmed. Delivery tomorrow."),
        ("user",  "My payment for handwash failed"),
        ("agent", "⚠️ Found failed transaction of ₹85\n🔄 Retry 1: Switching Card → UPI...\n✅ Recovered ₹85 via UPI!\nNew Pine Labs Ref: PL2D8E4F1A3C\n📦 Order confirmed now!"),
        ("user",  "How much did I spend this month?"),
        ("agent", "📊 This month so far:\n💰 Total Spend: ₹47,200\n📦 12 orders placed\n✅ 10 successful | ⚠️ 1 retried | ❌ 1 blocked\n💡 Tip: Buying Dolo in bulk of 100 saves ₹240/month"),
        ("user",  "Dettol stock is low what should I do?"),
        ("agent", "🚨 Alert: Dettol Handwash is at 8 units (reorder level: 10)\n🤖 Auto-reordering 20 units from Wholesale Hub @ ₹65/unit\n💳 Total ₹1,300 → Routing via Pine Labs Card\n✅ Order placed! Ref: PLA3F2E1D9B8"),
    ]

    priya_chats = [
        ("user",  "Send payment link to Meena for 2 Mango Pickle jars"),
        ("agent", "💳 Pine Labs payment link created!\n👤 Customer: Meena\n📦 2x Mango Pickle 500g = ₹560\n🔗 https://pay.pinelabs.com/link/PLA3B2C1D\n⏰ Link expires in 24 hours\n📲 Sending to Meena now..."),
        ("user",  "Meena hasn't paid yet"),
        ("agent", "📲 Reminder sent to Meena!\n💬 Message: 'Hi Meena! Your order of ₹560 is pending. Pay here: https://pay.pinelabs.com/link/PLA3B2C1D'\n⏰ If unpaid in 2 hours, I'll send a second reminder automatically"),
        ("user",  "How many orders are pending payment?"),
        ("agent", "📋 Pending Payments:\n1. Meena - ₹560 (2 Mango Pickles) - 3 hrs\n2. Rohit - ₹180 (Mixed Veg Pickle) - 1 day\n3. Sunita - ₹430 (Lemon + Coconut) - 2 days\n💰 Total pending: ₹1,170\n🤖 Want me to send reminders to all 3?"),
        ("user",  "Yes send reminders to all"),
        ("agent", "✅ Reminders sent to all 3 customers!\n📲 Meena, Rohit, Sunita notified\n⏰ Auto-retry payment links in 2 hours if unpaid\n💡 Pro tip: 89% of customers pay within 30 mins of reminder!"),
    ]

    ravi_chats = [
        ("user",  "Create invoices for today's appointments"),
        ("agent", "📋 Today's Appointments:\n1. Rahul - Haircut (Men) ₹200\n2. Sunita - Haircut + Color ₹1,200\n3. Vikram - Beard Trim ₹100\n4. Priya - Facial ₹600\n\n💳 Total: ₹2,100\n🔗 Pine Labs payment links sent to all 4!\n✅ Pine Labs Refs generated"),
        ("user",  "Reconcile today's payments"),
        ("agent", "🔁 Running reconciliation...\n✅ 3 payments matched perfectly\n⚠️ 1 mismatch found!\nSunita's payment: Expected ₹1,200 | Received ₹1,000\n🤖 Dispute raised automatically with Pine Labs\nRef: PLD1E2F3A4B5\n📧 You'll hear back in 24 hours"),
        ("user",  "What's my revenue this week?"),
        ("agent", "📊 This Week's Revenue:\n💰 Total: ₹14,200\n📈 23% up vs last week!\n\n🏆 Best day: Wednesday ₹3,800\n💇 Top service: Hair Color (₹4,800)\n⚡ Avg payment time: 4.2 mins\n💡 Tip: Offer combo packages on slow days (Mon/Thu)"),
        ("user",  "Any suspicious transactions this week?"),
        ("agent", "🔍 Anomaly Detection Report:\n🟡 Medium: 2 transactions from same card declined in 30 mins\n✅ Low risk - likely network issue, not fraud\n✅ All settlements matched\n🛡️ No high-risk patterns detected this week"),
    ]

    meena_chats = [
        ("user",  "Do you have BP medicine? Need home delivery"),
        ("agent", "👋 Hi Meena! Yes, we have:\n\n💊 Telma 40mg - ₹180/strip\n💊 Amlodipine 5mg - ₹95/strip\n\nBoth available for home delivery in 2 hours 🚴\nWhich one do you need?"),
        ("user",  "Telma 40mg 2 strips please"),
        ("agent", "✅ Order confirmed!\n📦 2x Telma 40mg = ₹360\n🚴 Home delivery in 2 hours\n\n💳 Pay here: https://pay.pinelabs.com/link/PLM3E2D1C\n\nOrder will be dispatched once payment is received!"),
        ("user",  "I want to return one strip it's wrong medicine"),
        ("agent", "😔 Sorry about that Meena!\n🔄 Refund initiated for 1x Telma 40mg\n💰 Refund amount: ₹180\n🏦 Pine Labs Ref: PLR4F5A6B7C8\n⏰ Back in your account in 2-4 hours\n📲 You'll get an SMS confirmation shortly"),
        ("user",  "What's my order history?"),
        ("agent", "📋 Your Recent Orders from Suresh Medical:\n\n1. ✅ Dolo 650mg x3 - ₹90 - 2 days ago\n2. ✅ Vicks VapoRub - ₹95 - 1 week ago\n3. 🔄 Telma 40mg x1 - ₹180 - Refund pending\n\n💊 Total spent this month: ₹365\n🙏 Thank you for being a loyal customer!"),
    ]

    all_chats = [
        (suresh.id, suresh_chats),
        (priya.id, priya_chats),
        (ravi.id, ravi_chats),
        (meena.id, meena_chats),
    ]

    base_time = datetime.utcnow() - timedelta(hours=2)
    for persona_id, chats in all_chats:
        for i, (sender, message) in enumerate(chats):
            db.add(ChatMessage(
                persona_id=persona_id,
                sender=sender,
                message=message,
                action_taken="none",
                timestamp=base_time + timedelta(minutes=i * 5)
            ))

    # ─── AGENT LOGS ───────────────────────────────────────
    logs = [
        (suresh.id, "payment",    "✅ Auto-ordered 50x Dolo 650mg for ₹360 via UPI. Ref: PL7F3A9C2B1E",         360,  "success"),
        (suresh.id, "retry",      "🔄 Recovered ₹85 failed payment via UPI retry. Ref: PL2D8E4F1A3C",           85,   "recovered"),
        (suresh.id, "reorder",    "📦 Low stock alert: Dettol (8 units). Auto-reordering 20 units.",             1300, "success"),
        (priya.id,  "payment",    "💳 Payment link sent to Meena for ₹560. Ref: PLA3B2C1D",                     560,  "pending"),
        (priya.id,  "insight",    "🤖 3 pending payments worth ₹1,170. Sending auto-reminders.",                 1170, "insight"),
        (ravi.id,   "reconcile",  "⚠️ Mismatch: Sunita payment ₹200 short. Dispute auto-raised.",               200,  "disputed"),
        (ravi.id,   "payment",    "✅ 4 invoices sent. Total ₹2,100 via Pine Labs.",                             2100, "success"),
        (meena.id,  "refund",     "🔄 Refund ₹180 initiated for Meena. Ref: PLR4F5A6B7C8",                     180,  "refunded"),
    ]

    for persona_id, event_type, message, amount, status in logs:
        db.add(AgentLog(
            persona_id=persona_id,
            event_type=event_type,
            message=message,
            amount_inr=amount,
            status=status,
            timestamp=datetime.utcnow() - timedelta(minutes=random.randint(1, 60))
        ))

    db.commit()
    db.close()
    print("✅ Seeding complete — all 4 personas ready!")

if __name__ == "__main__":
    from database import init_db
    init_db()
    seed()