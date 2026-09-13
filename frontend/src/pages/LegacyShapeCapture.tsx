import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, type LegacyShapeCapture as LegacyShapeCaptureOut, api } from "../services/api";

interface Connection {
  id: string;
  name: string;
  environment: "dev" | "test" | "prod";
}

interface SchemaResponse {
  tables?: string[];
}

/**
 * Captures a legacy_shape_capture (FR-001): a snapshot of an old wide table's
 * column list/order/types, taken by re-introspecting the connection live. This is
 * the step that previously had no frontend form at all — a legacy shape had to be
 * created with a raw POST /legacy-shapes call before a compatibility view could
 * reference it in ViewDefinitionEditor.
 */
export function LegacyShapeCapture() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [tableName, setTableName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const tablesQuery = useQuery({
    queryKey: ["schema", connectionId],
    queryFn: () => api.get<SchemaResponse>(`/connections/${connectionId}/schema`),
    enabled: Boolean(connectionId),
  });

  const captureMutation = useMutation({
    mutationFn: () =>
      api.post<LegacyShapeCaptureOut>("/legacy-shapes", {
        name,
        connection_id: connectionId,
        table_name: tableName,
        operator: "system-operator",
      }),
    onSuccess: (result) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["legacy-shapes"] });
      navigate("/view-definitions/new", { state: { legacyShapeCaptureId: result.id } });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not capture the legacy shape");
    },
  });

  const canSubmit = name.trim().length > 0 && Boolean(connectionId) && Boolean(tableName);

  return (
    <main>
      <div className="setup-hero">
        <div className="setup-hero__eyebrow">Legacy shape capture</div>
        <h1>Capture an old table's shape</h1>
        <p>
          Snapshots the old wide table's column list, order, and types by introspecting it live —
          this is the reference shape a compatibility view's output must match. Once captured,
          continue to{" "}
          <Link
            to="/view-definitions/new"
            style={{ color: "#cfe0ff", textDecoration: "underline" }}
          >
            building the view
          </Link>
          .
        </p>
      </div>

      {error && <div className="setup-banner setup-banner--error">{error}</div>}

      <div className="setup-card">
        <h2>1. Name this shape</h2>
        <p className="setup-card__hint">
          A label for this capture — you'll pick it by name when building the compatibility view.
        </p>
        <div className="setup-field">
          <label htmlFor="shape-name">Shape name</label>
          <input
            id="shape-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. legacy loan application shape"
          />
        </div>
      </div>

      <div className="setup-card">
        <h2>2. Connection</h2>
        <p className="setup-card__hint">Which connection the old table actually lives on.</p>
        <div className="setup-field">
          <label htmlFor="shape-connection">Connection</label>
          <select
            id="shape-connection"
            value={connectionId}
            onChange={(event) => {
              setConnectionId(event.target.value);
              setTableName("");
            }}
          >
            <option value="">Select a connection…</option>
            {connectionsQuery.data?.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.name} ({connection.environment})
              </option>
            ))}
          </select>
        </div>
        {connectionsQuery.data?.length === 0 && (
          <p className="setup-card__hint">
            No connections yet — <Link to="/setup">set one up first</Link>.
          </p>
        )}
      </div>

      {connectionId && (
        <div className="setup-card">
          <h2>3. Old table</h2>
          <p className="setup-card__hint">
            The existing wide table whose exact output shape the compatibility view must reproduce.
          </p>
          <div className="setup-field">
            <label htmlFor="shape-table">Table</label>
            <select
              id="shape-table"
              value={tableName}
              onChange={(event) => setTableName(event.target.value)}
            >
              <option value="">Select a table…</option>
              {tablesQuery.data?.tables?.map((table) => (
                <option key={table} value={table}>
                  {table}
                </option>
              ))}
            </select>
          </div>

          <div className="setup-actions">
            <button
              type="button"
              disabled={!canSubmit || captureMutation.isPending}
              onClick={() => captureMutation.mutate()}
            >
              {captureMutation.isPending ? "Capturing…" : "Capture shape"}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
