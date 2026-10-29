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
    from models_rev.Book import Book
    from models_rev.Section import Section
    from models_rev.CaseType import CaseType
    from models_rev.Subject import Subject

    Base.metadata.create_all(engine)
    with get_session() as s:
        from utils_rev.config import (
            ADMIN_DEFAULT_USERNAME, ADMIN_DEFAULT_PASSWORD,
        )

        admin = s.query(User).filter_by(role="admin").first()
        if admin is None:
            admin_hash = hashlib.sha256(ADMIN_DEFAULT_PASSWORD.encode("utf-8")).hexdigest()
            s.add(User(
                username=ADMIN_DEFAULT_USERNAME,
                password_hash=admin_hash,
                display_name="管理员",
                role="admin",
            ))

        _seed_catalog(s)


def _seed_catalog(s):
    from models_rev.Book import Book
    from models_rev.Section import Section
    from models_rev.CaseType import CaseType
    from models_rev.Subject import Subject

    if not (s.query(Book).count() == 0 and s.query(Section).count() == 0
            and s.query(CaseType).count() == 0 and s.query(Subject).count() == 0):
        return

    books = ["《大题必备·材料词》", "《必刷100讲》", "《最后十课》", "《解题大师》"]
    sections = ["审稿问题汇总", "审稿优秀案例"]
    problem_types = ["知识类问题", "解析类问题"]
    excellent_types = ["知识类优秀案例", "解析类优秀案例"]
    from utils_rev.config import DEFAULT_SUBJECTS
    subjects = DEFAULT_SUBJECTS

    for i, name in enumerate(books, 1):
        s.add(Book(name=name, sort_order=i, is_deleted=False))
    s.flush()
    for i, name in enumerate(sections, 1):
        s.add(Section(name=name, sort_order=i, is_deleted=False))
    s.flush()

    sec_problem = s.query(Section).filter_by(name="审稿问题汇总").first()
    sec_excellent = s.query(Section).filter_by(name="审稿优秀案例").first()
    for i, ct_name in enumerate(problem_types, 1):
        s.add(CaseType(section_id=sec_problem.id, name=ct_name, layout_key=ct_name, sort_order=i, is_deleted=False))
    for i, ct_name in enumerate(excellent_types, 1):
        s.add(CaseType(section_id=sec_excellent.id, name=ct_name, layout_key=ct_name, sort_order=i, is_deleted=False))
    s.flush()

    for i, sub_name in enumerate(subjects, 1):
        s.add(Subject(name=sub_name, sort_order=i, is_deleted=False))
    s.flush()
