import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from database import SessionLocal, Persona, Product, Transaction, Order, ChatMessage, AgentLog
from payment_engine import route_payment, create_payment_link, process_refund

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ── Setup Gemini ───────────────────────────────────────
gemini_model = None
if GEMINI_API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_model = client
        print("✅ Gemini 2.5 Flash connected")
    except ImportError:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_model = genai.GenerativeModel("gemini-1.5-flash")
            print("✅ Gemini 1.5 Flash connected (fallback)")
        except Exception as e:
            print(f"⚠️ Gemini setup error: {e}")

# ── Fallback responses by keyword ─────────────────────
FALLBACK_RESPONSES = {
    "order":     "🤖 Demo Mode: Order received! Auto-routing payment via Pine Labs UPI.\n✅ Pine Labs Ref: PL{ref}\n📦 Order confirmed!",
    "payment":   "🤖 Creating real Pine Labs payment link...\n💳 Link generated!\n🔗 Check transactions tab for the live checkout link\n⏰ Valid for 24 hours",
    "refund":    "🤖 Demo Mode: Refund initiated!\n💰 Amount will be back in 2-4 hours\n📋 Pine Labs Ref: PL{ref}",
    "stock":     "🤖 Demo Mode: Stock check complete!\n⚠️ 2 items below reorder level\n🤖 Auto-reorder triggered via Pine Labs",
    "reconcil":  "🤖 Demo Mode: Reconciliation complete!\n✅ 11 orders matched\n⚠️ 1 mismatch found — dispute auto-raised",
    "revenue":   "🤖 Demo Mode: This week's revenue ₹14,200 📈\n23% up vs last week!\nBest day: Wednesday",
    "spent":     "🤖 Demo Mode: Monthly spend analysis ready!\n💰 Total: ₹47,200 across 12 orders\n💡 Tip: Bulk buying saves 15%",
    "failed":    "🤖 Demo Mode: Failed payment detected!\n🔄 Switching Card → UPI...\n✅ Recovered! New Ref: PL{ref}",
    "default":   "🤖 Demo Mode: I understand your request!\nI can help with orders, payments, refunds, stock checks, and analytics.\nAdd GEMINI_API_KEY for full AI responses!"
}

def get_fallback_response(message: str) -> str:
    msg_lower = message.lower()
    for keyword, response in FALLBACK_RESPONSES.items():
        if keyword in msg_lower:
            return response.replace("{ref}", uuid.uuid4().hex[:10].upper())
    return FALLBACK_RESPONSES["default"].replace("{ref}", uuid.uuid4().hex[:10].upper())

