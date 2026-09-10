"""Unit tests (T043): the pushdown lookup correctly distinguishes all three outcomes
(found / field_missing / document_not_found, FR-012) given controlled fixture data.
Exercises `lookup_xml_field`'s branching logic against a scripted fake SQLAlchemy
engine/connection (no live MS SQL Server needed) so the exact
EXISTS-then-.value() decision path is unit-testable in isolation; the live-data
equivalent lives in tests/integration/test_xml_lookup_live.py (T045).
"""

import pytest

from src.services import xml_lookup_service
from src.services.xml_lookup_service import (
    XmlFieldNotConfiguredError,
    find_field_path,
    lookup_xml_field,
)

FIELD_PATHS = [
    {
        "legacy_column": "collateral_value_cents",
        "xpath": "(/Application/CollateralValue)[1]",
        "cast_type": "BIGINT",
    },
    {
        "legacy_column": "underwriting_score",
        "xpath": "(/Application/UnderwritingScore)[1]",
        "cast_type": "INT",
    },
]


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeConnection:
    def __init__(self, scalars):
        self._scalars = iter(scalars)

    def execute(self, *_args, **_kwargs):
        return _FakeResult(next(self._scalars))

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeEngine:
    def __init__(self, scalars):
        self._scalars = scalars

    def connect(self):
        return _FakeConnection(self._scalars)


def _patch_engine(monkeypatch, scalars):
    monkeypatch.setattr(
        xml_lookup_service, "build_engine", lambda _connection: _FakeEngine(scalars)
    )


def test_found_when_document_exists_and_value_extracted(monkeypatch):
    # First scalar: EXISTS check (1 = document exists). Second: the extracted value.
    _patch_engine(monkeypatch, [1, "32000000"])
    result = lookup_xml_field(
        connection=object(),
        xml_table_name="dbo.legacy_application_xml",
        xml_identity_column="application_id",
        xml_payload_column="xml_payload",
        identity="1",
        legacy_column="collateral_value_cents",
        field_paths=FIELD_PATHS,
    )
    assert result.outcome == "found"
    assert result.value == "32000000"


def test_field_missing_when_document_exists_but_value_is_null(monkeypatch):
    _patch_engine(monkeypatch, [1, None])
    result = lookup_xml_field(
        connection=object(),
        xml_table_name="dbo.legacy_application_xml",
        xml_identity_column="application_id",
        xml_payload_column="xml_payload",
        identity="5",
        legacy_column="collateral_value_cents",
        field_paths=FIELD_PATHS,
    )
    assert result.outcome == "field_missing"
    assert result.value is None


def test_document_not_found_when_no_row_for_identity(monkeypatch):
    # Only one scalar returned: the EXISTS check short-circuits before any .value() call.
    _patch_engine(monkeypatch, [0])
    result = lookup_xml_field(
        connection=object(),
        xml_table_name="dbo.legacy_application_xml",
        xml_identity_column="application_id",
        xml_payload_column="xml_payload",
        identity="10",
        legacy_column="collateral_value_cents",
        field_paths=FIELD_PATHS,
    )
    assert result.outcome == "document_not_found"
    assert result.value is None


def test_find_field_path_raises_when_no_entry_configured_for_the_column():
    with pytest.raises(XmlFieldNotConfiguredError):
        find_field_path(FIELD_PATHS, "applicant_email")


def test_lookup_raises_before_touching_the_connection_when_column_not_configured(monkeypatch):
    # No scalars provided at all — if the implementation tried to open a connection
    # before checking field_paths, this would raise StopIteration instead.
    _patch_engine(monkeypatch, [])
    with pytest.raises(XmlFieldNotConfiguredError):
        lookup_xml_field(
            connection=object(),
            xml_table_name="dbo.legacy_application_xml",
            xml_identity_column="application_id",
            xml_payload_column="xml_payload",
            identity="1",
            legacy_column="applicant_email",
            field_paths=FIELD_PATHS,
        )
