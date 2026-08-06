import argparse
from pathlib import Path

from blazon_parse.blazon_parser import parse_blazon
from blazon_parse.catalog import ensure_catalog
from blazon_parse.search_url import build_search_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "my.cat"
PARSED_CATALOG_PATH = PROJECT_ROOT / "data" / "my_catalog.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an SCA heraldry blazon.")
    parser.add_argument("blazon", help="The blazon text to parse")
    parser.add_argument(
        "-u", "--update", help="Update parsed my.cat catalog", action="store_true"
    )
    parser.add_argument(
        "-v", "--verbose", help="Show all parsed search terms", action="store_true"
    )
    parser.add_argument(
        "-s", "--search", help="Generate a search URL", action="store_true"
    )
    args = parser.parse_args()

    catalog, reparsed = ensure_catalog(
        CATALOG_PATH, PARSED_CATALOG_PATH, update=args.update
    )
    if reparsed:
        print("Updated my.cat catalog.")

    print(
        f"Loaded catalog: {len(catalog.features)} features, {len(catalog.terms())} terms."
    )

    terms = parse_blazon(args.blazon, catalog)
    print(args.blazon)
    if args.verbose:
        print(terms)
    if args.search:
        print(build_search_url(terms))


if __name__ == "__main__":
    main()
