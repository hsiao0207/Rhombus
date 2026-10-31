"""
Reading uploaded spreadsheets and persisting them as Parquet.

Design notes:
- Every column is read as text (`dtype=str`). Type inference would turn "007" into 7,
  strip leading zeros from phone numbers and render integer columns with gaps as "1.0".
  Regex replacement works on text, so the original representation must be preserved.
- Column kinds ("text" / "numeric") are inferred separately as metadata only.
- Processed data is stored as Parquet: compact, fast to read back and null-preserving.
- Large files are handled in batches of `ROWS_PER_BATCH` rows: CSV uploads are parsed,
  transformations are applied and Parquet is written one batch at a time, and each batch
  is stored as its own row group so a page of rows can be read without loading the rest.
  Memory use therefore depends on the batch size, not the file size. (Excel files are
  still parsed in one go; openpyxl cannot stream them with pandas' conversions.)
- All file access goes through Django's storage API so the backend can move to S3
  without code changes.
"""

import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import IO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from django.core.files import File
from django.core.files.storage import default_storage

from datasets.exceptions import EmptyFile, FileParseError, UnsupportedFileType

SUPPORTED_EXTENSIONS = {".csv": "csv", ".xlsx": "xlsx"}
CSV_ENCODINGS = ("utf-8-sig", "latin-1")  # latin-1 never fails, so it is the fallback.
ROWS_PER_BATCH = 50_000


@dataclass(frozen=True)
class Page:
    columns: list[str]
    rows: list[list[str | None]]
    total_rows: int


@dataclass(frozen=True)
class StoredTable:
    """A Parquet file written to storage, with the metadata a version needs."""

    path: str
    row_count: int
    columns: list[dict[str, str]]


def detect_format(filename: str) -> str:
    extension = PurePath(filename).suffix.lower()
    try:
        return SUPPORTED_EXTENSIONS[extension]
    except KeyError:
        raise UnsupportedFileType(details={"extension": extension or None}) from None


def store_upload(file: IO[bytes], file_format: str, path: str) -> StoredTable:
    """Parse an uploaded CSV/XLSX file into a Parquet file of strings at `path`."""
    try:
        if file_format == "csv":
            return _store_csv(file, path)
        df = pd.read_excel(file, dtype=str, engine="openpyxl")
        if df.columns.empty:
            raise EmptyFile()
        df.columns = _normalized_names(df.columns)
        return write_parquet(_split(df), path)
    except pd.errors.EmptyDataError:
        raise EmptyFile() from None
    except (EmptyFile, FileParseError, OSError):
        raise
    except Exception as exc:
        # Parsers raise many exception types on malformed input (BadZipFile, KeyError,
        # ParserError, ...). Any failure here means the user's file is unreadable.
        raise FileParseError(details={"reason": str(exc)}) from exc


def _store_csv(file: IO[bytes], path: str) -> StoredTable:
    for encoding in CSV_ENCODINGS:
        file.seek(0)
        try:
            return write_parquet(_read_csv_batches(file, encoding), path)
        except UnicodeDecodeError:
            # Undecodable bytes may only appear in a late batch, so start over from the
            # beginning with the next encoding. Nothing was saved: write_parquet only
            # stores the file once every batch has been written.
            continue
    raise FileParseError("Could not decode the CSV file.")


def _read_csv_batches(file: IO[bytes], encoding: str) -> Iterator[pd.DataFrame]:
    names = None
    with pd.read_csv(file, dtype=str, encoding=encoding, chunksize=ROWS_PER_BATCH) as reader:
        for batch in reader:
            names = names or _normalized_names(batch.columns)
            batch.columns = names
            yield batch


def _split(df: pd.DataFrame) -> Iterator[pd.DataFrame]:
    for start in range(0, max(len(df), 1), ROWS_PER_BATCH):
        yield df.iloc[start : start + ROWS_PER_BATCH]


def _normalized_names(raw_names: Iterable) -> list[str]:
    """Ensure column names are non-empty, unique strings (Parquet requires this)."""
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(raw_names):
        name = str(raw).strip()
        if not name or name.startswith("Unnamed:"):
            name = f"column_{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    return names


class _ColumnKinds:
    """Infers column kinds across batches: "numeric" when every non-empty value is a number."""

    def __init__(self) -> None:
        # None until a column has a non-empty value; then whether all values so far are numeric.
        self._numeric: dict[str, bool | None] = {}

    def update(self, batch: pd.DataFrame) -> None:
        for name in batch.columns:
            if self._numeric.setdefault(name, None) is False:
                continue
            values = batch[name].dropna()
            if not values.empty:
                self._numeric[name] = bool(pd.to_numeric(values, errors="coerce").notna().all())

    def result(self) -> list[dict[str, str]]:
        return [
            {"name": name, "kind": "numeric" if numeric else "text"}
            for name, numeric in self._numeric.items()
        ]