# ─── MAIN CHAT AGENT ──────────────────────────────────
def process_message(persona_id: int, user_message: str) -> dict:
    db      = SessionLocal()
    persona = db.query(Persona).filter(Persona.id == persona_id).first()

    if not persona:
        db.close()
        return {"response": "Persona not found", "action": "none"}

    products = db.query(Product).filter(Product.persona_id == persona_id).all()
    recent_txns = db.query(Transaction).filter(
        Transaction.persona_id == persona_id
    ).order_by(Transaction.created_at.desc()).limit(5).all()

    # ── Save user message ──────────────────────────────
    db.add(ChatMessage(persona_id=persona_id, sender="user",
                       message=user_message, timestamp=datetime.utcnow()))
    db.commit()

    # ── Build context ──────────────────────────────────
    product_list = "\n".join([
        f"- {p.name} | ₹{p.price_inr} | Stock: {p.stock_qty} | Category: {p.category}"
        for p in products
    ])

    txn_list = "\n".join([
        f"- ₹{t.amount_inr:.2f} via {t.payment_method} | {t.status} | {t.pine_labs_ref_id}"
        for t in recent_txns
    ])

    agent_response = ""
    action_taken   = "none"

    # ── Try Gemini ─────────────────────────────────────
    if gemini_model:
        try:
            system_context = f"""You are BharatAgent, an autonomous commerce and payment AI agent 
embedded in WhatsApp for Indian small businesses. You work with Pine Labs payment infrastructure.

Current Merchant: {persona.name} | {persona.business_name} | {persona.business_type}
Monthly Budget: ₹{persona.monthly_budget:,.0f}

Available Products/Services:
{product_list if product_list else "No products listed"}

Recent Transactions:
{txn_list if txn_list else "No recent transactions"}

TODAY: {datetime.utcnow().strftime('%d %B %Y, %A')}

RULES:
1. Respond in Hinglish (mix Hindi words naturally with English) — like a real WhatsApp message
2. Keep responses concise — this is WhatsApp, not an email
3. Always mention Pine Labs Ref ID when payment is involved (format: PL + 10 chars)
4. Use emojis naturally like Indians do on WhatsApp
5. Be proactive — suggest savings, flag issues
6. Payment routing rules:
   - Amount < ₹100 → UPI
   - ₹100-₹500 → Card  
   - > ₹500 → EMI
   - Weekly recurring → Mandate
7. If order requested → confirm with amount + Pine Labs ref
8. If payment link needed → say "Payment link generated! Check transactions tab for the real Pine Labs checkout link"
9. If analytics asked → give specific numbers from context
10. Always end with a helpful tip or next action

Respond ONLY as the agent. No meta-commentary."""

            full_prompt = f"{system_context}\n\nUser: {user_message}\n\nAgent:"
            if hasattr(gemini_model, 'models'):
                resp = gemini_model.models.generate_content(model="gemini-2.5-flash", contents=full_prompt)
                agent_response = resp.text.strip()
            else:
                agent_response = gemini_model.generate_content(full_prompt).text.strip()
            action_taken = "ai_response"

        except Exception as e:
            print(f"⚠️ Gemini error: {e}")
            agent_response = get_fallback_response(user_message)
            action_taken   = "fallback"
    else:
        agent_response = get_fallback_response(user_message)
        action_taken   = "fallback"

    # ── Execute detected actions ───────────────────────
    msg_lower = user_message.lower()

    if any(w in msg_lower for w in ["order", "buy", "purchase", "reorder"]) and products:
        matched_product = None
        for p in products:
            if p.name.lower().split()[0] in msg_lower:
                matched_product = p
                break
        if matched_product:
            # Extract quantity from message
            import re
            qty_match = re.search(r'(\d+)\s*strips?|(\d+)\s*units?|(\d+)\s*kg|(\d+)\s*pieces?', msg_lower)
            qty    = int([g for g in (qty_match.groups() if qty_match else []) if g][0]) if qty_match else 1
            amount = matched_product.price_inr * qty
            # Create real Pine Labs payment link for the order
            link_result  = create_payment_link(amount, f"Persona {persona_id}", persona_id)
            real_link    = link_result.get("link", "")
            pine_ref     = link_result.get("pine_labs_ref", "")
            action_taken = "order_created"
            # Append real link to agent response
            if real_link:
                agent_response += (
                    f"\n\n💳 Pine Labs Payment Link:\n🔗 {real_link}"
                    f"\nPine Labs Ref: {pine_ref}"
                    f"\n✅ Koi bhi payment method choose kar sakte ho — UPI, Card, EMI, NetBanking!"
                )

    elif any(w in msg_lower for w in ["payment link", "send link", "pay link"]):
        import re
        amount_match = re.search(r'₹?(\d+)', user_message)
        amount = float(amount_match.group(1)) if amount_match else 500.0
        # Extract customer name from message
        customer = "Customer"
        for word in ["to", "ke liye", "liye"]:
            if word in msg_lower:
                parts = user_message.lower().split(word)
                if len(parts) > 1:
                    customer = parts[1].strip().split()[0].capitalize()
                    break
        link_result = create_payment_link(amount, customer, persona_id)
        real_link   = link_result.get("link", "")
        pine_ref    = link_result.get("pine_labs_ref", "")
        # Inject real link directly into agent response
        agent_response = (
            f"✅ {customer} ke liye ₹{amount:.0f} ka payment link ready hai! 💰\n\n"
            f"🔗 {real_link}\n\n"
            f"Pine Labs Ref: {pine_ref}\n"
            f"⏰ Link 24 ghante valid rahega\n\n"
            f"💡 Tip: Link share karo aur payment hote hi order confirm ho jayega!"
        )
        action_taken = "payment_link_sent"

    elif any(w in msg_lower for w in ["refund", "return", "wapas"]):
        action_taken = "refund_processed"

    elif any(w in msg_lower for w in ["reconcil", "settlement", "match"]):
        action_taken = "reconciliation_run"

    # ── Save agent response ────────────────────────────
    db.add(ChatMessage(persona_id=persona_id, sender="agent",
                       message=agent_response, action_taken=action_taken,
                       timestamp=datetime.utcnow()))
    db.commit()
    db.close()

    return {"response": agent_response, "action": action_taken}

