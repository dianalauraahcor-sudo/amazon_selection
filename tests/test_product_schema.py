"""Test cases for the Product schema validation gate.

Run from the project root:
    py -X utf8 tests/test_product_schema.py

No pytest dependency — uses plain assertions and a tiny test harness so it
runs anywhere with stdlib + pydantic + openpyxl (already in requirements).

Coverage:
  - Section A: Product schema unit tests (17 cases)
  - Section B: Parser integration against the real xlsx file (5 cases)
  - Section C: Parser failure paths via _COLUMN_MAP monkey-patch (3 cases)
"""

import os
import sys
import traceback
from typing import Callable, List, Tuple

# Make sure we can import the project from the repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pydantic import ValidationError  # noqa: E402

from backend.excel_parser.schemas import Product  # noqa: E402
from backend.excel_parser import parser as parser_mod  # noqa: E402
from backend.excel_parser.parser import parse_all_files  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────────────────────

REAL_XLSX = r"C:\Users\18782\Desktop\新建文件夹 (4)\LED工作灯-类目分析V3.xlsx"

# 10 user-supplied target ASINs from the project requirements
TARGET_ASINS = [
    "B0CYWSWZ71", "B0GJB7M62C", "B0B6BCSKBV", "B0DHZVRHBV", "B0DM4M71X6",
    "B0FKRKLGY7", "B0D9L6L36B", "B0C6DCVDND", "B0DYY6J1H9", "B09VSV5FF3",
]

# Ground truth values pulled from the real xlsx (BSR竞品数据 sheet)
EXPECTED = {
    "B0CYWSWZ71": {"brand": "Zetunlo", "price": 59.55, "rating": 4.6,
                   "ratings_total": 779, "monthly_sales": 2790,
                   "title_starts": "Zetunlo 21000Lumen LED Work Lights"},
    "B0GJB7M62C": {"brand": "LIVOWALNY", "price": 29.99, "rating": 4.6,
                   "ratings_total": 22, "monthly_sales": 1200,
                   "title_starts": "LIVOWALNY LED Work Light Compatible"},
    "B0B6BCSKBV": {"brand": "Tresda", "price": 36.99, "rating": 4.4,
                   "ratings_total": 1188, "monthly_sales": 2128,
                   "title_starts": "Tresda 30W Rechargeable Work Light"},
    "B00SKOCRCW": {"brand": "DEWALT", "price": 65, "rating": 4.8,
                   "ratings_total": 20625, "monthly_sales": 4200,
                   "title_starts": "DEWALT 20V MAX LED Work Light"},
    "B07G9X19G1": {"brand": "Coquimbo", "price": 17.99, "rating": 4.3,
                   "ratings_total": 23905, "monthly_sales": 6800,
                   "title_starts": "Coquimbo Tool Fathers Day"},
}

# ──────────────────────────────────────────────────────────────────────────
# Tiny test harness — runs every function whose name starts with "test_"
# ──────────────────────────────────────────────────────────────────────────

_TESTS: List[Tuple[str, Callable]] = []


def case(fn: Callable) -> Callable:
    """Decorator to register a test case."""
    _TESTS.append((fn.__name__, fn))
    return fn


def assert_validation_error(callable_, *, field: str = None, msg_substr: str = None):
    """Assert that calling `callable_()` raises pydantic.ValidationError.

    Optionally assert the error mentions a specific field or contains a substring.
    """
    try:
        callable_()
    except ValidationError as e:
        if field is not None:
            locs = [err["loc"] for err in e.errors()]
            assert any(field in tuple(loc) for loc in locs), (
                f"expected error on field {field!r}, got locs={locs}"
            )
        if msg_substr is not None:
            assert msg_substr in str(e), f"expected substring {msg_substr!r} in error"
        return e
    raise AssertionError(f"expected ValidationError but call succeeded: {callable_}")


# ══════════════════════════════════════════════════════════════════════════
# Section A — Product schema unit tests (17 cases)
# ══════════════════════════════════════════════════════════════════════════

@case
def test_a01_happy_minimal():
    """Only the two required fields — should validate."""
    p = Product.model_validate({"asin": "B0CYWSWZ71", "title": "Zetunlo LED"})
    assert p.asin == "B0CYWSWZ71"
    assert p.title == "Zetunlo LED"
    assert p.brand is None
    assert p.price is None


