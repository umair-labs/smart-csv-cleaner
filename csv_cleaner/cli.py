"""Command-line interface for the Smart CSV Data Cleaner."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from .cleaner import (
    CleanerConfig,
    clean_dataframe,
    inspect_dataframe,
    load_csv,
    standardize_column_name,
)
from .report import print_report

log = logging.getLogger("csv_cleaner")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="csv_cleaner",
        description="Clean a messy CSV: tidy headers, trim text, fix types, "
                    "remove duplicates, and handle missing values.",
    )
    p.add_argument("input", type=Path, help="path to the raw CSV file")
    p.add_argument("-o", "--output", type=Path,
                   help="where to save the cleaned CSV (default: <input>_cleaned.csv)")

    g = p.add_argument_group("missing values")
    g.add_argument("--strategy", choices=["fill", "drop"], default="fill",
                   help="fill numeric gaps, or drop rows with gaps (default: fill)")
    g.add_argument("--fill-method", choices=["mean", "median"], default="median")
    g.add_argument("--drop-subset", nargs="+", metavar="COL",
                   help="with --strategy drop: only drop rows missing these columns")

    g = p.add_argument_group("parsing")
    g.add_argument("--delimiter", help="force a delimiter, e.g. ';' or 'tab' (default: auto-detect)")
    g.add_argument("--encoding", help="force an encoding, e.g. cp1252 (default: auto-detect)")
    g.add_argument("--date-columns", nargs="+", metavar="COL",
                   help="columns to parse as dates (default: guess from column names)")
    g.add_argument("--dayfirst", action="store_true", help="read 03/02/2024 as 3 February")
    g.add_argument("--no-convert-types", action="store_true", help="skip number/date conversion")
    g.add_argument("--no-keep-integers", action="store_true", help="allow 34.0 instead of 34")

    g = p.add_argument_group("output")
    g.add_argument("--inspect", action="store_true", help="print a preview of the raw data first")
    g.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    return p


def _names(cols: list[str] | None) -> list[str] | None:
    """Users type column names as they appear in the file; we match the cleaned versions."""
    return [standardize_column_name(c) for c in cols] if cols else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    output = args.output or args.input.with_name(f"{args.input.stem}_cleaned.csv")
    if output.resolve() == args.input.resolve():
        log.error("Output path is the same as the input; refusing to overwrite the original.")
        return 2

    delimiter = "\t" if args.delimiter in ("tab", "\\t") else args.delimiter

    try:
        config = CleanerConfig(
            strategy=args.strategy,
            fill_method=args.fill_method,
            drop_subset=_names(args.drop_subset),
            delimiter=delimiter,
            encoding=args.encoding,
            convert_types=not args.no_convert_types,
            date_columns=_names(args.date_columns),
            dayfirst=args.dayfirst,
            keep_integers=not args.no_keep_integers,
        )
        log.info("Loading %s", args.input)
        df, info = load_csv(args.input, config)
        log.debug("Detected %s", info)

        if args.inspect:
            inspect_dataframe(df)

        cleaned, report = clean_dataframe(df, config)
        report.encoding, report.delimiter = info["encoding"], info["delimiter"]

        output.parent.mkdir(parents=True, exist_ok=True)
        cleaned.to_csv(output, index=False, encoding="utf-8")
    except (FileNotFoundError, ValueError, pd.errors.ParserError, PermissionError) as exc:
        log.error("%s", exc)
        return 1

    print_report(report, args.input, output)
    return 0