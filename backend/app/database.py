from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url.get_secret_value(),
    pool_pre_ping=True, pool_size=5, max_overflow=5, pool_timeout=30,
    connect_args={"connect_timeout": 10, "options": "-c timezone=UTC"}, hide_parameters=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
