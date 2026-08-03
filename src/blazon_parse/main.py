import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an SCA heraldry blazon.")
    parser.add_argument("blazon", help="The blazon text to parse")
    args = parser.parse_args()
    print(args.blazon)


if __name__ == "__main__":
    main()
