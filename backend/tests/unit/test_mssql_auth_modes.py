"""Unit tests: `build_engine` constructs the right ODBC connection string for each
`auth_mode` — `windows_integrated` uses `Trusted_Connection=yes` with no UID/PWD at
all (on-prem Windows Integrated Security via the backend's own Windows/AD identity,
research.md §6), while `sql` uses the real `username` field (falling back to
`credential_ref` only for rows created before `username` existed) plus the resolved
secret. `create_engine` never actually opens a connection, so this needs no live
database — the ODBC string is inspectable straight off the returned engine's URL.
"""

from urllib.parse import unquote_plus, urlparse

import pytest

from src.connectors.mssql import ConnectionUnreachableError, build_engine


class _FakeConnection:
    """Duck-types just the attributes build_engine reads off a ConnectionConfig."""

    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "test-connection")
        self.host = kwargs.get("host", "sqlhost")
        self.port = kwargs.get("port", 1433)
        self.database = kwargs.get("database", "mydb")
        self.auth_mode = kwargs.get("auth_mode", "sql")
        self.username = kwargs.get("username")
        self.credential_ref = kwargs.get("credential_ref")


def _odbc_params(engine) -> str:
    query = urlparse(str(engine.url)).query
    # query is like "odbc_connect=<url-encoded odbc string>"
    encoded = query.split("odbc_connect=", 1)[1]
    return unquote_plus(encoded)


def test_windows_integrated_uses_trusted_connection_with_no_credentials():
    connection = _FakeConnection(auth_mode="windows_integrated")
    engine = build_engine(connection)
    odbc_str = _odbc_params(engine)

    assert "Trusted_Connection=yes;" in odbc_str
    assert "UID=" not in odbc_str
    assert "PWD=" not in odbc_str
    assert "SERVER=sqlhost,1433;" in odbc_str
    assert "DATABASE=mydb;" in odbc_str


def test_windows_integrated_ignores_leftover_username_or_credential_ref():
    # Defensive: even if a row somehow has stale username/credential_ref values (e.g.
    # after switching an existing connection's auth_mode), windows_integrated mode
    # must never emit them.
    connection = _FakeConnection(
        auth_mode="windows_integrated", username="leftover", credential_ref="leftover-ref"
    )
    odbc_str = _odbc_params(build_engine(connection))
    assert "leftover" not in odbc_str
    assert "UID=" not in odbc_str


def test_sql_auth_uses_real_username_field(monkeypatch):
    monkeypatch.setenv("VIEWBUILDER_CRED_MYSECRET", "s3cret-password")
    connection = _FakeConnection(
        auth_mode="sql", username="svc_viewbuilder", credential_ref="mysecret"
    )
    odbc_str = _odbc_params(build_engine(connection))
    assert "UID=svc_viewbuilder;" in odbc_str
    assert "PWD=s3cret-password;" in odbc_str


def test_sql_auth_falls_back_to_credential_ref_as_username_when_username_unset(monkeypatch):
    # Backward compatibility: rows created before `username` existed used
    # credential_ref as the literal login name.
    monkeypatch.setenv("VIEWBUILDER_CRED_LEGACYLOGIN", "s3cret-password")
    connection = _FakeConnection(auth_mode="sql", username=None, credential_ref="legacylogin")
    odbc_str = _odbc_params(build_engine(connection))
    assert "UID=legacylogin;" in odbc_str


def test_sql_auth_without_credential_ref_raises():
    connection = _FakeConnection(auth_mode="sql", username="someone", credential_ref=None)
    with pytest.raises(ConnectionUnreachableError):
        build_engine(connection)
