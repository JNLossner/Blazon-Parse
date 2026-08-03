import argparse
from pathlib import Path

from blazon_parse.catalog import get_updated_catalog

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "my.cat"


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an SCA heraldry blazon.")
    parser.add_argument("blazon", help="The blazon text to parse")
    args = parser.parse_args()

    _, updated = get_updated_catalog(CATALOG_PATH)
    if updated:
        print("Updated my.cat catalog.")

    print(args.blazon)


if __name__ == "__main__":
    main()
