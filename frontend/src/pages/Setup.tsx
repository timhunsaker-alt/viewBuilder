import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../services/api";

type AuthMode = "sql" | "windows_integrated";

interface ConnectionOut {
  id: string;
  name: string;
  role: "source" | "target" | "either";
  environment: "dev" | "test" | "prod";
  host: string;
  port: number;
  database: string;
  auth_mode: AuthMode;
  username: string | null;
}

interface ConnectionCreateBody {
  name: string;
  role: string;
  environment: string;
  host: string;
  port: number;
  database: string;
  auth_mode: AuthMode;
  username?: string;
  credential_ref?: string;
}

const LockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="4" y="10" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

/**
 * Connection setup screen: create a `connection_config`, choosing between a SQL Server
 * login (username + a secret reference resolved server-side, Constitution Principle VI
 * — the raw secret itself is never round-tripped through this form's own state after
 * submit) or on-prem Windows Integrated Security (the backend's own Windows/AD service
 * identity — see research.md §6 for why true per-end-user Kerberos delegation isn't
 * offered here). This is the "no frontend form for creating a connection yet" gap
 * flagged in quickstart.md — the golden path previously required a raw curl call.
 */
export function Setup() {
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [role, setRole] = useState("either");
  const [environment, setEnvironment] = useState("dev");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("1433");
  const [database, setDatabase] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("sql");
  const [username, setUsername] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [error, setError] = useState<string | null>(null);

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<ConnectionOut[]>("/connections"),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const body: ConnectionCreateBody = {
        name,
        role,
        environment,
        host,
        port: Number(port) || 1433,
        database,
        auth_mode: authMode,
      };
      if (authMode === "sql") {
        body.username = username;
        body.credential_ref = credentialRef;
      }
      return api.post<ConnectionOut>("/connections", body);
    },
    onSuccess: () => {
      setError(null);
      setName("");
      setHost("");
      setDatabase("");
      setUsername("");
      setCredentialRef("");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not create the connection");
    },
  });

  const canSubmit =
    name.trim().length > 0 &&
    host.trim().length > 0 &&
    database.trim().length > 0 &&
    (authMode === "windows_integrated" ||
      (username.trim().length > 0 && credentialRef.trim().length > 0));

  return (
    <main>
      <div className="setup-hero">
        <div className="setup-hero__eyebrow">
          <LockIcon /> Secure connection setup
        </div>
        <h1>Connect a SQL Server database</h1>
        <p>
          Register a source or target connection for viewBuilder. Credentials are resolved
          server-side and never returned by the API once saved — see{" "}
          <Link to="/" style={{ color: "#cfe0ff", textDecoration: "underline" }}>
            the table picker
          </Link>{" "}
          once a connection exists.
        </p>
      </div>

      {error && <div className="setup-banner setup-banner--error">{error}</div>}
      {createMutation.isSuccess && (
        <div className="setup-banner setup-banner--success">
          Connection saved. It's ready to use from the table picker.
        </div>
      )}

      <div className="setup-card">
        <h2>1. Connection details</h2>
        <p className="setup-card__hint">
          A name to identify this connection, and where the database actually lives.
        </p>

        <div className="setup-field">
          <label htmlFor="setup-name">Connection name</label>
          <input
            id="setup-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Core Banking — Production"
          />
        </div>

        <div className="setup-field-row">
          <div className="setup-field">
            <label htmlFor="setup-role">Role</label>
            <select id="setup-role" value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="either">Either (source or target)</option>
              <option value="source">Source only</option>
              <option value="target">Target only</option>
            </select>
          </div>
          <div className="setup-field">
            <label htmlFor="setup-environment">Environment</label>
            <select
              id="setup-environment"
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              <option value="dev">Development</option>
              <option value="test">Test</option>
              <option value="prod">Production</option>
            </select>
          </div>
        </div>

        <div className="setup-field-row">
          <div className="setup-field">
            <label htmlFor="setup-host">Host</label>
            <input
              id="setup-host"
              value={host}
              onChange={(event) => setHost(event.target.value)}
              placeholder="sql.internal.example.com"
            />
          </div>
          <div className="setup-field">
            <label htmlFor="setup-port">Port</label>
            <input
              id="setup-port"
              value={port}
              onChange={(event) => setPort(event.target.value)}
              inputMode="numeric"
            />
          </div>
        </div>

        <div className="setup-field">
          <label htmlFor="setup-database">Database</label>
          <input
            id="setup-database"
            value={database}
            onChange={(event) => setDatabase(event.target.value)}
            placeholder="master"
          />
        </div>
      </div>

      <div className="setup-card">
        <h2>2. Authentication</h2>
        <p className="setup-card__hint">
          How the backend authenticates to this database. Every action taken through viewBuilder is
          still attributed to the operator who performed it in the audit log, regardless of which
          mode a connection uses.
        </p>

        <div className="setup-auth-toggle">
          <button
            type="button"
            className="setup-auth-option"
            data-selected={authMode === "sql"}
            onClick={() => setAuthMode("sql")}
          >
            <strong>SQL Login</strong>
            <span>A dedicated SQL Server username and password.</span>
          </button>
          <button
            type="button"
            className="setup-auth-option"
            data-selected={authMode === "windows_integrated"}
            onClick={() => setAuthMode("windows_integrated")}
          >
            <strong>Windows Integrated</strong>
            <span>The backend's own Windows/AD service identity — no secret to store.</span>
          </button>
        </div>

        {authMode === "sql" ? (
          <div className="setup-field-row">
            <div className="setup-field">
              <label htmlFor="setup-username">SQL login username</label>
              <input
                id="setup-username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="svc_viewbuilder"
              />
            </div>
            <div className="setup-field">
              <label htmlFor="setup-credential-ref">Credential reference</label>
              <input
                id="setup-credential-ref"
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder="an opaque name resolved server-side, not the password itself"
              />
            </div>
          </div>
        ) : (
          <p className="setup-card__hint" style={{ marginBottom: 0 }}>
            Requires the backend host to be domain-joined with the SQL Server ODBC driver's
            <code> Trusted_Connection</code> path available — this is a single fixed service-account
            identity, not per-user delegation.
          </p>
        )}

        <div className="setup-trust-row">
          <LockIcon /> Credentials are never returned by the API once a connection is saved.
        </div>

        <div className="setup-actions">
          <button
            type="button"
            disabled={!canSubmit || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? "Saving…" : "Save connection"}
          </button>
        </div>
      </div>

      <div className="setup-card">
        <h2>Existing connections</h2>
        {connectionsQuery.data && connectionsQuery.data.length === 0 && (
          <p className="setup-card__hint">None yet — the one you save above will show up here.</p>
        )}
        {connectionsQuery.data && connectionsQuery.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Environment</th>
                <th>Auth</th>
                <th>Host</th>
              </tr>
            </thead>
            <tbody>
              {connectionsQuery.data.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.environment}</td>
                  <td>
                    {c.auth_mode === "windows_integrated" ? "Windows Integrated" : "SQL Login"}
                  </td>
                  <td>
                    {c.host}:{c.port}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
