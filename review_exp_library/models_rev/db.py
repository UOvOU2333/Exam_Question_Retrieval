"""SQLAlchemy Engine / Session 工厂与建表初始化。"""

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from utils_rev.config import DB_PATH

Base = declarative_base()

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, conn_record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    import hashlib
    from models_rev.User import User
    from models_rev.Case import Case
    from models_rev.CaseImage import CaseImage
    from models_rev.OperationLog import OperationLog

    Base.metadata.create_all(engine)
    with get_session() as s:
        existing = s.query(User).filter_by(role="chief").first()
        if existing is None:
            from utils_rev.config import CHIEF_DEFAULT_PASSWORD, CHIEF_DEFAULT_USERNAME
            pwd_hash = hashlib.sha256(CHIEF_DEFAULT_PASSWORD.encode("utf-8")).hexdigest()
            chief = User(
                username=CHIEF_DEFAULT_USERNAME,
                password_hash=pwd_hash,
                display_name="总编",
                role="chief",
            )
            s.add(chief)
