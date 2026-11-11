"""Adapt the verified product and washer source files to the shared seed loader."""

import json
from pathlib import Path

from backend.app.ai.catalog import load_catalog

VERIFIED_DIR = Path(__file__).parent / "verified"


def verified_seed() -> dict:
    products = []
    for entry in load_catalog():
        product = entry.product
        source_url = str(product.source_url)
        products.append({
            "product_key": product.id,
            "brand": product.brand,
            "product_name": product.name,
            "official_url": source_url,
            "catalog_details": {
                "color": product.color,
                "product_code": product.product_code,
                **entry.model_dump(mode="json", exclude={"product", "care"}),
            },
            "source_type": "official_product_information",
            "verification_status": "confirmed",
            "care_instructions": [
                {
                    "field_name": name,
                    "value_text": (
                        reading["value"] if isinstance(reading["value"], str)
                        else json.dumps(reading["value"])
                    ),
                    "evidence": reading["evidence"],
                    "source_type": "official_product_information",
                    "source_url": source_url,
                    "verification_status": "confirmed",
                }
                for name, reading in entry.care.model_dump(exclude_none=True).items()
            ],
        })

    washers = json.loads((VERIFIED_DIR / "washers.json").read_text(encoding="utf-8"))
    models = []
    for washer in washers:
        models.append({
            "machine_key": washer["id"],
            "machine_type": "washer",
            "manufacturer": washer["manufacturer"],
            "model_name": washer["model_number"],
            "source_url": washer["source_url"],
            "verification_status": "confirmed",
            "verified_scope": f'{washer["market"]} 모델 · 공식 설명서의 기본 온도와 탈수 단계',
            "courses": [
                {
                    "course_key": course["id"],
                    "name": course["name_ko"],
                    "description": " ".join(setting["evidence"] for setting in course["verified_settings"]),
                    "settings": [
                        {
                            "temperature_celsius": setting["wash_temperature_c"],
                            "temperature_setting": setting["wash_temperature_setting"],
                            "spin_level": setting["spin_setting"],
                            "spin_rpm": setting["spin_rpm"],
                            "is_default": setting["is_default"],
                            "manual_page": setting["manual_page"],
                            "evidence": setting["evidence"],
                            "source_url": f'{washer["manual_url"]}#page={setting["manual_page"]}',
                            "verification_status": "confirmed",
                        }
                        for setting in course["verified_settings"]
                    ],
                }
                for course in washer["cycles"]
            ],
        })
    return {"products": products, "machine_models": models}
