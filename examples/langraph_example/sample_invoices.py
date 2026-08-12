# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Fake invoice fixtures and deterministic mock extraction (no OCR / LLM)."""

from __future__ import annotations

from typing import Any

# Raw text blobs the graph "ingests"; worker parses them deterministically.
SAMPLES: dict[str, dict[str, Any]] = {
    "inv-1001": {
        "raw_text": (
            "INVOICE\n"
            "Vendor: Acme Supplies Ltd\n"
            "Date: 2026-03-15\n"
            "Currency: GBP\n"
            "Line: Widget A x2 @ 12.50 = 25.00\n"
            "Line: Widget B x1 @ 7.50 = 7.50\n"
            "Total: 32.50\n"
        ),
        "expected": {
            "vendor": "Acme Supplies Ltd",
            "invoice_date": "2026-03-15",
            "total": 32.50,
            "currency": "GBP",
            "line_items": [
                {"description": "Widget A", "qty": 2, "unit_price": 12.50, "amount": 25.00},
                {"description": "Widget B", "qty": 1, "unit_price": 7.50, "amount": 7.50},
            ],
        },
    },
    "inv-1002": {
        "raw_text": (
            "RECEIPT\n"
            "Vendor: CloudBits Inc\n"
            "Date: 2026-04-01\n"
            "Currency: USD\n"
            "Line: API credits x1000 @ 0.01 = 10.00\n"
            "Total: 10.00\n"
        ),
        "expected": {
            "vendor": "CloudBits Inc",
            "invoice_date": "2026-04-01",
            "total": 10.00,
            "currency": "USD",
            "line_items": [
                {
                    "description": "API credits",
                    "qty": 1000,
                    "unit_price": 0.01,
                    "amount": 10.00,
                },
            ],
        },
    },
    "inv-1003": {
        "raw_text": (
            "INVOICE\n"
            "Vendor: Office Hub\n"
            "Date: 2026-05-20\n"
            "Currency: EUR\n"
            "Line: Desk chair x1 @ 199.00 = 199.00\n"
            "Line: Monitor arm x2 @ 45.00 = 90.00\n"
            "Total: 289.00\n"
        ),
        "expected": {
            "vendor": "Office Hub",
            "invoice_date": "2026-05-20",
            "total": 289.00,
            "currency": "EUR",
            "line_items": [
                {
                    "description": "Desk chair",
                    "qty": 1,
                    "unit_price": 199.00,
                    "amount": 199.00,
                },
                {
                    "description": "Monitor arm",
                    "qty": 2,
                    "unit_price": 45.00,
                    "amount": 90.00,
                },
            ],
        },
    },
}

DEFAULT_DOCUMENT_ID = "inv-1001"


def get_sample(document_id: str = DEFAULT_DOCUMENT_ID) -> dict[str, Any]:
    if document_id not in SAMPLES:
        raise KeyError(f"unknown sample document_id: {document_id!r}")
    return SAMPLES[document_id]


def extract_fields(document_id: str, raw_text: str, doc_type: str) -> dict[str, Any]:
    """Deterministic mock OCR/extract. Prefer sample table; else parse lines."""
    _ = doc_type  # reserved for future type-specific extractors
    sample = SAMPLES.get(document_id)
    if sample is not None and sample["raw_text"] == raw_text:
        return dict(sample["expected"])
    return _parse_raw_text(raw_text)


def _parse_raw_text(raw_text: str) -> dict[str, Any]:
    vendor = ""
    invoice_date = ""
    currency = "USD"
    total = 0.0
    line_items: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("vendor:"):
            vendor = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("date:"):
            invoice_date = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("currency:"):
            currency = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("total:"):
            total = float(stripped.split(":", 1)[1].strip())
        elif stripped.lower().startswith("line:"):
            # "Widget A x2 @ 12.50 = 25.00"
            body = stripped.split(":", 1)[1].strip()
            try:
                left, amount_s = body.rsplit("=", 1)
                amount = float(amount_s.strip())
                desc_part, price_s = left.rsplit("@", 1)
                unit_price = float(price_s.strip())
                desc, qty_s = desc_part.rsplit("x", 1)
                qty = int(qty_s.strip())
                line_items.append(
                    {
                        "description": desc.strip(),
                        "qty": qty,
                        "unit_price": unit_price,
                        "amount": amount,
                    }
                )
            except (ValueError, IndexError):
                continue
    return {
        "vendor": vendor,
        "invoice_date": invoice_date,
        "total": total,
        "currency": currency,
        "line_items": line_items,
    }
