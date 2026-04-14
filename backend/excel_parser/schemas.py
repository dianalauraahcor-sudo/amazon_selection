"""Internal canonical schemas for the excel_parser package.

These models act as parse-time validation gates — `excel_data` still flows
through the rest of the system as `Dict[str, dict]`, but each parsed row is
validated against `Product` before being accepted into the dict. The presence
of this contract makes column-mapping failures fail loudly at the parser
boundary instead of silently producing empty fields downstream (e.g. an empty
"标题" column in the docx report).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Product(BaseModel):
    """Canonical product record. Used purely as a parse-time validation gate."""

    model_config = ConfigDict(extra="ignore")  # tolerate unknown columns (e.g. raw 产品类型)

    # ── REQUIRED — parser must populate these or validation fails ──
    asin: str = Field(..., min_length=10, max_length=20)
    title: str = Field(..., min_length=1)

    # ── OPTIONAL — None default; downstream consumers already handle None ──
    brand: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    ratings_total: Optional[int] = Field(None, ge=0)
    monthly_sales: Optional[int] = Field(None, ge=0)
    monthly_revenue: Optional[float] = None
    title_cn: Optional[str] = None
    bullet_points: Optional[str] = None
    bullet_points_cn: Optional[str] = None
    main_bsr: Optional[int] = None
    sub_bsr: Optional[int] = None
    main_category: Optional[str] = None
    sub_category: Optional[str] = None
    category_path: Optional[str] = None
    fulfillment: Optional[str] = None
    seller_location: Optional[str] = None
    launch_date: Optional[str] = None
    margin: Optional[float] = None
    fba_fee: Optional[float] = None
    # BSR竞品数据 sheet 扩展字段
    product_type: Optional[str] = None       # 产品类型
    power_source: Optional[str] = None       # 供电方式
    brightness: Optional[str] = None         # 亮度(LM)
    waterproof: Optional[str] = None         # 防水等级
    weight: Optional[str] = None             # 重量
    seller_info: Optional[str] = None        # 卖家信息
    product_subtype: Optional[str] = None    # 类型细分
    color_temp: Optional[str] = None         # 色温(K)
    battery_spec: Optional[str] = None       # 电池容量/电压

    # _safe_float in parser.py returns float; pydantic v2 won't auto-coerce
    # float→int, so coerce here for the integer-typed counts.
    @field_validator(
        "ratings_total", "monthly_sales", "main_bsr", "sub_bsr", mode="before"
    )
    @classmethod
    def _to_int(cls, v):
        if v is None:
            return None
        s = str(v).replace(",", "").replace("#", "").replace("—", "").replace("--", "").strip()
        if not s:
            return None
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return None
