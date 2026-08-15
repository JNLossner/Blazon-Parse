import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from blazon_parse.blazon_grammar import parse_blazon
from blazon_parse.blazon_lines import grouped_blazon_lines
from blazon_parse.blazon_parser import build_blazon, grouped_search_terms
from blazon_parse.blazon_resolve import resolve_blazon
from blazon_parse.catalog import ensure_catalog
from blazon_parse.config import WEB_HOST, WEB_OPEN_BROWSER, WEB_PORT
from blazon_parse.feature_catalog import FeatureCatalog
from blazon_parse.heraldic import FeatureType
from blazon_parse.search_url import (
    DEFAULT_MATCH_TYPE,
    KINGDOM_CODES,
    MAX_TERMS,
    build_search_url,
    search_oanda,
)

KINGDOMS = sorted(KINGDOM_CODES.items(), key=lambda code_name: code_name[1])

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "my.cat"
PARSED_CATALOG_PATH = PROJECT_ROOT / "data" / "my_catalog.json"

app = FastAPI(title="Blazon Parse")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@dataclass
class CatalogRow:
    """One catalog feature, with every term/category that resolves to it."""

    feature_type: str
    subtype: str
    details: str | None
    codes: dict[str, str]
    terms: list[str]
    categories: list[str]

    def matches(self, query: str) -> bool:
        haystacks = [
            *self.terms,
            *self.codes.values(),
            *self.categories,
            self.details or "",
        ]
        return any(query in haystack.lower() for haystack in haystacks)


def _build_catalog_rows(catalog: FeatureCatalog) -> list[CatalogRow]:
    rows = [
        CatalogRow(
            feature_type=str(feat.feature_type),
            subtype=feat.subtype,
            details=feat.details,
            codes=feat.codes,
            terms=catalog.terms_for(idx),
            categories=catalog.categories_for(idx),
        )
        for idx, feat in enumerate(catalog.features)
    ]
    rows.sort(key=lambda r: (r.feature_type, r.terms[0] if r.terms else ""))
    return rows


def _catalog_word_lists(
    catalog: FeatureCatalog,
) -> tuple[list[str], list[str], list[str]]:
    return (
        catalog.terms_of_type(FeatureType.tincture),
        catalog.terms_of_type(FeatureType.field_division),
        catalog.terms_of_type(FeatureType.field_treatment),
    )


catalog, _ = ensure_catalog(CATALOG_PATH, PARSED_CATALOG_PATH, update=False)
catalog_rows = _build_catalog_rows(catalog)
tinctures, divisions, treatments = _catalog_word_lists(catalog)


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


_HIGHLIGHT_CLASS = {"unknown": "text-error", "glued": "text-warning"}


