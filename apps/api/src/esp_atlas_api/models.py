"""Pydantic response/request models for the esp-atlas API.

Field names mirror the records esp_atlas_core.search/wizard already return —
this module only shapes them for HTTP, it adds no business logic.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

PartType = Literal["soc", "module", "board"]
BudgetTier = Literal["cheap", "medium", "expensive"]


class HealthResponse(BaseModel):
    status: str
    count: int


class SourceEntry(BaseModel):
    field: str
    url: str
    verified: str


class Record(BaseModel):
    id: str
    type: str
    name: str
    vendor_or_brand: str
    brand_name: str
    brand_url: Optional[str] = None
    wifi_standard: Optional[str] = None
    wifi_bands: Optional[str] = None
    ble_version: Optional[str] = None
    bt_classic: Optional[bool] = None
    ieee802154: Optional[bool] = None
    ieee802154_protocols: Optional[str] = None
    form_factor: Optional[str] = None
    price_tier: Optional[str] = None
    soc_ref: Optional[str] = None
    module_ref: Optional[str] = None
    usb_native: Optional[bool] = None
    flash_mb: Optional[float] = None
    psram_mb: Optional[float] = None
    path: str = Field(alias="_path")
    sources: list[SourceEntry] = []

    model_config = {"populate_by_name": True}


class WizardRecord(Record):
    score: int
    reasons: list[str]


class Chain(BaseModel):
    soc: Optional[Record] = None
    module: Optional[Record] = None


class PartDetail(Record):
    """One part with everything a detail page needs — see esp_atlas_core.search.get_part."""

    frontmatter: dict
    body: str
    chain: Chain
    related: list[Record] = []


class Facet(BaseModel):
    value: str
    count: int


class BrandFacet(Facet):
    """A vendor_or_brand facet entry, enriched with its editorial display name —
    see esp_atlas_core.facets. `display_name` falls back to `value` (the slug)
    when data/brands/<value>/ has no brand.md."""

    display_name: str
    url: Optional[str] = None


class NumericFacet(BaseModel):
    """A minimum-capability tier (e.g. psram_min/flash_min): `count` is how many
    parts clear that floor, not how many equal it — see esp_atlas_core.facets."""

    value: int
    count: int


class FacetsResponse(BaseModel):
    type: list[Facet]
    vendor_or_brand: list[BrandFacet]
    form_factor: list[Facet]
    wifi_standard: list[Facet]
    price_tier: list[Facet]
    soc_ref: list[Facet]
    wifi_bands: list[Facet]
    ieee802154_protocols: list[Facet]
    psram_min: list[NumericFacet]
    flash_min: list[NumericFacet]


class Brand(BaseModel):
    slug: str
    name: str
    url: Optional[str] = None


class BrandPageResponse(BaseModel):
    """GET /brands/{slug}: the brand's own identity plus every part from it."""

    brand: Brand
    results: list[Record]


class SearchResponse(BaseModel):
    results: list[Record]


class WizardResponse(BaseModel):
    results: list[WizardRecord]


class WizardNeeds(BaseModel):
    protocol: Optional[str] = None
    radio: Optional[str] = None
    band: Optional[float] = None
    ble: Optional[bool] = None
    bt_classic: Optional[bool] = None
    usb_native: Optional[bool] = None
    ieee802154: Optional[bool] = None
    form: Optional[str] = None
    type: Optional[PartType] = None
    budget: Optional[BudgetTier] = None
    psram_min: Optional[int] = None
    flash_min: Optional[int] = None

    model_config = {"extra": "forbid"}


class WizardRequest(BaseModel):
    needs: WizardNeeds = WizardNeeds()


class ValidateRequest(BaseModel):
    markdown: Optional[str] = None
    kind: Optional[PartType] = None
    frontmatter: Optional[dict] = None

    model_config = {"extra": "forbid"}


class ValidateResponse(BaseModel):
    ok: bool
    errors: list[str]
    kind: Optional[str] = None


class FirmwareRecord(BaseModel):
    """A firmware record straight from data/firmware/<id>/firmware.md — see
    esp_atlas_core.firmware. First-class like a brand: never in /search, /wizard,
    or the parts index."""

    id: str
    type: str
    name: str
    url: str
    category: str
    maintainer: Optional[str] = None
    license: Optional[str] = None
    distribution: list[str] = []
    manifest_url: Optional[str] = None
    capabilities: list[str] = []
    socs: list[str]
    sources: list[SourceEntry]


class FirmwareListResponse(BaseModel):
    results: list[FirmwareRecord]


class RecipeFlash(BaseModel):
    method: Optional[str] = None
    manifest_url: Optional[str] = None
    bin_url: Optional[str] = None
    offset: Optional[str] = None
    env: Optional[str] = None
    partition: Optional[str] = None


class RecipeRecord(BaseModel):
    """A recipe record straight from data/recipes/<id>/recipe.md — see
    esp_atlas_core.firmware. First-class like a brand: never in /search, /wizard,
    or the parts index. `chip_family` always equals the referenced board's soc."""

    id: str
    type: str
    board: str
    firmware: str
    status: str
    chip_family: str
    firmware_version: Optional[str] = None
    flash: Optional[RecipeFlash] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    notes: Optional[str] = None
    sources: list[SourceEntry]


class RecipeListResponse(BaseModel):
    results: list[RecipeRecord]
