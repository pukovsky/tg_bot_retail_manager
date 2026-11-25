import os
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Client, Order, OrderItem, Product, StockBalance, User

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "copilot_user")
db_password = os.getenv("POSTGRES_PASSWORD")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "order_copilot")

DATABASE_URL = os.getenv(
    "DATABASE_URL_SYNC",
    f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
)



def seed() -> None:
    engine = create_engine(DATABASE_URL, echo=False)

    with Session(engine) as session:
        # 1. Whitelist users
        manager = session.scalar(select(User).where(User.tg_user_id == 100001))
        if not manager:
            manager = User(
                tg_user_id=100001,
                tg_username="alex_manager",
                full_name="Alexey Volkov",
                role="manager",
                is_active=True,
            )
            session.add(manager)
            session.flush()

        # 2. Clients
        clients_data = [
            {
                "name": "Bar Noir",
                "aliases": "noir, бар нуар, нуар самара",
                "delivery_address": "Samara, Leningradskaya St, 25",
                "default_payment_terms": "Net 7",
                "manager_id": manager.id,
            },
            {
                "name": "Bistro Verde",
                "aliases": "verde, верде, бистро верде",
                "delivery_address": "Samara, Kuibysheva St, 88",
                "default_payment_terms": "Prepayment",
                "manager_id": manager.id,
            },
        ]
        clients_by_name: dict[str, Client] = {}
        for item in clients_data:
            existing = session.scalar(select(Client).where(Client.name == item["name"]))
            if not existing:
                existing = Client(**item)
                session.add(existing)
                session.flush()
            clients_by_name[item["name"]] = existing

        # 3. Products + Stock balances
        products_data = [
            {
                "sku": "GIN-070",
                "name": "Dry Gin 0.7L",
                "aliases": "gin 0.7, джин 0.7, сухой джин",
                "base_unit": "pcs",
                "pack_to_base_factor": Decimal("1"),
                "stock_pcs": Decimal("45"),
            },
            {
                "sku": "TON-020",
                "name": "Tonic Water 0.2L (Pack 24)",
                "aliases": "tonic, тоник, тоник упаковка",
                "base_unit": "pcs",
                "pack_to_base_factor": Decimal("24"),
                "stock_pcs": Decimal("120"),
            },
            {
                "sku": "SYR-100",
                "name": "Vanilla Syrup 1.0L",
                "aliases": "vanilla syrup, ванильный сироп",
                "base_unit": "pcs",
                "pack_to_base_factor": Decimal("1"),
                "stock_pcs": Decimal("4"),
            },
        ]

        products_by_sku: dict[str, Product] = {}
        for item in products_data:
            prod = session.scalar(select(Product).where(Product.sku == item["sku"]))
            if not prod:
                prod = Product(
                    sku=item["sku"],
                    name=item["name"],
                    aliases=item["aliases"],
                    base_unit=item["base_unit"],
                    pack_to_base_factor=item["pack_to_base_factor"],
                )
                session.add(prod)
                session.flush()

                balance = StockBalance(
                    product_id=prod.id,
                    quantity_pcs=item["stock_pcs"],
                    source_batch="seed_batch_01",
                )
                session.add(balance)
            products_by_sku[item["sku"]] = prod

        # 4. Sample order
        sample_client = clients_by_name["Bar Noir"]
        existing_order = session.scalar(
            select(Order).where(Order.raw_input == "Need 10 gin 0.7 and 2 packs of tonic tomorrow")
        )
        if not existing_order:
            order = Order(
                client_id=sample_client.id,
                manager_id=manager.id,
                source_type="text",
                raw_input="Need 10 gin 0.7 and 2 packs of tonic tomorrow",
                delivery_address=sample_client.delivery_address,
                delivery_date="tomorrow",
                payment_terms=sample_client.default_payment_terms,
                status="pending_manager",
            )
            session.add(order)
            session.flush()

            session.add_all([
                OrderItem(
                    order_id=order.id,
                    product_id=products_by_sku["GIN-070"].id,
                    raw_name="gin 0.7",
                    requested_qty=Decimal("10"),
                    requested_unit="pcs",
                    normalized_qty_pcs=Decimal("10"),
                    match_status="matched",
                    stock_status="ok",
                    needs_clarification=False,
                    sort_order=1,
                ),
                OrderItem(
                    order_id=order.id,
                    product_id=products_by_sku["TON-020"].id,
                    raw_name="2 packs of tonic",
                    requested_qty=Decimal("2"),
                    requested_unit="pack",
                    normalized_qty_pcs=Decimal("48"),
                    match_status="matched",
                    stock_status="ok",
                    needs_clarification=False,
                    sort_order=2,
                ),
            ])

            session.add(
                AuditLog(
                    actor_tg_id=manager.tg_user_id,
                    action="seed_order_created",
                    entity_type="order",
                    entity_id=str(order.id),
                    details="Initial seeded sample order",
                )
            )

        session.commit()
    print("Seed data applied successfully.")


if __name__ == "__main__":
    seed()