def _subtract_spans(
    spans: list[tuple[int, int]], cuts: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """`spans` with any overlapping `cuts` ranges carved out."""
    result = []
    for start, end in spans:
        cursor = start
        for cut_start, cut_end in cuts:
            if cut_end <= cursor or cut_start >= end:
                continue
            if cut_start > cursor:
                result.append((cursor, cut_start))
            cursor = max(cursor, cut_end)
        if cursor < end:
            result.append((cursor, end))
    return result


def _highlight_spans(
    text: str, unknown_spans: list[tuple[int, int]], glued_spans: list[tuple[int, int]]
) -> Markup:
    """`text` with `unknown_spans` (never matched) in red and `glued_spans`
    (matched, but discarded as a likely false positive) in yellow."""
    red_spans = _subtract_spans(unknown_spans, glued_spans)
    segments = sorted(
        [(start, end, "unknown") for start, end in red_spans]
        + [(start, end, "glued") for start, end in glued_spans]
    )
    html: list[str] = []
    cursor = 0
    for start, end, kind in segments:
        html.append(str(escape(text[cursor:start])))
        html.append(
            f'<mark class="{_HIGHLIGHT_CLASS[kind]} bg-transparent font-semibold">'
        )
        html.append(str(escape(text[start:end])))
        html.append("</mark>")
        cursor = end
    html.append(str(escape(text[cursor:])))
    return Markup("".join(html))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/parse", response_class=HTMLResponse)
def parse(request: Request, blazon: Annotated[str, Form()]) -> HTMLResponse:
    blazon_struct = build_blazon(blazon, catalog)
    groups = [
        g for g in grouped_search_terms(blazon_struct) if g.label != "Unknown terms"
    ]
    highlighted_blazon = (
        _highlight_spans(blazon, blazon_struct.unknown_spans, blazon_struct.glued_spans)
        if blazon_struct.unknown_spans or blazon_struct.glued_spans
        else None
    )
    return templates.TemplateResponse(
        request,
        "_breakdown.html",
        {
            "groups": groups,
            "highlighted_blazon": highlighted_blazon,
            "kingdoms": KINGDOMS,
        },
    )


@app.get("/new", response_class=HTMLResponse)
def new_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index_new.html", {})


@app.post("/parse-new", response_class=HTMLResponse)
def parse_new(request: Request, blazon: Annotated[str, Form()]) -> HTMLResponse:
    tree = parse_blazon(
        blazon, tinctures=tinctures, divisions=divisions, treatments=treatments
    )
    resolved = resolve_blazon(tree, catalog)
    groups = grouped_blazon_lines(resolved)
    return templates.TemplateResponse(
        request,
        "_breakdown.html",
        {
            "groups": groups,
            "highlighted_blazon": None,
            "kingdoms": KINGDOMS,
        },
    )


def _paired_weights(term: list[str], weight: list[int] | None) -> list[int]:
    """Weights aligned to `term`, defaulting missing/non-positive entries to 1."""
    weight = weight or []
    return [max(1, weight[i]) if i < len(weight) else 1 for i in range(len(term))]


def _paired_match_types(term: list[str], match_type: list[str] | None) -> list[str]:
    """Match types aligned to `term`, defaulting missing/blank entries to armory description."""
    match_type = match_type or []
    return [
        match_type[i] if i < len(match_type) and match_type[i] else DEFAULT_MATCH_TYPE
        for i in range(len(term))
    ]


@app.post("/search/link", response_class=HTMLResponse)
def search_link(
    request: Request,
    term: Annotated[list[str] | None, Form()] = None,
    weight: Annotated[list[int] | None, Form()] = None,
    match_type: Annotated[list[str] | None, Form()] = None,
    limit: Annotated[int, Form()] = 500,
) -> HTMLResponse:
    term = term or []
    if len(term) > MAX_TERMS:
        return templates.TemplateResponse(
            request, "_search_error.html", {"count": len(term)}
        )
    url = build_search_url(
        term,
        weights=_paired_weights(term, weight),
        match_types=_paired_match_types(term, match_type),
        limit=max(1, limit),
    )
    return templates.TemplateResponse(request, "_search_link.html", {"url": url})


@app.post("/search/run", response_class=HTMLResponse)
def search_run(
    request: Request,
    term: Annotated[list[str] | None, Form()] = None,
    weight: Annotated[list[int] | None, Form()] = None,
    match_type: Annotated[list[str] | None, Form()] = None,
    limit: Annotated[int, Form()] = 500,
) -> HTMLResponse:
    term = term or []
    if len(term) > MAX_TERMS:
        return templates.TemplateResponse(
            request, "_search_error.html", {"count": len(term)}
        )
    results = search_oanda(
        term,
        weights=_paired_weights(term, weight),
        match_types=_paired_match_types(term, match_type),
        limit=max(1, limit),
    )
    groups = [
        (score, list(items)) for score, items in groupby(results, key=lambda r: r.score)
    ]
    return templates.TemplateResponse(
        request, "_results.html", {"results": results, "groups": groups}
    )


@app.get("/catalog", response_class=HTMLResponse)
def catalog_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "catalog.html", {})


@app.get("/catalog/rows", response_class=HTMLResponse)
def catalog_rows_route(request: Request, q: str = "") -> HTMLResponse:
    query = q.strip().lower()
    rows = (
        [row for row in catalog_rows if row.matches(query)] if query else catalog_rows
    )
    return templates.TemplateResponse(
        request, "_catalog_rows.html", {"rows": rows, "total": len(catalog_rows)}
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", _catalog_stats())


@app.post("/settings/update-catalog", response_class=HTMLResponse)
def update_catalog_route(request: Request) -> HTMLResponse:
    global catalog, catalog_rows, tinctures, divisions, treatments
    catalog, updated = ensure_catalog(CATALOG_PATH, PARSED_CATALOG_PATH, update=True)
    catalog_rows = _build_catalog_rows(catalog)
    tinctures, divisions, treatments = _catalog_word_lists(catalog)
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
    if WEB_OPEN_BROWSER:
        webbrowser.open(f"http://{WEB_HOST}:{WEB_PORT}")
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)


if __name__ == "__main__":
    run()
