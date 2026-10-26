# db.py — SQLAlchemy models and database helpers for SDS Retrieval Agent

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

DB_PATH = os.path.join(os.path.dirname(__file__), "sds_agent.db")
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class Product(Base):
    """One row from the uploaded Excel sheet."""
    __tablename__ = "products"
    __allow_unmapped__ = True

    id            = Column(Integer, primary_key=True, autoincrement=True)
    supplier      = Column(String(128), nullable=False, index=True)
    product_name  = Column(String(512), nullable=False)
    part_number   = Column(String(256), nullable=True)
    cas_number    = Column(String(64),  nullable=True)
    language      = Column(String(8),   nullable=True, default="EN")
    jurisdiction  = Column(String(32),  nullable=True, default="US")
    notes         = Column(Text,        nullable=True)
    created_at    = Column(DateTime,    default=datetime.utcnow)

    results: list[SdsResult] = relationship(
        "SdsResult", back_populates="product", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":           self.id,
            "supplier":     self.supplier,
            "product_name": self.product_name,
            "part_number":  self.part_number,
            "cas_number":   self.cas_number,
            "language":     self.language,
            "jurisdiction": self.jurisdiction,
            "notes":        self.notes,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }


class SdsResult(Base):
    """One retrieved SDS for a product."""
    __tablename__ = "sds_results"
    __allow_unmapped__ = True

    id           = Column(Integer, primary_key=True, autoincrement=True)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    supplier     = Column(String(128), nullable=True)
    url          = Column(Text,        nullable=True)
    filename     = Column(String(512), nullable=True)
    language     = Column(String(8),   nullable=True)
    jurisdiction = Column(String(32),  nullable=True)
    date_issued  = Column(String(64),  nullable=True)
    status       = Column(String(32),  nullable=True, default="pending")   # pending|found|not_found|error
    error_msg    = Column(Text,        nullable=True)
    retrieved_at = Column(DateTime,    default=datetime.utcnow)

    product: Product = relationship("Product", back_populates="results")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":           self.id,
            "product_id":   self.product_id,
            "supplier":     self.supplier,
            "url":          self.url,
            "filename":     self.filename,
            "language":     self.language,
            "jurisdiction": self.jurisdiction,
            "date_issued":  self.date_issued,
            "status":       self.status,
            "error_msg":    self.error_msg,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


_COLUMN_MAP = {
    # normalised key → possible Excel header variants
    "supplier": [
        "supplier", "supplier name", "supplier_name", "company", "company name", 
        "company_name", "vendor", "vendor name", "vendor_name", "manufacturer", 
        "manufacturer name", "brand", "make", "source"
    ],
    "product_name": [
        "product name", "product_name", "product", "chemical name", "chemical_name", 
        "chemical", "name", "substance", "item description", "material", 
        "description", "item name", "material name", "reagent", "compound"
    ],
    "part_number": [
        "part number", "part_number", "part no", "part no.", "part #", "part_no", 
        "part#", "part", "catalog number", "catalog no", "catalog no.", "catalog_number", 
        "catalog_no", "catalog #", "catalog#", "cat no", "cat no.", "cat_no", "cat#", 
        "cat #", "catalogue number", "catalogue no", "catalogue no.", "catalogue_number", 
        "catalogue_no", "catalogue #", "catalogue#", "product number", "product no", 
        "product no.", "product_number", "product_no", "product #", "product#", 
        "item number", "item no", "item no.", "item_number", "item_no", "item #", 
        "item#", "sku", "code", "material number", "material no", "article number", 
        "article no", "order no", "order number", "ref", "ref no", "reference"
    ],
    "cas_number": [
        "cas", "cas number", "cas no", "cas no.", "cas_number", "cas_no", "cas #", 
        "cas#", "cas-number", "cas registry number", "cas rn"
    ],
    "language": [
        "language", "lang", "sds language", "sds_language", "doc language"
    ],
    "jurisdiction": [
        "jurisdiction", "country", "region", "sds jurisdiction", "regulatory region", "market"
    ],
    "notes": [
        "notes", "note", "comment", "remarks", "memo"
    ],
}


