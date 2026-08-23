from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProductStatus(str, Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


# ==========================================================
# Product
# ==========================================================

class ProductRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    specification: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=255)
    gender: Optional[str] = Field(None, max_length=20)
    base_price: Decimal = Field(..., ge=0, description="Base price in currency units")
    discount_percent: Decimal = Field(Decimal("0.00"), ge=0, le=100)
    discount_start: Optional[datetime] = None
    discount_end: Optional[datetime] = None
    is_sellable: bool = True
    status: ProductStatus = ProductStatus.draft


class ProductResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    specification: Optional[str]
    brand_id: Optional[int]
    gender_id: Optional[int]
    base_price: Decimal
    discount_percent: Decimal
    discount_start: Optional[datetime]
    discount_end: Optional[datetime]
    is_sellable: bool
    status: ProductStatus
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Product Categories
# ==========================================================

class ProductCategoryRequest(BaseModel):
    category_path: str = Field(..., min_length=1, description="e.g. Clothing > Men > Shirts")


class ProductCategoryResponse(BaseModel):
    product_id: int
    category_id: int


class ProductDetailCategory(BaseModel):
    id: int
    name: str


# ==========================================================
# Product Tags
# ==========================================================

class ProductTagRequest(BaseModel):
    tag: str = Field(..., min_length=1, max_length=100)


class ProductTagResponse(BaseModel):
    product_id: int
    tag_id: int


# ==========================================================
# Colors & Sizes (catalog-level option tables)
# ==========================================================

class ProductColorRequest(BaseModel):
    id: str = Field(..., description="temp client id, e.g. color_1")
    name: str = Field(..., min_length=1, max_length=60)
    hex: Optional[str] = Field(None, max_length=9, description="e.g. #E5484D")


class ProductColorResponse(BaseModel):
    id: int
    name: str
    hex: Optional[str] = None


class ProductSizeRequest(BaseModel):
    id: str = Field(..., description="temp client id, e.g. size_0")
    name: str = Field(..., min_length=1, max_length=30)


class ProductSizeResponse(BaseModel):
    id: int
    name: str


# ==========================================================
# Product Images
# ==========================================================

class ProductImageRequest(BaseModel):
    url: str = Field(..., max_length=500)
    alt_text: Optional[str] = Field(None, max_length=255)
    is_primary: bool = False
    sort_order: int = 0


class ProductImageResponse(BaseModel):
    id: int
    product_id: int
    url: str
    alt_text: Optional[str]
    is_primary: bool
    sort_order: int


# ==========================================================
# Product Variants
# ==========================================================

class ProductVariantRequest(BaseModel):
    id: str = Field(..., description="e.g. variant_1")
    sku: str = Field(..., min_length=1, max_length=100)
    color_id: Optional[str] = Field(None, description="temp client color id")
    size_id: Optional[str] = Field(None, description="temp client size id")
    price_override: Optional[Decimal] = Field(None, ge=0)
    stock_quantity: int = Field(0, ge=0)
    is_active: bool = True


class ProductVariantResponse(BaseModel):
    id: int
    product_id: int
    color_id: Optional[int] = None
    size_id: Optional[int] = None
    sku: str
    price_override: Optional[Decimal]
    stock_quantity: int
    is_active: bool
    created_at: datetime


# ==========================================================
# Variant Images
# ==========================================================

class VariantImageRequest(BaseModel):
    color_id: str = Field(..., description="temp client color id")
    url: str = Field(..., max_length=500)
    sort_order: int = 0


class VariantImageResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    color_id: int
    url: str
    sort_order: int


# ==========================================================
# Composite payload for saving a full product
# ==========================================================

class ProductPayload(BaseModel):
    product: ProductRequest
    product_categories: List[ProductCategoryRequest] = Field(default_factory=list)
    product_tags: List[ProductTagRequest] = Field(default_factory=list)
    product_images: List[ProductImageRequest] = Field(default_factory=list)
    product_colors: List[ProductColorRequest] = Field(default_factory=list)
    product_sizes: List[ProductSizeRequest] = Field(default_factory=list)
    product_variants: List[ProductVariantRequest] = Field(default_factory=list)
    variant_images: List[VariantImageRequest] = Field(default_factory=list)


class ProductPayloadResponse(BaseModel):
    product: ProductResponse
    product_categories: List[ProductCategoryResponse] = Field(default_factory=list)
    product_tags: List[ProductTagResponse] = Field(default_factory=list)
    product_images: List[ProductImageResponse] = Field(default_factory=list)
    product_colors: List[ProductColorResponse] = Field(default_factory=list)
    product_sizes: List[ProductSizeResponse] = Field(default_factory=list)
    product_variants: List[ProductVariantResponse] = Field(default_factory=list)
    variant_images: List[VariantImageResponse] = Field(default_factory=list)


# ==========================================================
# Product Detail (public page) - images sourced from variant_images
# ==========================================================

class ProductDetailImage(BaseModel):
    url: str
    alt_text: Optional[str] = None
    is_primary: bool = False
    sort_order: int = 0


class ProductDetailColor(BaseModel):
    id: int
    name: str
    hex: Optional[str] = None
    images: List[ProductDetailImage] = Field(default_factory=list)


class ProductAvailableColor(BaseModel):
    id: int
    name: str
    hex: Optional[str] = None
    image: Optional[str] = None


class ProductDetailSize(BaseModel):
    id: int
    name: str


class ProductDetailVariant(BaseModel):
    id: int
    color_id: Optional[int] = None
    size_id: Optional[int] = None
    sku: str
    price_override: Optional[Decimal]
    stock_quantity: int
    is_active: bool


class ProductDetailResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    specification: Optional[str]
    base_price: Decimal
    discount_percent: Decimal
    is_sellable: bool
    status: ProductStatus
    brand_name: Optional[str] = None
    gender_name: Optional[str] = None
    main_image: Optional[str] = None
    gallery_images: List[ProductDetailImage] = Field(default_factory=list)
    categories: List[ProductDetailCategory] = Field(default_factory=list)
    tags: List[ProductTagResponse] = Field(default_factory=list)
    colors: List[ProductDetailColor] = Field(default_factory=list)
    available_colors: List[ProductAvailableColor] = Field(default_factory=list)
    sizes: List[ProductDetailSize] = Field(default_factory=list)
    variants: List[ProductDetailVariant] = Field(default_factory=list)



class CatalogFilterOption(BaseModel):
    id: int
    name: str
    count: int
    hex: Optional[str] = None

class CatalogFiltersResponse(BaseModel):
    categories: List[CatalogFilterOption] = Field(default_factory=list)
    brands: List[CatalogFilterOption] = Field(default_factory=list)
    genders: List[CatalogFilterOption] = Field(default_factory=list)
    colors: List[CatalogFilterOption] = Field(default_factory=list)
    sizes: List[CatalogFilterOption] = Field(default_factory=list)
    price_range: dict = Field(default_factory=dict)

class CatalogProductResponse(BaseModel):
    id: int
    name: str
    slug: str
    base_price: float
    discount_percent: float
    sale_price: float
    original_price: float
    image_url: Optional[str] = None
    category_name: Optional[str] = None
    brand_name: Optional[str] = None
    gender_name: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    color_id: Optional[int] = None
    colors: List[dict] = Field(default_factory=list)

class CatalogProductsResponse(BaseModel):
    total: int
    products: List[CatalogProductResponse]