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
from esp_atlas_core.index_build import build_index
from esp_atlas_core.search import search as core_search
from esp_atlas_core.wizard import wizard as core_wizard

from esp_atlas_api.models import (
    HealthResponse,
    PartType,
    Record,
    SearchResponse,
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

    @app.get("/parts", response_model=SearchResponse)
    def list_parts(db_path=Depends(get_db_path)):
        results = core_search("", filters={}, db_path=db_path, limit=_ALL_PARTS_LIMIT)
        return SearchResponse(results=results)

    @app.get("/parts/{part_id}", response_model=Record)
    def get_part(part_id: str, db_path=Depends(get_db_path)):
        results = core_search("", filters={}, db_path=db_path, limit=_ALL_PARTS_LIMIT)
        for record in results:
            if record["id"] == part_id:
                return record
        raise HTTPException(status_code=404, detail=f"part not found: {part_id}")

    return app


app = create_app()