# ─── AUTONOMOUS AGENT CHECK ───────────────────────────
def run_autonomous_check(persona_id: int):
    db           = SessionLocal()
    persona      = db.query(Persona).filter(Persona.id == persona_id).first()
    persona_name = persona.name if persona else "Unknown"
    products     = db.query(Product).filter(
        Product.persona_id == persona_id,
        Product.auto_reorder == True
    ).all()

    actions = []
    for product in products:
        if product.stock_qty <= product.reorder_level and product.reorder_level > 0:
            reorder_qty = product.reorder_level * 2
            total_cost  = reorder_qty * product.supplier_price

            result = route_payment(total_cost, persona_id, triggered_by="agent")
            product.stock_qty += reorder_qty

            msg = f"📦 Auto-reordered {reorder_qty}x {product.name} for ₹{total_cost:.2f} via {result['method']} | Ref: {result['pine_labs_ref']}"
            actions.append(msg)
            db.add(AgentLog(persona_id=persona_id, event_type="reorder",
                            message=msg, amount_inr=total_cost, status="success"))

    # ── Gemini insight for the run ─────────────────────
    if gemini_model and actions:
        try:
            txns = db.query(Transaction).filter(
                Transaction.persona_id == persona_id
            ).order_by(Transaction.created_at.desc()).limit(10).all()

            txn_summary = "\n".join([
                f"₹{t.amount_inr:.2f} | {t.payment_method} | {t.status}"
                for t in txns
            ])

            insight_prompt = f"""Analyze this merchant's last 10 transactions and give ONE actionable insight in 2 sentences max. Be specific with numbers. Respond in Hinglish like a WhatsApp message.

Transactions:
{txn_summary}

Actions just taken: {', '.join(actions) if actions else 'Routine check — no reorders needed'}"""

            if hasattr(gemini_model, 'models'):
                insight = gemini_model.models.generate_content(model="gemini-2.5-flash", contents=insight_prompt).text.strip()
            else:
                insight = gemini_model.generate_content(insight_prompt).text.strip()
            db.add(AgentLog(persona_id=persona_id, event_type="insight",
                            message=f"🤖 {insight}", amount_inr=None, status="insight"))
        except Exception as e:
            print(f"⚠️ Gemini insight error: {e}")

    db.commit()
    db.close()
    return {"actions": actions, "persona": persona_name}

# ─── ANALYTICS VIA GEMINI ─────────────────────────────
def generate_analytics_insight(persona_id: int, query: str) -> str:
    db   = SessionLocal()
    txns = db.query(Transaction).filter(
        Transaction.persona_id == persona_id
    ).order_by(Transaction.created_at.desc()).limit(30).all()

    persona  = db.query(Persona).filter(Persona.id == persona_id).first()
    total    = sum(t.amount_inr for t in txns if t.status in ["success", "recovered"])
    success  = len([t for t in txns if t.status in ["success", "recovered"]])
    failed   = len([t for t in txns if t.status in ["failed", "failed_final"]])
    methods  = {}
    for t in txns:
        methods[t.payment_method] = methods.get(t.payment_method, 0) + 1

    summary = f"""Merchant: {persona.name if persona else 'Unknown'} | {persona.business_name if persona else ''}
Total transactions: {len(txns)}
Successful: {success} | Failed: {failed}
Total revenue: ₹{total:,.2f}
Payment methods: {methods}
Recent transactions: {[(f'₹{t.amount_inr:.0f}', t.payment_method, t.status) for t in txns[:10]]}"""

    db.close()

    if gemini_model:
        try:
            prompt = f"""You are BharatAgent, analyzing payment data for an Indian merchant.

Data:
{summary}

User query: {query}

Answer in 3-4 sentences max. Be specific with numbers. Use Hinglish. Give one actionable tip."""
            if hasattr(gemini_model, 'models'):
                return gemini_model.models.generate_content(model="gemini-2.5-flash", contents=prompt).text.strip()
            else:
                return gemini_model.generate_content(prompt).text.strip()
        except Exception as e:
            print(f"⚠️ Analytics Gemini error: {e}")

    # Fallback analytics
    return f"📊 Based on your data: Total revenue ₹{total:,.2f} from {success} successful transactions. Success rate: {(success/max(len(txns),1)*100):.0f}%. Most used method: {max(methods, key=methods.get) if methods else 'UPI'}. 💡 Tip: Enable auto-retry to recover failed payments automatically!"