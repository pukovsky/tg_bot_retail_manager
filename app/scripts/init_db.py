import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

from app.models import Base

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


def init_db() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")


if __name__ == "__main__":
    init_db()