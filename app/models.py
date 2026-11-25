from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Whitelist users and roles: admin, manager, client."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    tg_username: Mapped[Optional[str]] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="manager", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    managed_clients: Mapped[list["Client"]] = relationship(back_populates="manager")
    orders: Mapped[list["Order"]] = relationship(back_populates="manager")


class Client(Base):
    """Bars, restaurants, and venues in the directory."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated search aliases
    delivery_address: Mapped[str] = mapped_column(String(300), nullable=False)
    default_payment_terms: Mapped[Optional[str]] = mapped_column(String(100))
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    manager: Mapped[Optional["User"]] = relationship(back_populates="managed_clients")
    orders: Mapped[list["Order"]] = relationship(back_populates="client")


class Product(Base):
    """Catalog SKU items and unit conversion to base pieces (pcs)."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text)  # Synonyms / shorthand names
    base_unit: Mapped[str] = mapped_column(String(32), default="pcs", nullable=False)
    pack_to_base_factor: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("1.0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stock_balance: Mapped[Optional["StockBalance"]] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")


class StockBalance(Base):
    """Current stock quantities in base units (e.g., from 1C export)."""

    __tablename__ = "stock_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True, nullable=False)
    quantity_pcs: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"), nullable=False)
    source_batch: Mapped[Optional[str]] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="stock_balance")


class Order(Base):
    """Incoming order requests (active and archived via status)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    source_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)  # text | voice | image
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_address: Mapped[Optional[str]] = mapped_column(String(300))
    delivery_date: Mapped[Optional[str]] = mapped_column(String(100))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(40), default="parsed", nullable=False, index=True
    )  # parsed | awaiting_clarification | pending_manager | confirmed | rejected | archived
    clarification_question: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Optional["Client"]] = relationship(back_populates="orders")
    manager: Mapped[Optional["User"]] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """Line items inside an order."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"))
    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    requested_unit: Mapped[str] = mapped_column(String(32), default="pcs", nullable=False)
    normalized_qty_pcs: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    match_status: Mapped[str] = mapped_column(
        String(32), default="unrecognized", nullable=False
    )  # matched | ambiguous | unrecognized
    stock_status: Mapped[str] = mapped_column(
        String(32), default="unknown", nullable=False
    )  # ok | partial | out_of_stock | unknown
    needs_clarification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped[Optional["Product"]] = relationship(back_populates="order_items")


class AuditLog(Base):
    """Audit trail for orders, stock checks, access control, and approvals."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())