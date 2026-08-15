# Blazon-Parse

Parse SCA armorial blazon text (e.g. "Argent, a lion sable.") into the O&A
(Ordinary and Armorial) complex-search terms used by the SCA College of Arms
to check name/armory submissions for conflicts at
[oanda.sca.org](https://oanda.sca.org). Given a blazon, this produces the
terms a herald would type into that search by hand, and can optionally run
the search directly.

## Status

Under active development. Blazon coverage is broad but not exhaustive.

## Installation

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Usage

### CLI

```sh
uv run blazon-parse "Argent, a lion sable."
```

Options:

- `-v`, `--verbose` — print every parsed O&A search term, grouped by
  category.
- `-s`, `--search` — print a ready-to-use O&A complex-search URL.
- `-u`, `--update` — refresh the local catalog (`data/my.cat`) from
  oanda.sca.org before parsing.

### Web UI

```sh
uv run blazon-parse-web
```

Starts a local FastAPI server and opens a browser tab. From there you can
parse a blazon and view its search terms, browse/search the parsed catalog,
build or run an O&A search, and refresh the catalog.

Configuration is via environment variables (copy `.env.example` to `.env` to
override defaults): `BLAZON_PARSE_HOST`, `BLAZON_PARSE_PORT`,
`BLAZON_PARSE_OPEN_BROWSER`, `OANDA_SEARCH_URL`.

### Docker

```sh
docker compose up
```

Runs the web app alongside a local mirror of the O&A search endpoint (see
`docker/oanda/`), so it doesn't hit the live oanda.sca.org site.

## Development

```sh
uv sync
uv run pytest
uv run pre-commit run --all-files
```

## License

[MIT](LICENSE)
