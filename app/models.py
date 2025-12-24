# app/models.py

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class HL7Message(Base):
    __tablename__ = "hl7_messages"

    id = Column(Integer, primary_key=True, index=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_hl7 = Column(Text, nullable=False)

    # Patient info (denormalized for simplicity)
    patient_id = Column(String, index=True)
    patient_first_name = Column(String)
    patient_last_name = Column(String)
    patient_dob = Column(String)
    patient_sex = Column(String)

    # Full FHIR bundle JSON stored as text
    fhir_bundle_json = Column(Text)

    observations = relationship("Observation", back_populates="message")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("hl7_messages.id"), nullable=False)

    code = Column(String, index=True)
    display = Column(String)
    value_num = Column(Float, nullable=True)
    value_raw = Column(String, nullable=True)
    unit = Column(String)
    reference_low = Column(String, nullable=True)
    reference_high = Column(String, nullable=True)
    flag = Column(String, nullable=True)
    observation_datetime = Column(String, nullable=True)
    status = Column(String, nullable=True)

    message = relationship("HL7Message", back_populates="observations")