def _clean_str(val: Any) -> str | None:
    """Robust string cleaner that handles floats, scientific notations, nan, etc."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "<na>", "undefined", "n/a", "--", "-"):
        return None
    # If float ending in .0 like 12345.0 for catalog number, convert to integer string
    if re.match(r'^-?\d+\.0+$', s):
        s = s.split('.')[0]
    return s


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map arbitrary Excel headers → canonical column names using flexible fuzzy mapping."""
    rename = {}
    cleaned_col_map = {}
    for original_col in df.columns:
        # Lowercase and strip special characters
        norm_key = re.sub(r'[\s_\-\.\#\:\(\)\/\\]+', ' ', str(original_col).lower()).strip()
        cleaned_col_map[original_col] = norm_key

    for original_col, norm_key in cleaned_col_map.items():
        matched = False
        for canon, variants in _COLUMN_MAP.items():
            for v in variants:
                clean_variant = re.sub(r'[\s_\-\.\#\:\(\)\/\\]+', ' ', v.lower()).strip()
                if norm_key == clean_variant or norm_key.replace(" ", "") == clean_variant.replace(" ", ""):
                    rename[original_col] = canon
                    matched = True
                    break
            if matched:
                break
                
        # Secondary fallback: partial match
        if not matched:
            if any(k in norm_key for k in ["part", "catalog", "catalogue", "cat no", "item no", "sku", "code"]):
                rename[original_col] = "part_number"
            elif any(k in norm_key for k in ["cas"]):
                rename[original_col] = "cas_number"
            elif any(k in norm_key for k in ["supplier", "vendor", "company", "manufacturer", "brand"]):
                rename[original_col] = "supplier"
            elif any(k in norm_key for k in ["product", "chemical", "substance", "material", "item"]):
                rename[original_col] = "product_name"
            elif any(k in norm_key for k in ["lang"]):
                rename[original_col] = "language"
            elif any(k in norm_key for k in ["juris", "country", "region"]):
                rename[original_col] = "jurisdiction"

    return df.rename(columns=rename)


def insert_products_from_df(df: pd.DataFrame, session: Session | None = None) -> list[int]:
    """
    Parse a DataFrame from an uploaded Excel, insert rows, return list of new IDs.
    Accepts rows containing ANY identifiable field (Product Name, Part Number, CAS, or Supplier).
    """
    df = _normalise_columns(df)
    close = session is None
    if close:
        session = get_session()
    ids: list[int] = []
    try:
        for _, row in df.iterrows():
            supplier = _clean_str(row.get("supplier"))
            product_name = _clean_str(row.get("product_name"))
            part_no = _clean_str(row.get("part_number"))
            cas_no = _clean_str(row.get("cas_number"))
            lang = (_clean_str(row.get("language")) or "EN").upper()
            juris = (_clean_str(row.get("jurisdiction")) or "US").upper()
            notes = _clean_str(row.get("notes"))

            # If row is completely empty across all columns, skip it
            if not any([supplier, product_name, part_no, cas_no]):
                continue

            # Fallbacks:
            # 1. If product name is missing, use Part Number or CAS Number
            if not product_name:
                product_name = part_no or cas_no or "Unknown Chemical"

            # 2. If supplier is missing, default to Generic
            if not supplier:
                supplier = "Generic"

            p = Product(
                supplier=supplier,
                product_name=product_name,
                part_number=part_no,
                cas_number=cas_no,
                language=lang,
                jurisdiction=juris,
                notes=notes,
            )
            session.add(p)
            session.flush()
            ids.append(p.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if close:
            session.close()
    return ids


def get_products(session: Session | None = None) -> list[dict[str, Any]]:
    close = session is None
    if close:
        session = get_session()
    try:
        products = session.query(Product).order_by(Product.created_at.desc()).all()
        return [p.to_dict() for p in products]
    finally:
        if close:
            session.close()


def get_product(product_id: int, session: Session | None = None) -> dict[str, Any] | None:
    close = session is None
    if close:
        session = get_session()
    try:
        p = session.get(Product, product_id)
        return p.to_dict() if p else None
    finally:
        if close:
            session.close()


def save_sds_result(
    product_id: int,
    supplier: str | None = None,
    url: str | None = None,
    filename: str | None = None,
    language: str | None = None,
    jurisdiction: str | None = None,
    date_issued: str | None = None,
    status: str = "pending",
    error_msg: str | None = None,
    session: Session | None = None,
) -> int:
    """Insert or update SDS result for a product; return result ID."""
    close = session is None
    if close:
        session = get_session()
    try:
        existing = (
            session.query(SdsResult)
            .filter_by(product_id=product_id)
            .first()
        )
        if existing:
            existing.supplier     = supplier
            existing.url          = url
            existing.filename     = filename
            existing.language     = language
            existing.jurisdiction = jurisdiction
            existing.date_issued  = date_issued
            existing.status       = status
            existing.error_msg    = error_msg
            existing.retrieved_at = datetime.now(timezone.utc)
            session.commit()
            return existing.id
        result = SdsResult(
            product_id=product_id,
            supplier=supplier,
            url=url,
            filename=filename,
            language=language,
            jurisdiction=jurisdiction,
            date_issued=date_issued,
            status=status,
            error_msg=error_msg,
        )
        session.add(result)
        session.commit()
        session.refresh(result)
        return result.id
    except Exception:
        session.rollback()
        raise
    finally:
        if close:
            session.close()


def get_results(product_id: int | None = None) -> list[dict[str, Any]]:
    session = get_session()
    try:
        q = session.query(SdsResult)
        if product_id is not None:
            q = q.filter_by(product_id=product_id)
        return [r.to_dict() for r in q.order_by(SdsResult.retrieved_at.desc()).all()]
    finally:
        session.close()


def get_result_by_id(result_id: int) -> SdsResult | None:
    session = get_session()
    try:
        return session.get(SdsResult, result_id)
    finally:
        session.close()


# Auto-init on import
init_db()