@case
def test_a02_happy_full():
    """All fields populated — should validate cleanly."""
    p = Product.model_validate({
        "asin": "B0CYWSWZ71",
        "title": "Zetunlo 21000Lumen LED Work Lights with Stand",
        "brand": "Zetunlo",
        "price": 59.55,
        "rating": 4.6,
        "ratings_total": 779,
        "monthly_sales": 2790,
        "monthly_revenue": 166144.5,
        "title_cn": "Zetunlo 21000流明 LED 工作灯",
        "bullet_points": "21000 lumen, 3 head, 16ft cord",
        "main_bsr": 9,
        "sub_bsr": 1,
        "main_category": "Tools & Home Improvement",
        "sub_category": "Job Site Lighting",
        "category_path": "Tools > Lighting > Work Lights",
        "fulfillment": "FBA",
        "seller_location": "China",
        "launch_date": "2024-01-15",
        "margin": 0.35,
        "fba_fee": 8.5,
    })
    assert p.brand == "Zetunlo"
    assert p.main_bsr == 9
    assert p.sub_bsr == 1


@case
def test_a03_happy_realistic_dewalt():
    """High-volume real-world data point — DEWALT, 20625 reviews."""
    p = Product.model_validate({
        "asin": "B00SKOCRCW",
        "title": "DEWALT 20V MAX LED Work Light, Handheld Spotlight",
        "brand": "DEWALT",
        "price": 65,
        "rating": 4.8,
        "ratings_total": 20625,
        "monthly_sales": 4200,
    })
    assert p.ratings_total == 20625
    assert p.price == 65.0


@case
def test_a04_fail_missing_title():
    """Required field title missing — must fail."""
    assert_validation_error(
        lambda: Product.model_validate({"asin": "B0CYWSWZ71"}),
        field="title",
    )


@case
def test_a05_fail_missing_asin():
    """Required field asin missing — must fail."""
    assert_validation_error(
        lambda: Product.model_validate({"title": "X"}),
        field="asin",
    )


@case
def test_a06_fail_empty_title():
    """Empty string for title violates min_length=1."""
    assert_validation_error(
        lambda: Product.model_validate({"asin": "B0CYWSWZ71", "title": ""}),
        field="title",
    )


@case
def test_a07_fail_asin_too_short():
    """ASIN must be at least 10 chars."""
    assert_validation_error(
        lambda: Product.model_validate({"asin": "B0CYW", "title": "X"}),
        field="asin",
    )


@case
def test_a08_fail_rating_above_5():
    """Rating > 5 is impossible."""
    assert_validation_error(
        lambda: Product.model_validate(
            {"asin": "B0CYWSWZ71", "title": "X", "rating": 5.5}
        ),
        field="rating",
    )


@case
def test_a09_fail_rating_negative():
    """Negative rating is impossible."""
    assert_validation_error(
        lambda: Product.model_validate(
            {"asin": "B0CYWSWZ71", "title": "X", "rating": -0.5}
        ),
        field="rating",
    )


@case
def test_a10_fail_price_negative():
    """Negative price is impossible (ge=0)."""
    assert_validation_error(
        lambda: Product.model_validate(
            {"asin": "B0CYWSWZ71", "title": "X", "price": -10.0}
        ),
        field="price",
    )


@case
def test_a11_coerce_ratings_total_float_to_int():
    """_safe_float in parser returns float; schema must coerce to int."""
    p = Product.model_validate(
        {"asin": "B0CYWSWZ71", "title": "X", "ratings_total": 779.0}
    )
    assert p.ratings_total == 779
    assert isinstance(p.ratings_total, int)


@case
def test_a12_coerce_monthly_sales_float_to_int():
    p = Product.model_validate(
        {"asin": "B0CYWSWZ71", "title": "X", "monthly_sales": 2790.0}
    )
    assert p.monthly_sales == 2790
    assert isinstance(p.monthly_sales, int)


@case
def test_a13_coerce_main_bsr_string_to_int():
    """A stringified BSR like '#2052' would fail; bare numeric string OK."""
    p = Product.model_validate(
        {"asin": "B0CYWSWZ71", "title": "X", "main_bsr": "9"}
    )
    assert p.main_bsr == 9


