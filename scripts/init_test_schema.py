# scripts/init_test_schema.py
from sqlalchemy import create_engine
from src.core.config import settings
from src.db.base import Base

def main():
    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", ""), future=True)
    with engine.begin() as conn:
        Base.metadata.create_all(bind=conn)

if __name__ == "__main__":
    main()
