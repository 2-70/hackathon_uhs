"""Read the shared database's verified products for the analysis router."""

import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from backend.app.ai.catalog import CatalogProduct
from backend.app.api.deps import DbSession
from backend.app.db.models import Product

logger = logging.getLogger(__name__)
SCALAR_FIELDS = {"max_wash_temperature_c", "tumble_dry_allowed", "dry_in_shade"}


def get_db_catalog(db: DbSession) -> list[CatalogProduct] | None:
    try:
        rows = db.scalars(
            select(Product)
            .options(selectinload(Product.care_instructions))
            .where(
                Product.verification_status == "confirmed",
                Product.source_type == "official_product_information",
            )
            .order_by(Product.product_key)
        )
        entries = []
        for row in rows:
            if not row.catalog_details or not row.official_url:
                continue
            details = dict(row.catalog_details)
            product = {
                "id": row.product_key, "brand": row.brand, "name": row.product_name,
                "source_url": row.official_url, "color": details.pop("color"),
                "product_code": details.pop("product_code", None),
            }
            care = {}
            for field in row.care_instructions:
                if (
                    field.verification_status != "confirmed"
                    or field.source_type != "official_product_information"
                    or not field.evidence
                ):
                    continue
                value = field.value_text
                if field.field_name in SCALAR_FIELDS:
                    value = json.loads(value)
                care[field.field_name] = {"value": value, "evidence": field.evidence}
            entries.append(CatalogProduct.model_validate({**details, "product": product, "care": care}))
        return entries
    except (SQLAlchemyError, ValidationError, ValueError, KeyError) as error:
        logger.warning("Verified catalog unavailable: %s", type(error).__name__)
        return None
    finally:
        # Release the read transaction before an upload waits for Gemini.
        db.rollback()
