import argparse
from pathlib import Path

from blazon_parse.blazon_grammar import parse_blazon
from blazon_parse.blazon_lines import blazon_lines, grouped_blazon_lines
from blazon_parse.blazon_resolve import resolve_blazon
from blazon_parse.catalog import ensure_catalog
from blazon_parse.heraldic import FeatureType
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

    tree = parse_blazon(
        args.blazon,
        tinctures=catalog.terms_of_type(FeatureType.tincture),
        divisions=catalog.terms_of_type(FeatureType.field_division),
        treatments=catalog.terms_of_type(FeatureType.field_treatment),
        lines=catalog.terms_of_type(FeatureType.line),
    )
    resolved = resolve_blazon(tree, catalog)
    print(args.blazon, "\n")
    if args.verbose:
        for group in grouped_blazon_lines(resolved):
            print(group.label)
            for term in group.terms:
                print(" " * 4, term)
            for term in group.alternates:
                print(" " * 4, "?", term)
    if args.search:
        print(build_search_url(blazon_lines(resolved)))


if __name__ == "__main__":
    main()
