"""
Unit tests for file parsing, column normalization, kind inference and Parquet storage,
including batch-by-batch processing of files larger than one batch.
"""

import io

import pandas as pd
import pyarrow.parquet as pq
import pytest
from django.core.files.storage import default_storage

from datasets.exceptions import EmptyFile, UnsupportedFileType
from datasets.services import file_io


@pytest.fixture
def small_batches(monkeypatch):
    """Use 2-row batches so small test files span several batches and row groups."""
    monkeypatch.setattr(file_io, "ROWS_PER_BATCH", 2)


def store_csv(data: bytes) -> file_io.StoredTable:
    return file_io.store_upload(io.BytesIO(data), "csv", "test/upload.parquet")


def read_csv(data: bytes) -> pd.DataFrame:
    return file_io.read_head(store_csv(data).path, 1000)


def test_detect_format_is_case_insensitive():
    assert file_io.detect_format("Data.CSV") == "csv"
    assert file_io.detect_format("report.xlsx") == "xlsx"


@pytest.mark.parametrize("name", ["notes.txt", "legacy.xls", "no_extension"])
def test_detect_format_rejects_unsupported(name):
    with pytest.raises(UnsupportedFileType):
        file_io.detect_format(name)


def test_read_csv_preserves_text_representation():
    df = read_csv(b"code,phone,amount\n007,0912345678,1\n010,,2\n")
    assert df["code"].tolist() == ["007", "010"]
    assert df["phone"].iloc[0] == "0912345678"
    assert pd.isna(df["phone"].iloc[1])
    assert df["amount"].tolist() == ["1", "2"]


def test_read_csv_falls_back_to_latin1():
    df = read_csv("name\nJos\xe9\n".encode("latin-1"))
    assert df["name"].iloc[0] == "José"


def test_latin1_fallback_restarts_when_bad_bytes_are_in_a_late_batch(small_batches):
    data = "name\nAnn\nBob\nCid\nJos\xe9\n".encode("latin-1")  # é is in the second batch

    table = store_csv(data)

    assert table.row_count == 4
    assert file_io.read_head(table.path, 10)["name"].tolist() == ["Ann", "Bob", "Cid", "José"]


def test_read_empty_csv_raises():
    with pytest.raises(EmptyFile):
        store_csv(b"")


def test_columns_are_normalized():
    # pandas itself renames exact duplicates ("a" -> "a.1"); names that only collide
    # after trimming whitespace are de-duplicated by us.
    df = read_csv(b"a,,a,b,b \n1,2,3,4,5\n")
    assert list(df.columns) == ["a", "column_2", "a.1", "b", "b_2"]


def test_infer_column_kinds():
    assert store_csv(b"id,name,empty\n1,Ann,\n2.5,Bob,\n").columns == [
        {"name": "id", "kind": "numeric"},
        {"name": "name", "kind": "text"},
        {"name": "empty", "kind": "text"},
    ]


def test_column_kinds_consider_every_batch(small_batches):
    # "code" looks numeric in the first batch only; "late" is empty until the last one.
    table = store_csv(b"code,late\n1,\n2,\n3,\nA7,9\n")

    assert table.columns == [
        {"name": "code", "kind": "text"},
        {"name": "late", "kind": "numeric"},
    ]


def test_large_csv_is_stored_as_one_row_group_per_batch(small_batches):
    table = store_csv(b"n\n" + b"".join(f"{i}\n".encode() for i in range(5)))

    assert table.row_count == 5
    with default_storage.open(table.path, "rb") as file:
        assert pq.ParquetFile(file).num_row_groups == 3
    assert [len(batch) for batch in file_io.iter_batches(table.path)] == [2, 2, 1]


def test_header_only_csv_keeps_its_columns():
    table = store_csv(b"a,b\n")

    assert table.row_count == 0
    assert [column["name"] for column in table.columns] == ["a", "b"]
    [batch] = file_io.iter_batches(table.path)
    assert list(batch.columns) == ["a", "b"]


def test_parquet_round_trip_and_paging():
    df = pd.DataFrame({"n": [str(i) for i in range(10)], "s": ["x"] * 9 + [None]})
    path = file_io.write_parquet([df], "test/data.parquet").path

    page = file_io.read_page(path, offset=8, limit=5)
    assert page.total_rows == 10
    assert page.columns == ["n", "s"]
    assert page.rows == [["8", "x"], ["9", None]]


@pytest.mark.parametrize(
    ("offset", "limit", "expected"),
    [
        (0, 2, ["0", "1"]),  # exactly one row group
        (1, 3, ["1", "2", "3"]),  # spans two row groups
        (4, 10, ["4"]),  # last, partial row group
        (9, 5, []),  # past the end
    ],
)
def test_paging_across_row_groups(small_batches, offset, limit, expected):
    table = store_csv(b"n\n" + b"".join(f"{i}\n".encode() for i in range(5)))

    page = file_io.read_page(table.path, offset=offset, limit=limit)

    assert page.total_rows == 5
    assert [row[0] for row in page.rows] == expected
