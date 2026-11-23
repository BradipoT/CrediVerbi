import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .db import Base


class VerdictRating(str, enum.Enum):
    VRAI = "vrai"
    PARTIELLEMENT_VRAI = "partiellement_vrai"
    TROMPLEUR = "trompeur"
    FAUX = "faux"
    INDETERMINE = "indetermine"


RATING_LABELS = {
    VerdictRating.VRAI: "Vrai",
    VerdictRating.PARTIELLEMENT_VRAI: "Partiellement vrai",
    VerdictRating.TROMPLEUR: "Trompeur",
    VerdictRating.FAUX: "Faux",
    VerdictRating.INDETERMINE: "Indéterminé",
}


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class Organization(Base):
    __tablename__ = "organization"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    kind = Column(String(50), nullable=False, default="autre")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    persons = relationship("Person", back_populates="organization")


class Person(Base):
    __tablename__ = "person"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    role = Column(String(200), nullable=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=True)
    is_public_figure = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="persons")
    statements = relationship("Statement", back_populates="person")


class Statement(Base):
    __tablename__ = "statement"

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey("person.id"), nullable=False)
    quote = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    source_url = Column(String(2000), nullable=True)
    source_title = Column(String(500), nullable=True)
    said_at = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    person = relationship("Person", back_populates="statements")
    verdicts = relationship(
        "Verdict", back_populates="statement", order_by="Verdict.created_at"
    )


class Verdict(Base):
    __tablename__ = "verdict"

    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("statement.id"), nullable=False)
    rating = Column(
        Enum(
            VerdictRating,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    justification = Column(Text, nullable=False)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    replaced_by_id = Column(Integer, ForeignKey("verdict.id"), nullable=True)

    statement = relationship("Statement", back_populates="verdicts")
    sources = relationship(
        "VerdictSource", back_populates="verdict", cascade="all, delete-orphan"
    )
    responses = relationship(
        "Response", back_populates="verdict", cascade="all, delete-orphan"
    )
    replaced_by = relationship(
        "Verdict", remote_side=[id], foreign_keys=[replaced_by_id]
    )


class VerdictSource(Base):
    __tablename__ = "verdict_source"

    id = Column(Integer, primary_key=True)
    verdict_id = Column(Integer, ForeignKey("verdict.id"), nullable=False)
    url = Column(String(2000), nullable=False)
    title = Column(String(500), nullable=True)

    verdict = relationship("Verdict", back_populates="sources")


class Response(Base):
    __tablename__ = "response"

    id = Column(Integer, primary_key=True)
    verdict_id = Column(Integer, ForeignKey("verdict.id"), nullable=False)
    author_name = Column(String(200), nullable=False)
    author_capacity = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    verdict = relationship("Verdict", back_populates="responses")
