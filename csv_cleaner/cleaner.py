"""Core cleaning logic for the Smart CSV Data Cleaner."""

from __future__ import annotations

import csv
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Extra strings to treat as "missing" (pandas already handles "", "NA", "N/A", "null", "NaN", etc.)
EXTRA_NA_VALUES = ["-", "--", "?", "n/a", "missing"]

ENCODINGS_TO_TRY = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
DATE_NAME_HINTS = ("date", "time", "dob", "_dt")


@dataclass
class CleanerConfig:
    """All user-tunable behaviour lives here, not scattered through the code."""
    strategy: str = "fill"
    fill_method: str = "median"
    drop_subset: list[str] | None = None
    delimiter: str | None = None          # None = auto-detect
    encoding: str | None = None           # None = auto-detect
    convert_types: bool = True
    date_columns: list[str] | None = None # None = guess from column names
    dayfirst: bool = False                # True for dd/mm/yyyy data
    keep_integers: bool = True            # 34.0 -> 34

    def __post_init__(self):
        if self.strategy not in {"fill", "drop"}:
            raise ValueError(f"strategy must be 'fill' or 'drop', got {self.strategy!r}")
        if self.fill_method not in {"mean", "median"}:
            raise ValueError(f"fill_method must be 'mean' or 'median', got {self.fill_method!r}")


@dataclass
class CleaningReport:
    """Collects the numbers the console summary needs."""
    encoding: str = ""
    delimiter: str = ""
    converted_types: dict[str, str] = field(default_factory=dict)   # column -> "numeric" / "date"
    unparseable_dates: dict[str, int] = field(default_factory=dict)
    rows_before: int = 0
    rows_after: int = 0
    duplicates_removed: int = 0
    rows_dropped_missing: int = 0
    renamed_columns: dict[str, str] = field(default_factory=dict)
    missing_before: pd.Series = field(default_factory=lambda: pd.Series(dtype="int64"))
    missing_after: pd.Series = field(default_factory=lambda: pd.Series(dtype="int64"))
    filled: dict[str, int] = field(default_factory=dict)


# ---------- 1. Load & inspect ----------

def detect_encoding(raw: bytes) -> str:
    """Return the first encoding that decodes the whole file without error."""
    for enc in ENCODINGS_TO_TRY:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"  # decodes anything, so this is the safe last resort


def detect_delimiter(text: str) -> str:
    """Guess the delimiter from a sample of the file; fall back to a comma."""
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def load_csv(
    path: str | Path, config: CleanerConfig | None = None
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load a raw CSV, auto-detecting encoding and delimiter unless the config overrides them."""
    config = config or CleanerConfig()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError(f"Input file is empty: {path}")

    encoding = config.encoding or detect_encoding(raw)
    delimiter = config.delimiter or detect_delimiter(raw.decode(encoding))

    df = pd.read_csv(path, sep=delimiter, encoding=encoding, na_values=EXTRA_NA_VALUES)
    return df, {"encoding": encoding, "delimiter": delimiter}


def inspect_dataframe(df: pd.DataFrame) -> None:
    """Print a quick look at the raw data before touching it."""
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")
    print("Column types:")
    print(df.dtypes.to_string(), "\n")
    print("First rows:")
    print(df.head().to_string(), "\n")
    print(f"Exact duplicate rows (before cleaning): {df.duplicated().sum()}\n")


# ---------- 2. Column names ----------

def standardize_column_name(name: object) -> str:
    """'  First Name ' -> 'first_name', 'E-mail Address' -> 'e_mail_address'."""
    name = str(name).strip().lower()
    name = re.sub(r"[^0-9a-z]+", "_", name)   # anything non-alphanumeric becomes "_"
    return name.strip("_")


def clean_column_names(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Standardize all column names, guaranteeing uniqueness."""
    new_names, seen = [], {}
    for col in df.columns:
        base = standardize_column_name(col) or "unnamed"
        count = seen.get(base, 0)
        seen[base] = count + 1
        new_names.append(base if count == 0 else f"{base}_{count}")

    mapping = dict(zip(df.columns, new_names))
    df = df.copy()
    df.columns = new_names
    return df, mapping


# ---------- 3. Strings ----------

def clean_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from text columns and turn empty strings into real missing values."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].str.strip().replace("", np.nan)
    return df
# ---------- 3b. Type detection ----------

def _to_numeric_if_clean(series: pd.Series) -> pd.Series | None:
    """Convert a text column to numbers only if EVERY non-missing value parses."""
    stripped = series.astype("string").str.replace(r"[$€£,\s]", "", regex=True)
    converted = pd.to_numeric(stripped, errors="coerce")
    if series.notna().sum() > 0 and converted.notna().sum() == series.notna().sum():
        return converted
    return None


def convert_types(df: pd.DataFrame, config: CleanerConfig) -> tuple[pd.DataFrame, dict, dict]:
    """Turn numeric-looking text into numbers and date-looking columns into datetimes."""
    df = df.copy()
    converted: dict[str, str] = {}
    bad_dates: dict[str, int] = {}

    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]) and df[col].dtype != object:
            continue

        is_date_col = (
            col in config.date_columns
            if config.date_columns is not None
            else any(hint in col for hint in DATE_NAME_HINTS)
        )

        if is_date_col:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(
                    df[col], errors="coerce", dayfirst=config.dayfirst, format="mixed"
                )
            failed = int(parsed.isna().sum() - df[col].isna().sum())
            if parsed.notna().sum() > 0:
                df[col] = parsed
                converted[col] = "date"
                if failed:
                    bad_dates[col] = failed
            continue

        numeric = _to_numeric_if_clean(df[col])
        if numeric is not None:
            df[col] = numeric
            converted[col] = "numeric"

    return df, converted, bad_dates


def restore_integers(df: pd.DataFrame) -> pd.DataFrame:
    """Float columns whose values are all whole numbers become nullable integers."""
    df = df.copy()
    for col in df.select_dtypes(include="float").columns:
        values = df[col].dropna()
        if len(values) and (values % 1 == 0).all():
            df[col] = df[col].astype("Int64")
    return df

# ---------- 4. Missing values ----------

def handle_missing(
    df: pd.DataFrame, config: CleanerConfig
) -> tuple[pd.DataFrame, int, dict[str, int]]:
    """Return (cleaned_df, rows_dropped, {column: values_filled})."""
    if config.strategy == "drop":
        before = len(df)
        df = df.dropna(subset=config.drop_subset).reset_index(drop=True)
        return df, before - len(df), {}

    df = df.copy()
    filled: dict[str, int] = {}
    for col in df.select_dtypes(include="number").columns:
        n_missing = int(df[col].isna().sum())
        if n_missing == 0:
            continue
        value = df[col].median() if config.fill_method == "median" else df[col].mean()
        df[col] = df[col].fillna(value)
        filled[col] = n_missing
    return df, 0, filled


# ---------- 5. The pipeline ----------

def clean_dataframe(
    df: pd.DataFrame, config: CleanerConfig | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    """Run the full cleaning pipeline and return (clean_df, report)."""
    config = config or CleanerConfig()
    report = CleaningReport(rows_before=len(df))

    df, report.renamed_columns = clean_column_names(df)
    df = clean_string_columns(df)
    if config.convert_types:
        df, report.converted_types, report.unparseable_dates = convert_types(df, config)

    rows = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    report.duplicates_removed = rows - len(df)

    report.missing_before = df.isna().sum()
    df, report.rows_dropped_missing, report.filled = handle_missing(df, config)
    if config.keep_integers:
        df = restore_integers(df)
    report.missing_after = df.isna().sum()
    report.rows_after = len(df)
    return df, report