@case
def test_a14_coerce_truncates_floats_with_fraction():
    """A non-integer float should be truncated, not rejected."""
    p = Product.model_validate(
        {"asin": "B0CYWSWZ71", "title": "X", "monthly_sales": 2790.7}
    )
    # int(float(2790.7)) → 2790
    assert p.monthly_sales == 2790


@case
def test_a15_extras_tolerated():
    """Unknown columns like 产品类型 must not raise."""
    p = Product.model_validate({
        "asin": "B0CYWSWZ71",
        "title": "X",
        "产品类型": "便携折叠工作灯",
        "供电方式": "充电",
        "亮度(LM)": "21000LM",
        "防水等级": "IP66",
        "未知中文列": "whatever",
    })
    # extras are ignored (extra="ignore"), not stored on the model
    assert p.title == "X"


@case
def test_a16_optional_fields_default_to_none():
    """Every optional field should default to None when omitted."""
    p = Product.model_validate({"asin": "B0CYWSWZ71", "title": "X"})
    for f in ("brand", "price", "rating", "ratings_total", "monthly_sales",
              "monthly_revenue", "title_cn", "bullet_points", "main_bsr",
              "sub_bsr", "main_category", "sub_category", "category_path",
              "fulfillment", "seller_location", "launch_date", "margin",
              "fba_fee"):
        assert getattr(p, f) is None, f"expected {f}=None"


@case
def test_a17_partial_optional_fields():
    """A realistic mid-quality record (some fields, not all)."""
    p = Product.model_validate({
        "asin": "B0CNMWSGCF",
        "title": "3000LM Rechargeable Work Light Magnetic",
        "brand": "--",                # placeholder brand
        "price": 22.99,
        "rating": 4.4,
        # ratings_total and monthly_sales intentionally absent
    })
    assert p.brand == "--"
    assert p.ratings_total is None
    assert p.monthly_sales is None


# ══════════════════════════════════════════════════════════════════════════
# Section B — Parser integration against the real xlsx file (5 cases)
# ══════════════════════════════════════════════════════════════════════════

@case
def test_b01_parse_real_xlsx_loads_40_products():
    """The real BSR sheet has 40 product rows; all should validate."""
    assert os.path.exists(REAL_XLSX), f"missing fixture file: {REAL_XLSX}"
    r = parse_all_files([REAL_XLSX])
    assert len(r["excel_data"]) == 40, f"expected 40, got {len(r['excel_data'])}"


@case
def test_b02_all_target_asins_present():
    """All 10 user-supplied target ASINs must parse."""
    r = parse_all_files([REAL_XLSX])
    missing = [a for a in TARGET_ASINS if a not in r["excel_data"]]
    assert not missing, f"missing target ASINs: {missing}"


@case
def test_b03_known_field_values_match_ground_truth():
    """Spot-check 5 ASINs against hand-verified ground truth."""
    r = parse_all_files([REAL_XLSX])
    for asin, expected in EXPECTED.items():
        p = r["excel_data"].get(asin)
        assert p is not None, f"{asin} not parsed"
        assert p["brand"] == expected["brand"], (
            f"{asin}: brand={p['brand']!r} expected {expected['brand']!r}"
        )
        assert abs(p["price"] - expected["price"]) < 0.01, (
            f"{asin}: price={p['price']} expected {expected['price']}"
        )
        assert p["rating"] == expected["rating"]
        assert p["ratings_total"] == expected["ratings_total"]
        assert p["monthly_sales"] == expected["monthly_sales"]
        assert p["title"].startswith(expected["title_starts"]), (
            f"{asin}: title={p['title'][:60]!r} expected to start with "
            f"{expected['title_starts']!r}"
        )


@case
def test_b04_parser_output_remains_dict_not_pydantic_instance():
    """Regression: schema is a validation gate, not a runtime type.
    The parser must still return Dict[str, dict] (not Dict[str, Product]),
    so downstream node code that uses raw .get(\"产品类型\") still works."""
    r = parse_all_files([REAL_XLSX])
    p = r["excel_data"]["B0CYWSWZ71"]
    assert isinstance(p, dict), f"expected dict, got {type(p).__name__}"
    assert not isinstance(p, Product)
    # ratings_total is still float in the dict (the schema's int coercion
    # only affected the discarded Product instance, not row_dict)
    assert isinstance(p["ratings_total"], float), (
        f"regression: ratings_total in dict should still be float, "
        f"got {type(p['ratings_total']).__name__}"
    )


