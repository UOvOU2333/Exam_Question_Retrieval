"""OperationLog 模型。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from models_rev.db import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator = Column(String(64), nullable=False)
    case_id = Column(Integer, nullable=True)
    action = Column(String(32), nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
