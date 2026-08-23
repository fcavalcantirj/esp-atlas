"""esp-atlas FastAPI backend — thin HTTP shell over esp_atlas_core.

All ranking/filtering logic lives in esp_atlas_core (search/wizard); this
module only maps HTTP in/out to that library's public functions.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from esp_atlas_core import db as dbmod
from esp_atlas_core.facets import facets as core_facets
from esp_atlas_core.firmware import get_firmware as core_get_firmware
from esp_atlas_core.firmware import list_firmware as core_list_firmware
from esp_atlas_core.firmware import list_recipes as core_list_recipes
from esp_atlas_core.firmware import recipes_for_board as core_recipes_for_board
from esp_atlas_core.firmware import recipes_for_firmware as core_recipes_for_firmware
from esp_atlas_core.index_build import build_index
from esp_atlas_core.search import brand_page as core_brand_page
from esp_atlas_core.search import get_part as core_get_part
from esp_atlas_core.search import search as core_search
from esp_atlas_core.validate import validate_frontmatter as core_validate_frontmatter
from esp_atlas_core.validate import validate_markdown as core_validate_markdown
from esp_atlas_core.wizard import wizard as core_wizard

from esp_atlas_api.models import (
    BrandPageResponse,
    FacetsResponse,
    FirmwareListResponse,
    FirmwareRecord,
    HealthResponse,
    PartDetail,
    PartType,
    RecipeListResponse,
    SearchResponse,
    ValidateRequest,
    ValidateResponse,
    WizardRequest,
    WizardResponse,
)
from esp_atlas_api.settings import resolve_db_path

_ALL_PARTS_LIMIT = 10_000


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db_path = Path(app.state.db_path)
    if not db_path.exists():
        build_index(db_path=db_path)
    yield


def get_db_path(request: Request):
    return request.app.state.db_path


def create_app(db_path=None):
    app = FastAPI(title="esp-atlas API", lifespan=_lifespan)
    app.state.db_path = db_path or resolve_db_path()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health(db_path=Depends(get_db_path)):
        conn = dbmod.connect(db_path)
        try:
            count = int(dbmod.get_meta(conn, "count", "0"))
        finally:
            conn.close()
        return HealthResponse(status="ok", count=count)

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = "",
        type: Optional[PartType] = None,
        radio: Optional[str] = None,
        band: Optional[float] = None,
        form: Optional[str] = None,
        protocol: Optional[str] = None,
        ieee802154: Optional[bool] = None,
        ble: Optional[bool] = None,
        bt_classic: Optional[bool] = None,
        usb_native: Optional[bool] = None,
        soc: Optional[str] = None,
        module: Optional[str] = None,
        brand: Optional[str] = None,
        db_path=Depends(get_db_path),
    ):
        filters = {}
        if type is not None:
            filters["type"] = type
        if radio is not None:
            filters["radio"] = radio
        if band is not None:
            filters["band"] = band
        if form is not None:
            filters["form"] = form
        if soc is not None:
            filters["soc"] = soc
        if module is not None:
            filters["module"] = module
        if brand is not None:
            filters["brand"] = brand
        if protocol is not None:
            filters["protocol"] = protocol
        if ieee802154 is not None:
            filters["ieee802154"] = ieee802154
        if ble is not None:
            filters["ble"] = ble
        if bt_classic is not None:
            filters["bt_classic"] = bt_classic
        if usb_native is not None:
            filters["usb_native"] = usb_native

        try:
            results = core_search(q, filters=filters, db_path=db_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SearchResponse(results=results)

    @app.post("/wizard", response_model=WizardResponse)
    def wizard(body: WizardRequest = WizardRequest(), db_path=Depends(get_db_path)):
        needs = body.needs.model_dump(exclude_none=True)
        try:
            results = core_wizard(needs, db_path=db_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WizardResponse(results=results)

    @app.post("/validate", response_model=ValidateResponse)
    def validate(body: ValidateRequest):
        if body.markdown is not None:
            result = core_validate_markdown(body.markdown)
        elif body.kind is not None and body.frontmatter is not None:
            fm_result = core_validate_frontmatter(body.frontmatter, body.kind)
            result = {**fm_result, "kind": body.kind}
        else:
            raise HTTPException(
                status_code=422,
                detail="provide either 'markdown' or both 'kind' and 'frontmatter'",
            )
        return ValidateResponse(**result)

    @app.get("/parts", response_model=SearchResponse)
    def list_parts(db_path=Depends(get_db_path)):
        results = core_search("", filters={}, db_path=db_path, limit=_ALL_PARTS_LIMIT)
        return SearchResponse(results=results)

    @app.get("/parts/{part_id}", response_model=PartDetail)
    def get_part(part_id: str, db_path=Depends(get_db_path)):
        record = core_get_part(part_id, db_path=db_path)
        if record is None:
            raise HTTPException(status_code=404, detail=f"part not found: {part_id}")
        return record

    @app.get("/facets", response_model=FacetsResponse)
    def facets(db_path=Depends(get_db_path)):
        return FacetsResponse(**core_facets(db_path=db_path))

    @app.get("/brands/{slug}", response_model=BrandPageResponse)
    def brand_page(slug: str, db_path=Depends(get_db_path)):
        return core_brand_page(slug, db_path=db_path)

    @app.get("/firmware", response_model=FirmwareListResponse)
    def list_firmware():
        return FirmwareListResponse(results=core_list_firmware())

    @app.get("/firmware/{firmware_id}", response_model=FirmwareRecord)
    def get_firmware(firmware_id: str):
        record = core_get_firmware(firmware_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"firmware not found: {firmware_id}")
        return record

    @app.get("/recipes", response_model=RecipeListResponse)
    def list_recipes(board: Optional[str] = None, firmware: Optional[str] = None):
        if board is not None:
            results = core_recipes_for_board(board)
        elif firmware is not None:
            results = core_recipes_for_firmware(firmware)
        else:
            results = core_list_recipes()
        return RecipeListResponse(results=results)

    return app


app = create_app()
