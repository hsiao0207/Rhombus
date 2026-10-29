"""Unit tests for file parsing, column normalization, kind inference and Parquet storage."""

import io

import pandas as pd
import pytest

from datasets.exceptions import EmptyFile, UnsupportedFileType
from datasets.services import file_io


def test_detect_format_is_case_insensitive():
    assert file_io.detect_format("Data.CSV") == "csv"
    assert file_io.detect_format("report.xlsx") == "xlsx"


@pytest.mark.parametrize("name", ["notes.txt", "legacy.xls", "no_extension"])
def test_detect_format_rejects_unsupported(name):
    with pytest.raises(UnsupportedFileType):
        file_io.detect_format(name)


def test_read_csv_preserves_text_representation():
    csv = b"code,phone,amount\n007,0912345678,1\n010,,2\n"
    df = file_io.read_tabular(io.BytesIO(csv), "csv")
    assert df["code"].tolist() == ["007", "010"]
    assert df["phone"].iloc[0] == "0912345678"
    assert pd.isna(df["phone"].iloc[1])
    assert df["amount"].tolist() == ["1", "2"]


def test_read_csv_falls_back_to_latin1():
    df = file_io.read_tabular(io.BytesIO("name\nJos\xe9\n".encode("latin-1")), "csv")
    assert df["name"].iloc[0] == "José"


def test_read_empty_csv_raises():
    with pytest.raises(EmptyFile):
        file_io.read_tabular(io.BytesIO(b""), "csv")


def test_columns_are_normalized():
    # pandas itself renames exact duplicates ("a" -> "a.1"); names that only collide
    # after trimming whitespace are de-duplicated by us.
    df = file_io.read_tabular(io.BytesIO(b"a,,a,b,b \n1,2,3,4,5\n"), "csv")
    assert list(df.columns) == ["a", "column_2", "a.1", "b", "b_2"]


def test_infer_column_kinds():
    df = file_io.read_tabular(io.BytesIO(b"id,name,empty\n1,Ann,\n2.5,Bob,\n"), "csv")
    assert file_io.infer_column_kinds(df) == [
        {"name": "id", "kind": "numeric"},
        {"name": "name", "kind": "text"},
        {"name": "empty", "kind": "text"},
    ]


def test_parquet_round_trip_and_paging():
    df = pd.DataFrame({"n": [str(i) for i in range(10)], "s": ["x"] * 9 + [None]})
    path = file_io.save_parquet(df, "test/data.parquet")

    page = file_io.read_page(path, offset=8, limit=5)
    assert page.total_rows == 10
    assert page.columns == ["n", "s"]
    assert page.rows == [["8", "x"], ["9", None]]
