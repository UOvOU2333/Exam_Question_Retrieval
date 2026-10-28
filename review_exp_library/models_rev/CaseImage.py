"""CaseImage 模型。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from models_rev.db import Base


class CaseImage(Base):
    __tablename__ = "case_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(String(256), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
