import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

load_dotenv()


def get_database_url() -> URL:
    if url := os.environ.get("DATABASE_URL"):
        return make_url(url)
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "epl"),
        password=os.environ.get("POSTGRES_PASSWORD", "epl"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "epl"),
    )
