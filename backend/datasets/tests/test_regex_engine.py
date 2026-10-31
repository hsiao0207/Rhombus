"""
Unit tests for the regex engine: replacement semantics, statistics, and rejection of
invalid, empty-matching or catastrophically slow patterns.
"""

import pandas as pd
import pytest

from datasets.exceptions import InvalidRegex, InvalidReplacement, PatternMatchesEmpty, RegexTimeout
from datasets.services import regex_engine
from datasets.services.regex_engine import CellChange

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"


@pytest.fixture
def people():
    return pd.DataFrame(
        {
            "ID": ["1", "2", "3"],
            "Name": ["John Doe", "Jane Smith", "Alice Brown"],
            "Email": ["john.doe@example.com", "jane_smith@domain.com", "alice.brown@website.org"],
        }
    )


def replace(df, pattern, replacement, columns, flags=None, **kwargs):
    compiled = regex_engine.compile_pattern(pattern, flags)
    return regex_engine.replace_in_columns(
        df, compiled, replacement, columns, timeout_seconds=kwargs.pop("timeout", 5), **kwargs
    )


def test_redacts_emails_like_the_spec_example(people):
    result = replace(people, EMAIL_PATTERN, "REDACTED", ["Email"])

    assert result.data["Email"].tolist() == ["REDACTED"] * 3
    assert result.data["Name"].tolist() == people["Name"].tolist()
    assert result.stats == {
        "total_matches": 3,
        "total_cells_changed": 3,
        "rows_affected": 3,
        "rows_scanned": 3,
        "columns": {"Email": {"matches": 3, "cells_changed": 3}},
    }


def test_does_not_mutate_input(people):
    replace(people, EMAIL_PATTERN, "REDACTED", ["Email"])
    assert people["Email"].iloc[0] == "john.doe@example.com"


def test_replaces_only_the_matched_part():
    df = pd.DataFrame({"note": ["call 555-1234 now", "no number"]})
    result = replace(df, r"\d{3}-\d{4}", "XXX-XXXX", ["note"])
    assert result.data["note"].tolist() == ["call XXX-XXXX now", "no number"]
    assert result.rows_affected == 1


def test_backreferences_in_replacement():
    df = pd.DataFrame({"date": ["2024-01-31", "1999-12-01"]})
    result = replace(df, r"(\d{4})-(\d{2})-(\d{2})", r"\3/\2/\1", ["date"])
    assert result.data["date"].tolist() == ["31/01/2024", "01/12/1999"]


def test_ignorecase_flag():
    df = pd.DataFrame({"t": ["Apple", "apple", "APPLE"]})
    result = replace(df, "apple", "fruit", ["t"], flags=["IGNORECASE"])
    assert result.data["t"].tolist() == ["fruit"] * 3


def test_nulls_are_preserved_and_not_counted():
    df = pd.DataFrame({"t": ["a1", None, "b2"]})
    result = replace(df, r"\d", "#", ["t"])
    assert result.data["t"].iloc[0] == "a#"
    assert pd.isna(result.data["t"].iloc[1])
    assert result.cells_changed == {"t": 2}


def test_match_count_accounts_for_repeated_values():
    df = pd.DataFrame({"t": ["x-x", "x-x", "y"]})
    result = replace(df, "x", "z", ["t"])
    assert result.matches == {"t": 4}
    assert result.cells_changed == {"t": 2}


def test_samples_are_row_major_and_limited():
    df = pd.DataFrame({"a": ["1", "2", "3"], "b": ["4", "5", "6"]})
    result = replace(df, r"\d", "#", ["a", "b"], sample_size=3)
    assert result.samples == [
        CellChange(row=0, column="a", before="1", after="#"),
        CellChange(row=0, column="b", before="4", after="#"),
        CellChange(row=1, column="a", before="2", after="#"),
    ]


def test_invalid_regex_reports_position():
    with pytest.raises(InvalidRegex) as exc:
        regex_engine.compile_pattern(r"abc(def")
    assert exc.value.details["position"] is not None


@pytest.mark.parametrize("pattern", [r"\d*", r"x?", r"^", r"(a|)"])
def test_patterns_matching_empty_text_are_rejected(pattern):
    with pytest.raises(PatternMatchesEmpty):
        regex_engine.compile_pattern(pattern)


def test_invalid_group_reference_in_replacement():
    df = pd.DataFrame({"t": ["abc"]})
    with pytest.raises(InvalidReplacement):
        replace(df, "b", r"\2", ["t"])


def test_catastrophic_backtracking_times_out():
    df = pd.DataFrame({"t": ["a" * 40 + "!"]})
    with pytest.raises(RegexTimeout):
        replace(df, r"(a|aa)+$", "", ["t"], timeout=0.1)


def test_per_cell_limit_stops_catastrophic_backtracking_within_a_long_budget():
    df = pd.DataFrame({"t": ["a" * 40 + "!"]})
    with pytest.raises(RegexTimeout):
        replace(df, r"(a|aa)+$", "", ["t"], timeout=600, cell_timeout_seconds=0.1)


def test_batches_give_the_same_result_as_one_pass():
    df = pd.DataFrame({"t": ["a1", "b", "c3", "a1", None, "d4", "e"]})
    compiled = regex_engine.compile_pattern(r"\d")
    replacer = regex_engine.Replacer(compiled, "#", ["t"], timeout_seconds=5, sample_size=3)

    batches = [replacer.process(df.iloc[i : i + 3]) for i in range(0, len(df), 3)]

    one_pass = replace(df, r"\d", "#", ["t"], sample_size=3)
    pd.testing.assert_series_equal(pd.concat(batches)["t"], one_pass.data["t"])
    assert replacer.result.stats == one_pass.stats
    # Sample rows are numbered across the whole dataset, not within each batch.
    assert [sample.row for sample in replacer.result.samples] == [0, 2, 3]
