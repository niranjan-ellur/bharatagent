from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./bharatagent.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── MODELS ───────────────────────────────────────────

class Persona(Base):
    __tablename__ = "personas"
    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String)
    business_name   = Column(String)
    business_type   = Column(String)  # medical / d2c / salon / customer
    phone           = Column(String)
    monthly_budget  = Column(Float, default=50000)
    avatar_emoji    = Column(String, default="👤")
    description     = Column(String)

    products        = relationship("Product", back_populates="persona")
    orders          = relationship("Order", back_populates="persona")
    transactions    = relationship("Transaction", back_populates="persona")
    chat_messages   = relationship("ChatMessage", back_populates="persona")
    agent_logs      = relationship("AgentLog", back_populates="persona")
    reconciliations = relationship("ReconciliationRecord", back_populates="persona")


class Product(Base):
    __tablename__ = "products"
    id               = Column(Integer, primary_key=True, index=True)
    persona_id       = Column(Integer, ForeignKey("personas.id"))
    name             = Column(String)
    category         = Column(String)
    price_inr        = Column(Float)
    stock_qty        = Column(Integer, default=50)
    reorder_level    = Column(Integer, default=10)
    supplier_name    = Column(String)
    supplier_price   = Column(Float)
    auto_reorder     = Column(Boolean, default=True)

    persona          = relationship("Persona", back_populates="products")
    orders           = relationship("Order", back_populates="product")


class Order(Base):
    __tablename__ = "orders"
    id              = Column(Integer, primary_key=True, index=True)
    persona_id      = Column(Integer, ForeignKey("personas.id"))
    product_id      = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name    = Column(String)
    quantity        = Column(Integer, default=1)
    total_amount    = Column(Float)
    order_type      = Column(String, default="sale")  # purchase / sale / service
    status          = Column(String, default="pending")  # pending/confirmed/failed/refunded
    customer_name   = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    persona         = relationship("Persona", back_populates="orders")
    product         = relationship("Product", back_populates="orders")
    transactions    = relationship("Transaction", back_populates="order")


class Transaction(Base):
    __tablename__ = "transactions"
    id               = Column(Integer, primary_key=True, index=True)
    persona_id       = Column(Integer, ForeignKey("personas.id"))
    order_id         = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount_inr       = Column(Float)
    payment_method   = Column(String)   # UPI / Card / EMI / Mandate / NetBanking
    payment_rail     = Column(String)   # pine_labs_upi / pine_labs_card etc
    status           = Column(String, default="pending")  # success/failed/pending/retrying/recovered/refunded
    retry_count      = Column(Integer, default=0)
    bin_number       = Column(String, nullable=True)
    issuer_bank      = Column(String, nullable=True)
    pine_labs_ref_id = Column(String)
    payment_link     = Column(String, nullable=True)
    triggered_by     = Column(String, default="agent")  # agent / manual / customer
    created_at       = Column(DateTime, default=datetime.utcnow)

    persona          = relationship("Persona", back_populates="transactions")
    order            = relationship("Order", back_populates="transactions")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id           = Column(Integer, primary_key=True, index=True)
    persona_id   = Column(Integer, ForeignKey("personas.id"))
    sender       = Column(String)   # user / agent
    message      = Column(Text)
    action_taken = Column(String, default="none")
    timestamp    = Column(DateTime, default=datetime.utcnow)

    persona      = relationship("Persona", back_populates="chat_messages")


class AgentLog(Base):
    __tablename__ = "agent_logs"
    id          = Column(Integer, primary_key=True, index=True)
    persona_id  = Column(Integer, ForeignKey("personas.id"))
    event_type  = Column(String)   # payment / retry / reorder / reconcile / insight
    message     = Column(Text)
    amount_inr  = Column(Float, nullable=True)
    status      = Column(String, nullable=True)
    timestamp   = Column(DateTime, default=datetime.utcnow)

    persona     = relationship("Persona", back_populates="agent_logs")


class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"
    id                 = Column(Integer, primary_key=True, index=True)
    persona_id         = Column(Integer, ForeignKey("personas.id"))
    date               = Column(String)
    total_orders       = Column(Integer, default=0)
    total_expected_inr = Column(Float, default=0)
    total_settled_inr  = Column(Float, default=0)
    mismatches_count   = Column(Integer, default=0)
    dispute_raised     = Column(Boolean, default=False)
    anomalies          = Column(Text, nullable=True)
    status             = Column(String, default="matched")
    created_at         = Column(DateTime, default=datetime.utcnow)

    persona            = relationship("Persona", back_populates="reconciliations")


def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")