def infer_column_kinds(df: pd.DataFrame) -> list[dict[str, str]]:
    """Label each column as "numeric" when every non-empty value parses as a number."""
    kinds = _ColumnKinds()
    kinds.update(df)
    return kinds.result()


def write_parquet(batches: Iterable[pd.DataFrame], path: str) -> StoredTable:
    """Write DataFrame batches to storage as one Parquet file, one row group per batch.

    The file is assembled in a local temporary file and only saved to storage once
    every batch has been written, so a failure part-way leaves nothing behind.
    """
    kinds = _ColumnKinds()
    row_count = 0
    with tempfile.TemporaryFile() as tmp:
        writer = None
        try:
            for batch in batches:
                if writer is None:
                    schema = pa.schema([(name, pa.string()) for name in batch.columns])
                    writer = pq.ParquetWriter(tmp, schema, compression="zstd")
                table = pa.Table.from_pandas(batch, schema=schema, preserve_index=False)
                writer.write_table(table, row_group_size=ROWS_PER_BATCH)
                kinds.update(batch)
                row_count += len(batch)
        finally:
            if writer is not None:
                writer.close()
        if writer is None:
            raise ValueError("write_parquet needs at least one batch, even an empty one.")
        tmp.seek(0)
        stored_path = default_storage.save(path, File(tmp))
    return StoredTable(path=stored_path, row_count=row_count, columns=kinds.result())


def iter_batches(path: str, columns: list[str] | None = None) -> Iterator[pd.DataFrame]:
    """Yield a stored Parquet file as DataFrames of at most `ROWS_PER_BATCH` rows.

    `columns` limits reading to those columns (Parquet stores each one separately).
    Always yields at least one (possibly empty) batch so the columns are known.
    """
    with default_storage.open(path, "rb") as file:
        parquet = pq.ParquetFile(file)
        empty = True
        for batch in parquet.iter_batches(batch_size=ROWS_PER_BATCH, columns=columns):
            empty = False
            yield batch.to_pandas()
        if empty:
            schema = parquet.schema_arrow
            if columns is not None:
                schema = pa.schema([schema.field(name) for name in columns])
            yield schema.empty_table().to_pandas()


def read_head(path: str, limit: int) -> pd.DataFrame:
    """Read the first `limit` rows of a stored Parquet file."""
    with default_storage.open(path, "rb") as file:
        parquet = pq.ParquetFile(file)
        batch = next(parquet.iter_batches(batch_size=limit), None)
        table = batch if batch is not None else parquet.schema_arrow.empty_table()
        return table.to_pandas()


def read_page(path: str, offset: int, limit: int) -> Page:
    """Read a slice of rows, loading only the row groups that contain it."""
    with default_storage.open(path, "rb") as file:
        parquet = pq.ParquetFile(file)
        groups = []
        first_row = 0  # index of the first row of the first selected group
        start = 0
        for index in range(parquet.num_row_groups):
            end = start + parquet.metadata.row_group(index).num_rows
            if start < offset + limit and end > offset:
                if not groups:
                    first_row = start
                groups.append(index)
            start = end
        table = parquet.read_row_groups(groups) if groups else parquet.schema_arrow.empty_table()
        total_rows = parquet.metadata.num_rows

    page = table.slice(max(offset - first_row, 0), limit).to_pandas()
    rows = page.astype(object).where(page.notna(), None).values.tolist()
    return Page(columns=list(table.column_names), rows=rows, total_rows=total_rows)


def list_dirs(prefix: str) -> list[str]:
    """Names of the "directories" directly under `prefix` in storage."""
    try:
        dirs, _ = default_storage.listdir(prefix)
    except FileNotFoundError:
        return []
    return dirs


def delete_tree(prefix: str) -> None:
    """Delete every stored file under `prefix`, then its (now empty) directories."""
    try:
        dirs, files = default_storage.listdir(prefix)
    except FileNotFoundError:
        return
    for name in files:
        default_storage.delete(f"{prefix}/{name}")
    for name in dirs:
        delete_tree(f"{prefix}/{name}")
    # Removes the empty directory on local disk; object stores have no directories.
    default_storage.delete(prefix)


def latest_modified(prefix: str) -> datetime | None:
    """When the most recently changed file under `prefix` was written, if any."""
    times = [default_storage.get_modified_time(path) for path in _walk_files(prefix)]
    return max(times, default=None)


def _walk_files(prefix: str) -> Iterator[str]:
    try:
        dirs, files = default_storage.listdir(prefix)
    except FileNotFoundError:
        return
    for name in files:
        yield f"{prefix}/{name}"
    for name in dirs:
        yield from _walk_files(f"{prefix}/{name}")
