"""Open Edit CLI — Phase 0 placeholder."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open_edit",
        description="AI-native video editing platform",
    )
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print("open_edit 0.1.0")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
