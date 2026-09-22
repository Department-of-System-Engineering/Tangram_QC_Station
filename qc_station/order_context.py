"""Validated order input boundary; future database/API adapter supplies this object."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class OrderContext:
    order_id: int
    product_instance_id: int
    expected_variant: str

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict) or set(payload) != {"order_id", "product_instance_id", "expected_variant"}:
            raise ValueError("Order context requires order_id, product_instance_id, expected_variant")
        for key in ("order_id", "product_instance_id"):
            if type(payload[key]) is not int or payload[key] <= 0:
                raise ValueError(f"{key} must be a positive integer")
        if payload["expected_variant"] not in ("A", "B", "C", "D"):
            raise ValueError("Order variant must be A, B, C or D")
        return cls(**payload)


def load_order_context(path):
    return OrderContext.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
