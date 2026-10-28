"""
Reading uploaded spreadsheets and persisting them as Parquet.

Design notes:
- Every column is read as text (`dtype=str`). Type inference would turn "007" into 7,
  strip leading zeros from phone numbers and render integer columns with gaps as "1.0".
  Regex replacement works on text, so the original representation must be preserved.
- Column kinds ("text" / "numeric") are inferred separately as metadata only.
- Processed data is stored as Parquet: compact, fast to read back and null-preserving.
- All file access goes through Django's storage API so the backend can move to S3
  without code changes.
"""

import io
from dataclasses import dataclass
from pathlib import PurePath
from typing import IO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from datasets.exceptions import EmptyFile, FileParseError, UnsupportedFileType

SUPPORTED_EXTENSIONS = {".csv": "csv", ".xlsx": "xlsx"}
CSV_ENCODINGS = ("utf-8-sig", "latin-1")  # latin-1 never fails, so it is the fallback.


@dataclass(frozen=True)
class Page:
    columns: list[str]
    rows: list[list[str | None]]
    total_rows: int


def detect_format(filename: str) -> str:
    extension = PurePath(filename).suffix.lower()
    try:
        return SUPPORTED_EXTENSIONS[extension]
    except KeyError:
        raise UnsupportedFileType(details={"extension": extension or None}) from None


def read_tabular(file: IO[bytes], file_format: str) -> pd.DataFrame:
    """Parse an uploaded CSV/XLSX file into a DataFrame of strings."""
    try:
        if file_format == "csv":
            df = _read_csv(file)
        else:
            df = pd.read_excel(file, dtype=str, engine="openpyxl")
    except pd.errors.EmptyDataError:
        raise EmptyFile() from None
    except FileParseError:
        raise
    except Exception as exc:
        # Parsers raise many exception types on malformed input (BadZipFile, KeyError,
        # ParserError, ...). Any failure here means the user's file is unreadable.
        raise FileParseError(details={"reason": str(exc)}) from exc

    if df.columns.empty:
        raise EmptyFile()
    return _normalize_columns(df)


def _read_csv(file: IO[bytes]) -> pd.DataFrame:
    for encoding in CSV_ENCODINGS:
        file.seek(0)
        try:
            return pd.read_csv(file, dtype=str, encoding=encoding, keep_default_na=True)
        except UnicodeDecodeError:
            continue
    raise FileParseError("Could not decode the CSV file.")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure column names are non-empty, unique strings (Parquet requires this)."""
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(df.columns):
        name = str(raw).strip()
        if not name or name.startswith("Unnamed:"):
            name = f"column_{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    df.columns = names
    return df


def infer_column_kinds(df: pd.DataFrame) -> list[dict[str, str]]:
    """Label each column as "numeric" when every non-empty value parses as a number."""
    columns = []
    for name in df.columns:
        values = df[name].dropna()
        is_numeric = not values.empty and pd.to_numeric(values, errors="coerce").notna().all()
        columns.append({"name": name, "kind": "numeric" if is_numeric else "text"})
    return columns


def save_parquet(df: pd.DataFrame, path: str) -> str:
    """Write a DataFrame to storage as Parquet and return the stored path."""
    buffer = io.BytesIO()
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, buffer, compression="zstd")
    return default_storage.save(path, ContentFile(buffer.getvalue()))


def read_dataframe(path: str) -> pd.DataFrame:
    """Load a stored Parquet file as a DataFrame."""
    with default_storage.open(path, "rb") as file:
        return pq.read_table(file).to_pandas()


def read_page(path: str, offset: int, limit: int) -> Page:
    """Read a slice of rows from a stored Parquet file."""
    with default_storage.open(path, "rb") as file:
        table = pq.read_table(file)
    page = table.slice(offset, limit).to_pandas()
    rows = page.astype(object).where(page.notna(), None).values.tolist()
    return Page(columns=list(table.column_names), rows=rows, total_rows=table.num_rows)
