import argparse
from pathlib import Path

from blazon_parse.blazon_parser import parse_blazon
from blazon_parse.catalog import get_updated_catalog
from blazon_parse.catalog_parser import (
    load_parsed_catalog,
    parse_catalog_file,
    save_parsed_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "my.cat"
PARSED_CATALOG_PATH = PROJECT_ROOT / "data" / "my_catalog.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an SCA heraldry blazon.")
    parser.add_argument("blazon", help="The blazon text to parse")
    args = parser.parse_args()

    _, updated = get_updated_catalog(CATALOG_PATH)
    if updated or not PARSED_CATALOG_PATH.exists():
        save_parsed_catalog(parse_catalog_file(CATALOG_PATH), PARSED_CATALOG_PATH)
        print("Updated my.cat catalog.")

    catalog = load_parsed_catalog(PARSED_CATALOG_PATH)
    print(
        f"Loaded catalog: {len(catalog.categories)} categories, {len(catalog.features)} features."
    )

    print(args.blazon)
    print(parse_blazon(args.blazon, catalog))


if __name__ == "__main__":
    main()
