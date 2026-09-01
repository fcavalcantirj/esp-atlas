"""esp-atlas FastAPI backend — thin HTTP shell over esp_atlas_core.

All ranking/filtering logic lives in esp_atlas_core (search/wizard); this
module only maps HTTP in/out to that library's public functions.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from esp_atlas_core import db as dbmod
from esp_atlas_core.boot import list_boot_modes as core_list_boot_modes
from esp_atlas_core.build_guide import build_guide as core_build_guide
from esp_atlas_core.clarify import clarify as core_clarify
from esp_atlas_core.intent import parse_intent as core_parse_intent
from esp_atlas_core.llm import GroqConfigError, GroqRateLimitError
from esp_atlas_core.flash import MAX_REDIRECT_HOPS
from esp_atlas_core.flash import bin_url_for as core_bin_url_for
from esp_atlas_core.flash import next_hop as core_next_hop
from esp_atlas_core.flash import build_manifest as core_build_manifest
from esp_atlas_core.examples import generate_examples as core_generate_examples
from esp_atlas_core.facets import facets as core_facets
from esp_atlas_core.firmware import get_firmware as core_get_firmware
from esp_atlas_core.firmware import list_firmware as core_list_firmware
from esp_atlas_core.firmware import list_recipes as core_list_recipes
from esp_atlas_core.firmware import recipes_for_board as core_recipes_for_board
from esp_atlas_core.firmware import recipes_for_firmware as core_recipes_for_firmware
from esp_atlas_core.index_build import build_index
from esp_atlas_core.run_guide import run_guide as core_run_guide
from esp_atlas_core.search import brand_page as core_brand_page
from esp_atlas_core.search import get_part as core_get_part
from esp_atlas_core.search import search as core_search
from esp_atlas_core.status import compute_status as core_compute_status
from esp_atlas_core.validate import validate_frontmatter as core_validate_frontmatter
from esp_atlas_core.validate import validate_markdown as core_validate_markdown
from esp_atlas_core.wizard import wizard as core_wizard

from esp_atlas_api.models import (
    BootBoard,
    BrandPageResponse,
    BuildGuideRequest,
    BuildGuideResponse,
    ClarifyRequest,
    ClarifyResponse,
    IntentRequest,
    IntentResponse,
    ExamplesResponse,
    FacetsResponse,
    FirmwareListResponse,
    FirmwareRecord,
    HealthResponse,
    PartDetail,
    PartType,
    RecipeListResponse,
    RunGuideResponse,
    SearchResponse,
    StatusResponse,
    ValidateRequest,
    ValidateResponse,
    WizardRequest,
    WizardResponse,
)
from esp_atlas_api.security import build_limiter, resolve_cors_origins, resolve_rate_limits
from esp_atlas_api.settings import resolve_db_path

_ALL_PARTS_LIMIT = 10_000
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


async def _fetch_following_allowlisted_redirects(client, url, headers):
    """GET `url`, following redirects only while each hop stays on the allowlist.

    Raises PermissionError the moment a hop points off-allowlist -- that is an
    SSRF attempt (or a compromised upstream), not a transport failure.
    """
    current = url
    for _ in range(MAX_REDIRECT_HOPS + 1):
        response = await client.send(client.build_request("GET", current, headers=headers), stream=True)
        if response.status_code not in _REDIRECT_CODES:
            return response
        location = response.headers.get("location")
        await response.aclose()
        target = core_next_hop(current, location)
        if target is None:
            raise PermissionError(f"redirect to a non-allowlisted host refused: {location!r}")
        current = target
    raise PermissionError("too many redirects")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db_path = Path(app.state.db_path)
    if not db_path.exists():
        build_index(db_path=db_path)
    yield


def get_db_path(request: Request):
    return request.app.state.db_path


def get_llm_client(request: Request):
    """None in production -- the caller builds a real GroqClient itself. Tests
    inject a fake here so the suite never makes a network call."""
    return getattr(request.app.state, "llm_client", None)


def create_app(db_path=None, llm_client=None, cors_origins=None, rate_limits=None):
    app = FastAPI(title="esp-atlas API", lifespan=_lifespan)
    app.state.db_path = db_path or resolve_db_path()
    app.state.llm_client = llm_client

    # Same-origin frontend (apps/web/lib/api.ts) needs no cross-origin
    # access at all; the allowlist exists for local dev and nothing else.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else resolve_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    limits = rate_limits if rate_limits is not None else resolve_rate_limits()
    limiter = build_limiter(limits)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # Enforces the generous default_limits (see security.py) on every route
    # that isn't itself @limiter.limit()-decorated or limiter.exempt()-ed.
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/health", response_model=HealthResponse)
    def health(db_path=Depends(get_db_path)):
        conn = dbmod.connect(db_path)
        try:
            count = int(dbmod.get_meta(conn, "count", "0"))
        finally:
            conn.close()
        return HealthResponse(status="ok", count=count)

    limiter.exempt(health)  # uptime/monitoring checks must never 429

    @app.get("/status", response_model=StatusResponse)
    def status(db_path=Depends(get_db_path)):
        """Public live health snapshot (INTERFACE-SPEC.md `GET /status`).

        esp_atlas_core.status wraps every component probe individually, so it
        already never raises -- this except is defense in depth against a
        genuinely unexpected failure, so the page still renders "down" rather
        than a bare 500.
        """
        try:
            return core_compute_status(db_path=db_path)
        except Exception:
            return StatusResponse(status="down", generated_at=datetime.now(timezone.utc).isoformat(), components=[])

    limiter.exempt(status)  # public status page polls every 30s, must never 429

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
        psram_min: Optional[int] = None,
        flash_min: Optional[int] = None,
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
        if psram_min is not None:
            filters["psram_min"] = psram_min
        if flash_min is not None:
            filters["flash_min"] = flash_min

        try:
            results = core_search(q, filters=filters, db_path=db_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SearchResponse(results=results)

    @app.post("/wizard", response_model=WizardResponse)
    @limiter.limit(limits["llm"])
    def wizard(request: Request, body: WizardRequest = WizardRequest(), db_path=Depends(get_db_path)):
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

    @app.get("/boards/boot", response_model=list[BootBoard])
    def boards_boot():
        """Boards that cite a Firmware-Download-mode, for the /debug connect
        troubleshooter (SPEC-first-flash.md P0). Reads frontmatter directly --
        no DB, no network -- and never 500s: list_boot_modes() wraps every board
        read and skips unreadable ones, so a malformed board.md degrades to a
        shorter list rather than an error."""
        try:
            return core_list_boot_modes()
        except Exception:
            return []

    @app.get("/manifest/{recipe_id}.json")
    def manifest(recipe_id: str, request: Request, db_path=Depends(get_db_path)):
        """An ESP Web Tools manifest derived from the recipe (SPEC-wizard P3).

        404 when the recipe cannot flash in-browser -- unknown, not a
        `release-bin`, no binary recorded, or a chip ESP Web Tools has no
        chipFamily for. The wizard falls back to a guided handoff on 404.
        """
        proxy_url = str(request.url_for("flash_bin"))
        result = core_build_manifest(recipe_id, db_path=db_path, proxy_url=proxy_url)
        if result is None:
            raise HTTPException(status_code=404, detail=f"no in-browser manifest for recipe: {recipe_id}")
        return result

    @app.get("/flash-bin", name="flash_bin")
    @limiter.limit(limits["flash"])
    async def flash_bin(request: Request, recipe: str, part: Optional[int] = None):
        """Stream an upstream firmware binary same-origin so ESP Web Tools can fetch it.

        GitHub release assets send no Access-Control-Allow-Origin, so the browser
        cannot fetch them from our page directly. This passes the bytes through
        and stores nothing -- we transit, we do not rehost (SPEC-wizard).

        Not an open proxy by construction: the caller names a *recipe*, and the
        URL is resolved server-side from that record and re-checked against an
        allowlist. There is no request shape that makes it fetch a caller-chosen
        host, which is the whole SSRF surface.
        """
        url = core_bin_url_for(recipe, part=part)
        if url is None:
            raise HTTPException(status_code=403, detail="no allowlisted binary for that recipe")

        # Range must survive in both directions: esptool-js reads the image in
        # chunks, and a dropped Range would restart the flash from zero.
        forwarded = {"Range": request.headers["range"]} if "range" in request.headers else {}
        # follow_redirects is deliberately OFF: httpx would validate only the
        # first hop, so an allowlisted host could redirect us anywhere. Each hop
        # is re-checked against the allowlist before it is followed.
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=False)
        try:
            upstream = await _fetch_following_allowlisted_redirects(client, url, forwarded)
        except PermissionError as exc:
            await client.aclose()
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"upstream fetch failed: {exc}") from exc

        if upstream.status_code >= 400:
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"upstream returned {upstream.status_code}")

        async def body():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        passthrough = {
            key: upstream.headers[key]
            for key in ("content-length", "content-range", "accept-ranges")
            if key in upstream.headers
        }
        # A released binary is immutable for its version, so it caches hard at
        # the edge. That is a transient CDN cache, not a stored artifact.
        passthrough["Cache-Control"] = "public, max-age=3600, s-maxage=31536000, immutable"
        return StreamingResponse(
            body(),
            status_code=upstream.status_code,
            media_type="application/octet-stream",
            headers=passthrough,
        )

    @app.post("/intent", response_model=IntentResponse, response_model_exclude_none=True)
    @limiter.limit(limits["llm"])
    def intent(request: Request, payload: IntentRequest, db_path=Depends(get_db_path), llm_client=Depends(get_llm_client)):
        """Plain-language goal -> the wizard's own filters (SPEC-INDEX G4).

        Groq reads the query, never the catalogue, so cost is per-unique-phrasing
        and flat in the number of boards. If inference is unavailable the caller
        gets 503 and falls back to keyword search -- the prompt must never be a
        dead end just because a model is down.
        """
        try:
            return core_parse_intent(payload.query, llm_client=llm_client, db_path=db_path)
        except GroqConfigError as exc:
            raise HTTPException(status_code=503, detail="Intent parsing is unavailable: no Groq API key configured.") from exc
        except GroqRateLimitError as exc:
            raise HTTPException(status_code=503, detail="Intent parsing is rate-limited right now.") from exc

    @app.post("/build", response_model=BuildGuideResponse, response_model_exclude_none=True)
    @limiter.limit(limits["llm"])
    def build(request: Request, payload: BuildGuideRequest, db_path=Depends(get_db_path), llm_client=Depends(get_llm_client)):
        """The grounded "here's what you need" answer for a project goal
        (SPEC-build-guide.md, esp_atlas_core.build_guide) -- the web calls this
        when POST /intent returns kind=="unmapped". Always 200: build_guide()
        degrades to a deterministic, still-grounded answer on its own rather
        than ever raising, so this route needs no exception handling.
        """
        return core_build_guide(payload.query, llm_client=llm_client, db_path=db_path)

    @app.post("/clarify", response_model=ClarifyResponse)
    @limiter.limit(limits["llm"])
    def clarify(request: Request, payload: ClarifyRequest, db_path=Depends(get_db_path), llm_client=Depends(get_llm_client)):
        """Confidence-gated clarification (SPEC-clarify.md): a deterministic
        gate over parse_intent()'s own output either answers directly
        (confident=True, no questions) or returns 1-3 grounded questions from
        a fixed catalog. Always 200 -- the gate is pure code, and question
        selection degrades to a deterministic default order rather than ever
        raising when Groq is down/rate-limited/garbage.
        """
        return core_clarify(payload.query, answers=payload.answers, llm_client=llm_client, db_path=db_path)

    @app.get("/facets", response_model=FacetsResponse)
    def facets(db_path=Depends(get_db_path)):
        return FacetsResponse(**core_facets(db_path=db_path))

    @app.get("/examples", response_model=ExamplesResponse, response_model_exclude_none=True)
    def examples(db_path=Depends(get_db_path)):
        return ExamplesResponse(results=core_generate_examples(db_path=db_path))

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

    @app.get("/run/{firmware_id}", response_model=RunGuideResponse, response_model_exclude_none=True)
    def run(firmware_id: str, constraints: Optional[str] = None, db_path=Depends(get_db_path), llm_client=Depends(get_llm_client)):
        """Grounded, reasoned "why does this firmware run on these boards"
        (esp_atlas_core.run_guide). Degrades honestly rather than 500s or
        4xx-ing: an unknown firmware, a down/rate-limited model, or a garbage
        model reply all fall back to a deterministic, fully-grounded answer.
        """
        return core_run_guide(firmware_id, constraints=constraints, llm_client=llm_client, db_path=db_path)

    return app


app = create_app()
