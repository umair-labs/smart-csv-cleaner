import sys

from .cli import main

sys.exit(main())
from pathlib import Path

from csv_cleaner.cleaner import CleanerConfig, clean_dataframe, inspect_dataframe, load_csv
from csv_cleaner.report import print_report

BASE_DIR = Path(__file__).resolve().parent
RAW_PATH = BASE_DIR / "data" / "raw" / "messy_spanish.csv"
OUT_PATH = BASE_DIR / "data" / "cleaned" / "spanish_cleaned.csv"


def main() -> None:
    config = CleanerConfig(strategy="fill", fill_method="median", dayfirst=True)

    df, info = load_csv(RAW_PATH, config)
    inspect_dataframe(df)

    cleaned, report = clean_dataframe(df, config)
    report.encoding, report.delimiter = info["encoding"], info["delimiter"]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print_report(report, RAW_PATH, OUT_PATH)


if __name__ == "__main__":
    main()