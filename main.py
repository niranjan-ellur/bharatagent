from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn

from database import init_db, get_db, Persona, Product, Transaction, ChatMessage, AgentLog, ReconciliationRecord, Order, SessionLocal
from seed_data import seed
from payment_engine import route_payment, smart_retry, create_payment_link, process_refund, simulate_price_spike
from reconciliation import run_reconciliation
from agent import process_message, run_autonomous_check, generate_analytics_insight

# ─── SCHEDULER ────────────────────────────────────────
scheduler = BackgroundScheduler()

def scheduled_agent_run():
    db = SessionLocal()
    persona_ids = [p.id for p in db.query(Persona).all()]
    db.close()
    for pid in persona_ids:
        try:
            run_autonomous_check(pid)
        except Exception as e:
            print(f"⚠️ Scheduled agent error for persona {pid}: {e}")

def scheduled_reconciliation():
    db = SessionLocal()
    persona_ids = [p.id for p in db.query(Persona).all()]
    db.close()
    for pid in persona_ids:
        try:
            run_reconciliation(pid)
        except Exception as e:
            print(f"⚠️ Scheduled reconciliation error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    seed()
    scheduler.add_job(scheduled_agent_run, "interval", seconds=60, id="agent_run")
    scheduler.add_job(scheduled_reconciliation, "interval", seconds=300, id="reconcile")
    scheduler.start()
    print("✅ BharatAgent started! Visit http://localhost:8000")
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(title="BharatAgent", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# ─── PINE LABS HACKATHON COVERAGE MAP ─────────────────
# 1. Intelligent Decisioning  → payment_engine.route_payment()
# 2. Smart Retry Engine       → payment_engine.smart_retry()
# 3. Conversational Commerce  → agent.process_message() + WhatsApp UI
# 4. Voice Payment Agents     → Web Speech API in index.html
# 5. Agentic Workflows        → agent.run_autonomous_check()
# 6. Agentic Checkout         → payment_engine (0-click mandate flow)
# 7. Agentic Dashboards       → agent.generate_analytics_insight()
# 8. Smart Reconciliation     → reconciliation.run_reconciliation()

# ─── ROUTES ───────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/personas")
async def get_personas(db: Session = Depends(get_db)):
    personas = db.query(Persona).all()
    return [{"id": p.id, "name": p.name, "business_name": p.business_name,
             "business_type": p.business_type, "avatar_emoji": p.avatar_emoji,
             "description": p.description, "monthly_budget": p.monthly_budget}
            for p in personas]

@app.get("/api/dashboard/{persona_id}")
async def get_dashboard(persona_id: int, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        return JSONResponse({"error": "Persona not found"}, status_code=404)

    # Transactions
    txns = db.query(Transaction).filter(
        Transaction.persona_id == persona_id
    ).order_by(Transaction.created_at.desc()).limit(15).all()

    # Chat messages
    chats = db.query(ChatMessage).filter(
        ChatMessage.persona_id == persona_id
    ).order_by(ChatMessage.timestamp.asc()).limit(30).all()

    # Agent logs
    logs = db.query(AgentLog).filter(
        AgentLog.persona_id == persona_id
    ).order_by(AgentLog.timestamp.desc()).limit(10).all()

    # Products
    products = db.query(Product).filter(Product.persona_id == persona_id).all()

    # Stats
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    month_txns  = db.query(Transaction).filter(
        Transaction.persona_id == persona_id,
        Transaction.created_at >= month_start,
        Transaction.status.in_(["success", "recovered"])
    ).all()

    monthly_spend  = sum(t.amount_inr for t in month_txns)
    savings        = sum(log.amount_inr or 0 for log in
                         db.query(AgentLog).filter(
                             AgentLog.persona_id == persona_id,
                             AgentLog.status == "blocked_spike"
                         ).all())

    auto_reorders  = db.query(AgentLog).filter(
        AgentLog.persona_id == persona_id,
        AgentLog.event_type == "reorder",
        AgentLog.timestamp >= month_start
    ).count()

    # Chart data — last 7 days
    chart_labels = []
    chart_revenue = []
    for i in range(6, -1, -1):
        day       = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end   = day.replace(hour=23, minute=59, second=59)
        day_txns  = db.query(Transaction).filter(
            Transaction.persona_id == persona_id,
            Transaction.created_at >= day_start,
            Transaction.created_at <= day_end,
            Transaction.status.in_(["success", "recovered"])
        ).all()
        chart_labels.append(day.strftime("%d %b"))
        chart_revenue.append(sum(t.amount_inr for t in day_txns))

    # Payment method split
    method_counts = {}
    for t in txns:
        method_counts[t.payment_method] = method_counts.get(t.payment_method, 0) + 1

    # Success rate trend
    success_rates = []
    for i in range(6, -1, -1):
        day       = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end   = day.replace(hour=23, minute=59, second=59)
        day_all   = db.query(Transaction).filter(
            Transaction.persona_id == persona_id,
            Transaction.created_at >= day_start,
            Transaction.created_at <= day_end
        ).all()
        if day_all:
            rate = len([t for t in day_all if t.status in ["success", "recovered"]]) / len(day_all) * 100
        else:
            rate = 0
        success_rates.append(round(rate, 1))

    # Latest reconciliation
    recon = db.query(ReconciliationRecord).filter(
        ReconciliationRecord.persona_id == persona_id
    ).order_by(ReconciliationRecord.created_at.desc()).first()

    return {
        "persona": {"id": persona.id, "name": persona.name,
                    "business_name": persona.business_name,
                    "business_type": persona.business_type,
                    "avatar_emoji": persona.avatar_emoji,
                    "monthly_budget": persona.monthly_budget},
        "stats": {
            "monthly_spend":   round(monthly_spend, 2),
            "monthly_budget":  persona.monthly_budget,
            "auto_reorders":   auto_reorders,
            "savings":         round(savings, 2),
            "total_txns":      len(txns),
            "success_rate":    round(len([t for t in txns if t.status in ["success","recovered"]]) / max(len(txns),1) * 100, 1)
        },
        "transactions": [
            {"id": t.id, "amount": t.amount_inr, "method": t.payment_method,
             "status": t.status, "pine_ref": t.pine_labs_ref_id,
             "issuer": t.issuer_bank, "bin": t.bin_number,
             "retry_count": t.retry_count, "payment_link": t.payment_link,
             "time": t.created_at.strftime("%d %b %H:%M")}
            for t in txns
        ],
        "chat_messages": [
            {"id": m.id, "sender": m.sender, "message": m.message,
             "action": m.action_taken,
             "time": m.timestamp.strftime("%H:%M")}
            for m in chats
        ],
        "agent_logs": [
            {"id": l.id, "event_type": l.event_type, "message": l.message,
             "amount": l.amount_inr, "status": l.status,
             "time": l.timestamp.strftime("%d %b %H:%M")}
            for l in logs
        ],
        "products": [
            {"id": p.id, "name": p.name, "category": p.category,
             "price": p.price_inr, "stock": p.stock_qty,
             "reorder_level": p.reorder_level, "auto_reorder": p.auto_reorder,
             "supplier": p.supplier_name, "supplier_price": p.supplier_price,
             "status": "critical" if p.stock_qty <= p.reorder_level
                       else "low" if p.stock_qty <= p.reorder_level * 1.2
                       else "good"}
            for p in products
        ],
        "reconciliation": {
            "matched":          recon.total_orders - recon.mismatches_count if recon else 0,
            "mismatched":       recon.mismatches_count if recon else 0,
            "total_settled":    recon.total_settled_inr if recon else 0,
            "total_expected":   recon.total_expected_inr if recon else 0,
            "dispute_raised":   recon.dispute_raised if recon else False,
            "status":           recon.status if recon else "not_run"
        },
        "chart_data": {
            "labels":        chart_labels,
            "revenue":       chart_revenue,
            "methods":       method_counts,
            "success_rates": success_rates
        }
    }

@app.post("/api/chat/{persona_id}")
async def chat(persona_id: int, request: Request):
    body    = await request.json()
    message = body.get("message", "")
    if not message.strip():
        return {"error": "Empty message"}
    result = process_message(persona_id, message)
    return result

@app.post("/api/run-agent/{persona_id}")
async def run_agent(persona_id: int):
    result = run_autonomous_check(persona_id)
    return {"status": "completed", "result": result}

@app.post("/api/retry/{transaction_id}")
async def retry_payment(transaction_id: int):
    result = smart_retry(transaction_id)
    return result

@app.post("/api/reconcile/{persona_id}")
async def reconcile(persona_id: int):
    result = run_reconciliation(persona_id)
    return result

@app.post("/api/refund/{transaction_id}")
async def refund(transaction_id: int):
    result = process_refund(transaction_id)
    return result

@app.get("/api/analytics/{persona_id}")
async def analytics(persona_id: int, q: str = "Give me a summary of my business performance"):
    insight = generate_analytics_insight(persona_id, q)
    return {"insight": insight}

@app.post("/api/payment-link/{persona_id}")
async def payment_link(persona_id: int, request: Request):
    body          = await request.json()
    amount        = float(body.get("amount", 500))
    customer_name = body.get("customer_name", "Customer")
    result        = create_payment_link(amount, customer_name, persona_id)
    return result

@app.get("/api/simulate-spike/{product_id}")
async def price_spike(product_id: int):
    result = simulate_price_spike(product_id)
    return result

@app.post("/api/toggle-auto/{product_id}")
async def toggle_auto(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return {"error": "Product not found"}
    product.auto_reorder = not product.auto_reorder
    db.commit()
    return {"product_id": product_id, "auto_reorder": product.auto_reorder}

@app.post("/api/reset-demo")
async def reset_demo(db: Session = Depends(get_db)):
    db.query(Transaction).delete()
    db.query(ChatMessage).delete()
    db.query(AgentLog).delete()
    db.query(ReconciliationRecord).delete()
    db.commit()
    # Re-seed chat messages
    from seed_data import seed
    db.query(Persona).delete()
    db.query(Product).delete()
    db.commit()
    seed()
    return {"status": "Demo reset complete! Fresh start ready."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)