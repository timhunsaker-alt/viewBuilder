import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../services/api";

interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
}

interface EnumTranslationTable {
  id: string;
  name: string;
  current_version_id: string | null;
}

interface LocationState {
  connectionId?: string;
  table?: string;
}

interface MappingDefinition {
  id: string;
}

/**
 * Configure a retirement mapping (US3): which status codes mean "retired", where the
 * translated reason comes from, and which target table/columns the audit record is
 * written into. Executing this mapping never updates or deletes the source row
 * (append-only retirement policy) — it only ever inserts a new audit record.
 */
export function RetirementConfig() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state as LocationState | null) ?? {};

  const [name, setName] = useState("");
  const [rowIdentityColumn, setRowIdentityColumn] = useState("");
  const [statusColumn, setStatusColumn] = useState("");
  const [retiredValueCodes, setRetiredValueCodes] = useState("");
  const [reasonColumn, setReasonColumn] = useState("");
  const [reasonTranslationVersionId, setReasonTranslationVersionId] = useState("");
  const [auditTable, setAuditTable] = useState("");
  const [rowIdentityTargetColumn, setRowIdentityTargetColumn] = useState("");
  const [reasonTargetColumn, setReasonTargetColumn] = useState("");
  const [timestampTargetColumn, setTimestampTargetColumn] = useState("");
  const [mappingVersionTargetColumn, setMappingVersionTargetColumn] = useState("");

  const columnsQuery = useQuery({
    queryKey: ["schema", state.connectionId, state.table],
    queryFn: () =>
      api.get<{ columns: SchemaColumn[] }>(
        `/connections/${state.connectionId}/schema?table=${encodeURIComponent(state.table ?? "")}`,
      ),
    enabled: Boolean(state.connectionId) && Boolean(state.table),
  });

  const enumTranslationsQuery = useQuery({
    queryKey: ["enum-translations"],
    queryFn: () => api.get<EnumTranslationTable[]>("/enum-translations"),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<MappingDefinition>("/mappings", {
        name,
        kind: "retirement",
        source_connection_id: state.connectionId,
        source_table: state.table,
        target_connection_id: state.connectionId,
        target_table: auditTable,
        column_links: [],
        row_identity_column: rowIdentityColumn,
        retirement_config: {
          status_column: statusColumn,
          retired_value_codes: retiredValueCodes
            .split(",")
            .map((code) => code.trim())
            .filter(Boolean),
          reason_column: reasonColumn,
          reason_translation_version_id: reasonTranslationVersionId || undefined,
          audit_binding: {
            audit_table: auditTable,
            row_identity_target_column: rowIdentityTargetColumn,
            reason_target_column: reasonTargetColumn,
            timestamp_target_column: timestampTargetColumn,
            mapping_version_target_column: mappingVersionTargetColumn || undefined,
          },
        },
      }),
    onSuccess: (mapping) => navigate(`/mappings/${mapping.id}`),
  });

  const columns = columnsQuery.data?.columns ?? [];

  return (
    <main>
      <h1>Configure retirement mapping</h1>
      <p>
        Source: {state.connectionId ?? "?"} / {state.table ?? "?"}
      </p>

      <label>
        Mapping name
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </label>

      <label>
        Row identity column
        <select
          value={rowIdentityColumn}
          onChange={(event) => setRowIdentityColumn(event.target.value)}
        >
          <option value="">Select…</option>
          {columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Status column (enum-coded)
        <select value={statusColumn} onChange={(event) => setStatusColumn(event.target.value)}>
          <option value="">Select…</option>
          {columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Retired status codes (comma-separated)
        <input
          value={retiredValueCodes}
          onChange={(event) => setRetiredValueCodes(event.target.value)}
          placeholder="e.g. 3"
        />
      </label>

      <label>
        Reason column (enum-coded)
        <select value={reasonColumn} onChange={(event) => setReasonColumn(event.target.value)}>
          <option value="">Select…</option>
          {columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Reason translation table
        <select
          value={reasonTranslationVersionId}
          onChange={(event) => setReasonTranslationVersionId(event.target.value)}
        >
          <option value="">Select…</option>
          {enumTranslationsQuery.data
            ?.filter((t) => t.current_version_id)
            .map((t) => (
              <option key={t.id} value={t.current_version_id ?? ""}>
                {t.name}
              </option>
            ))}
        </select>
      </label>

      <h2>Retirement audit target</h2>
      <label>
        Audit table (schema-qualified)
        <input value={auditTable} onChange={(event) => setAuditTable(event.target.value)} />
      </label>
      <label>
        Row identity target column
        <input
          value={rowIdentityTargetColumn}
          onChange={(event) => setRowIdentityTargetColumn(event.target.value)}
        />
      </label>
      <label>
        Reason target column
        <input
          value={reasonTargetColumn}
          onChange={(event) => setReasonTargetColumn(event.target.value)}
        />
      </label>
      <label>
        Timestamp target column
        <input
          value={timestampTargetColumn}
          onChange={(event) => setTimestampTargetColumn(event.target.value)}
        />
      </label>
      <label>
        Mapping-version target column (optional)
        <input
          value={mappingVersionTargetColumn}
          onChange={(event) => setMappingVersionTargetColumn(event.target.value)}
        />
      </label>

      <button
        type="button"
        onClick={() => createMutation.mutate()}
        disabled={
          createMutation.isPending ||
          !name ||
          !rowIdentityColumn ||
          !statusColumn ||
          !retiredValueCodes ||
          !reasonColumn ||
          !auditTable ||
          !rowIdentityTargetColumn ||
          !reasonTargetColumn ||
          !timestampTargetColumn
        }
      >
        Save retirement mapping
      </button>
    </main>
  );
}
