"""Console summary report."""
from __future__ import annotations

from pathlib import Path

from .cleaner import CleaningReport

WIDTH = 56


def print_report(report: CleaningReport, source: Path, output: Path) -> None:
    bar = "=" * WIDTH
    print(f"\n{bar}\n{'CSV CLEANING REPORT'.center(WIDTH)}\n{bar}")
    print(f"Input file            : {source}")
    print(f"Output file           : {output}")
    print(f"Detected encoding     : {report.encoding}")
    print(f"Detected delimiter    : {report.delimiter!r}")
    print("-" * WIDTH)
    print(f"Total rows (original) : {report.rows_before}")
    print(f"Duplicates removed    : {report.duplicates_removed}")
    print(f"Rows dropped (missing): {report.rows_dropped_missing}")
    print(f"Total rows (final)    : {report.rows_after}")
    print("-" * WIDTH)

    print("Missing values by column")
    print(f"  {'column':<18}{'found':>7}{'filled':>8}{'remaining':>11}")
    any_missing = False
    for col, found in report.missing_before.items():
        if found == 0:
            continue
        any_missing = True
        filled = report.filled.get(col, 0)
        remaining = int(report.missing_after.get(col, 0))
        print(f"  {col:<18}{found:>7}{filled:>8}{remaining:>11}")
    if not any_missing:
        print("  none")
    if report.converted_types:
        print("-" * WIDTH)
        print("Type conversions")
        for col, kind in report.converted_types.items():
            note = ""
            if col in report.unparseable_dates:
                note = f"  ({report.unparseable_dates[col]} unparseable -> missing)"
            print(f"  {col:<18}-> {kind}{note}")
    print(f"{bar}\n")