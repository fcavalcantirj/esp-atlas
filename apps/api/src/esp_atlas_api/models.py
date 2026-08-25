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
    soc: Optional[str] = None
    battery: Optional[bool] = None
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


ExampleKind = Literal["firmware", "needs"]
ExampleGroup = Literal["run-firmware", "build-project", "just-show-me"]


class ExampleRecord(BaseModel):
    """A generated home example — a computed projection of the dataset, never a
    stored entity (the `example` data entity is SPEC-discovery's G2, unspecced).
    See esp_atlas_core.examples. kind="firmware" carries `firmware` (a firmware
    id whose page lists the boards it runs on); kind="needs" carries `needs` (a
    saved wizard query). Every record resolves to >=1 result by construction.
    """

    id: str
    label: str
    kind: ExampleKind
    group: ExampleGroup
    #: What the firmware is, derived from its category + capabilities. Absent on
    #: needs-examples, whose query already says what they select for.
    description: Optional[str] = None
    firmware: Optional[str] = None
    needs: Optional[WizardNeeds] = None
    count: int


class ExamplesResponse(BaseModel):
    results: list[ExampleRecord]


class IntentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    model_config = {"extra": "forbid"}


class FirmwareRequirement(BaseModel):
    """One `requires` entry from data/firmware/<id>/firmware.md -- the author's
    own verbatim rationale for why a firmware needs a capability. `board_signal`
    names the structured board field esp_atlas_core.run_guide checks to state
    met/unmet for a given board, or is None when the capability can't be proven
    or disproven from any board's structured record (e.g. sub-GHz, NFC, IR)."""

    capability: str
    why: Optional[str] = None
    board_signal: Optional[str] = None


class FirmwareNotRequired(BaseModel):
    """One `not_required` entry -- a capability the firmware explicitly does
    NOT need, taught regardless of what any one board happens to carry."""

    capability: str
    why: Optional[str] = None


class BoardReason(BaseModel):
    """Why one board runs a firmware -- the recipe's own cited justification
    (SPEC-wizard.md trust tiers), never invented prose. See
    esp_atlas_core.firmware.list_recipes / esp_atlas_core.intent.parse_intent."""

    board: str
    status: str
    chip_family: str
    sources: list[SourceEntry] = []
    reason: Optional[str] = None


class IntentResponse(BaseModel):
    """What the intent box understood, and what it could not.

    `kind` is "firmware" (the query named one — answer from the recipe graph),
    "filters" (mapped onto real fields), or "unreadable" (say so plainly rather
    than dumping a keyword search under an AI-looking prompt).
    """

    kind: Literal["firmware", "filters", "unreadable"]
    filters: WizardNeeds = WizardNeeds()
    understood: list[str] = []
    unmapped: list[str] = []
    firmware: Optional[str] = None
    firmware_name: Optional[str] = None
    #: What the firmware is, derived server-side from its category + capabilities
    #: (esp_atlas_core.examples.describe_firmware) -- data only, never generated prose.
    firmware_description: Optional[str] = None
    boards: list[str] = []
    #: Per-board cited justification, parallel to `boards` -- see BoardReason.
    board_reasons: list[BoardReason] = []
    #: The firmware's own declared requirement-rationale (data/firmware/<id>/
    #: firmware.md `requires`/`not_required`), only populated for kind=="firmware".
    requires: list[FirmwareRequirement] = []
    not_required: list[FirmwareNotRequired] = []
    cached: bool = False


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
    benefits_from: list[str] = []
    requires: list[FirmwareRequirement] = []
    not_required: list[FirmwareNotRequired] = []
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


class RunGuideBoard(BaseModel):
    """One board's grounded, reasoned fit for a firmware -- see
    esp_atlas_core.run_guide. `reasons`, `particularities`, and `fit` are always
    deterministic, computed straight from this board's own real record; `note`
    is the only field an LLM ever contributes, and only after surviving the
    grounding validator (a hallucinated board, spec, or source is rejected
    outright, never sanitized into something safer)."""

    board_id: str
    board_name: str
    fit: str
    reasons: list[str] = []
    particularities: list[str] = []
    #: Grounded requirement-rationale teaching for THIS board -- each
    #: `requires` entry stated met/unmet against its real record (or named as
    #: unverifiable when `board_signal` is null); `not_required` is the same
    #: for every board of this firmware (see esp_atlas_core.run_guide).
    requires: list[str] = []
    not_required: list[str] = []
    status: Optional[str] = None
    chip_family: Optional[str] = None
    sources: list[SourceEntry] = []
    note: Optional[str] = None


class RunGuideFlashNext(BaseModel):
    board: str
    recipe_id: str
    manifest_url: str


class RunGuideConstraint(BaseModel):
    chip: str


class RunGuideExcludedBoard(BaseModel):
    board: str
    reason: str


class RunGuideResponse(BaseModel):
    """GET /run/{firmware_id} -- the grounded "why does this firmware run on
    these boards" answer. `grounded` is False only for an unknown/misspelled
    firmware id, in which case `summary` is the honest not-found message and
    every list is empty -- never a guess."""

    firmware: str
    firmware_name: Optional[str] = None
    summary: str
    requirements: list[str] = []
    #: The firmware's own declared requirement-rationale, verbatim from
    #: data/firmware/<id>/firmware.md -- see FirmwareRequirement/FirmwareNotRequired.
    #: Per-board grounded teaching (met/unmet) lives on each RunGuideBoard instead.
    requires: list[FirmwareRequirement] = []
    not_required: list[FirmwareNotRequired] = []
    boards: list[RunGuideBoard] = []
    flash_next: list[RunGuideFlashNext] = []
    citations: list[str] = []
    grounded: bool
    constraint: Optional[RunGuideConstraint] = None
    excluded_boards: list[RunGuideExcludedBoard] = []