@case
def test_b05_unmapped_chinese_keys_preserved_in_dict():
    """Regression: raw Chinese column names that don't map to a normalized
    key (e.g. 产品类型) should still be present in the dict so that
    competition.py:135 can read raw.get('产品类型')."""
    r = parse_all_files([REAL_XLSX])
    p = r["excel_data"]["B0CYWSWZ71"]
    # 产品类型 has no entry in _COLUMN_MAP, so _normalise_header falls back
    # to the raw key — it should still be in the row_dict.
    assert "产品类型" in p, (
        f"expected raw '产品类型' key in dict; keys={list(p.keys())[:25]}"
    )


# ══════════════════════════════════════════════════════════════════════════
# Section C — Parser failure paths via _COLUMN_MAP monkey-patch (3 cases)
# ══════════════════════════════════════════════════════════════════════════

class _patch_column_map:
    """Context manager that removes a key from _COLUMN_MAP and restores it."""
    def __init__(self, key: str):
        self.key = key
        self.removed = None

    def __enter__(self):
        self.removed = parser_mod._COLUMN_MAP.pop(self.key, None)
        # rebuild the lowercase cache so the key is fully gone
        parser_mod._COL_LOWER = {
            k.lower(): v for k, v in parser_mod._COLUMN_MAP.items()
        }
        return self

    def __exit__(self, *exc):
        if self.removed is not None:
            parser_mod._COLUMN_MAP[self.key] = self.removed
            parser_mod._COL_LOWER = {
                k.lower(): v for k, v in parser_mod._COLUMN_MAP.items()
            }


@case
def test_c01_raises_when_title_alias_missing():
    """Removing the 产品标题（完整）→title alias must trigger the targeted error."""
    with _patch_column_map("产品标题（完整）"):
        try:
            parse_all_files([REAL_XLSX])
        except ValueError as e:
            msg = str(e)
            assert "未能识别标题列" in msg, f"missing guidance text: {msg}"
            assert "BSR竞品数据" in msg, f"missing sheet name: {msg}"
            assert "产品标题（完整）" in msg, f"missing alias suggestion: {msg}"
            return
        raise AssertionError("expected ValueError, parser succeeded")


@case
def test_c02_raises_when_asin_alias_missing():
    """Removing ASIN→asin alias must trigger an analogous error."""
    with _patch_column_map("ASIN"):
        try:
            parse_all_files([REAL_XLSX])
        except ValueError as e:
            msg = str(e)
            # The sheet may not be classified as a product sheet at all
            # without ASIN, so the error could come from either the new
            # gate or the existing "no product data" check in jobs.py.
            # Accept either path as long as something failed loudly.
            assert ("未能识别 ASIN 列" in msg) or ("未识别到任何产品" in msg) \
                or ("BSR竞品数据" in msg), f"unexpected error: {msg}"
            return
        raise AssertionError("expected ValueError, parser succeeded")


@case
def test_c03_validation_error_message_format():
    """Verify the per-row pydantic error format is human-readable.
    Construct an in-memory invalid product directly via the schema."""
    try:
        Product.model_validate({
            "asin": "B0CYWSWZ71",
            "title": "X",
            "rating": 99,           # out of range
            "price": -5,            # negative
            "ratings_total": 779.0,  # this one is fine
        })
    except ValidationError as e:
        errs = e.errors()
        loc_set = {tuple(err["loc"]) for err in errs}
        assert ("rating",) in loc_set
        assert ("price",) in loc_set
        # The combined error message should be parseable into a useful summary
        msg = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in errs
        )
        assert "rating" in msg and "price" in msg
        return
    raise AssertionError("expected ValidationError")


# ══════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"Running {len(_TESTS)} tests...\n")
    passed = 0
    failed = []
    for name, fn in _TESTS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}")
            print(f"        {type(e).__name__}: {e}")
            tb = traceback.format_exc().splitlines()
            for line in tb[-4:-1]:
                print(f"        {line}")
            failed.append(name)
    print()
    print(f"Results: {passed}/{len(_TESTS)} passed")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
