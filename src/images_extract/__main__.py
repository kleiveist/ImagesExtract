"""Allow ``python -m images_extract`` to use the command-line interface."""

from images_extract.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
