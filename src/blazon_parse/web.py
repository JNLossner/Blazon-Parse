import webbrowser
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from blazon_parse.blazon_parser import build_blazon, grouped_search_terms
from blazon_parse.catalog import ensure_catalog
from blazon_parse.search_url import MAX_TERMS, build_search_url, search_oanda

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "my.cat"
PARSED_CATALOG_PATH = PROJECT_ROOT / "data" / "my_catalog.json"

HOST = "127.0.0.1"
PORT = 8000

app = FastAPI(title="Blazon Parse")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

catalog, _ = ensure_catalog(CATALOG_PATH, PARSED_CATALOG_PATH, update=False)


def _catalog_stats() -> dict:
    last_modified = (
        datetime.fromtimestamp(CATALOG_PATH.stat().st_mtime, tz=UTC).astimezone()
        if CATALOG_PATH.exists()
        else None
    )
    return {
        "catalog_path": str(CATALOG_PATH),
        "last_modified": last_modified.strftime("%Y-%m-%d %H:%M")
        if last_modified
        else "never",
        "feature_count": len(catalog.features),
        "term_count": len(catalog.terms()),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/parse", response_class=HTMLResponse)
def parse(request: Request, blazon: Annotated[str, Form()]) -> HTMLResponse:
    blazon_struct = build_blazon(blazon, catalog)
    groups = grouped_search_terms(blazon_struct)
    return templates.TemplateResponse(request, "_breakdown.html", {"groups": groups})


@app.post("/search/link", response_class=HTMLResponse)
def search_link(
    request: Request, term: Annotated[list[str] | None, Form()] = None
) -> HTMLResponse:
    term = term or []
    if len(term) > MAX_TERMS:
        return templates.TemplateResponse(
            request, "_search_error.html", {"count": len(term)}
        )
    url = build_search_url(term)
    return templates.TemplateResponse(request, "_search_link.html", {"url": url})


@app.post("/search/run", response_class=HTMLResponse)
def search_run(
    request: Request, term: Annotated[list[str] | None, Form()] = None
) -> HTMLResponse:
    term = term or []
    if len(term) > MAX_TERMS:
        return templates.TemplateResponse(
            request, "_search_error.html", {"count": len(term)}
        )
    results = search_oanda(term)
    groups = [
        (score, list(items)) for score, items in groupby(results, key=lambda r: r.score)
    ]
    return templates.TemplateResponse(
        request, "_results.html", {"results": results, "groups": groups}
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", _catalog_stats())


@app.post("/settings/update-catalog", response_class=HTMLResponse)
def update_catalog_route(request: Request) -> HTMLResponse:
    global catalog
    catalog, updated = ensure_catalog(CATALOG_PATH, PARSED_CATALOG_PATH, update=True)
    return templates.TemplateResponse(
        request,
        "_catalog_status.html",
        {
            "updated": updated,
            "feature_count": len(catalog.features),
            "term_count": len(catalog.terms()),
        },
    )


def run() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    run()
