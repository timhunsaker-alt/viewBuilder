import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { JoinGraphCanvas, type JoinGraphTable } from "../components/canvas/JoinGraphCanvas";
import {
  ApiError,
  type ColumnMappingEntry,
  type JoinGraphEdge,
  type LegacyShapeCapture,
  api,
} from "../services/api";

interface Connection {
  id: string;
  name: string;
  environment: "dev" | "test" | "prod";
}

interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
}

interface ViewDefinition {
  id: string;
  name: string;
  legacy_shape_capture_id: string;
  target_connection_id: string;
  current_version_id: string | null;
}

interface ViewDefinitionVersion {
  id: string;
  version_number: number;
  join_graph: JoinGraphEdge[];
  column_mappings: ColumnMappingEntry[];
  generated_sql: string;
}

/**
 * Builds a compatibility view definition (User Story 1): pick a captured legacy
 * shape, pick the new-schema tables that replace it, draw the join graph connecting
 * them (JoinGraphCanvas, FR-002), then map every legacy column to a source
 * table/column (FR-003/FR-004). Column mapping is deliberately a plain per-row
 * table/column picker rather than forcing MappingCanvas's single-source-table drag
 * interaction to also carry a per-link table choice — JoinGraphCanvas is the piece of
 * this editor that reuses the drag-and-drop canvas interaction (multi-table joins),
 * per plan.md's Project Structure.
 */
export function ViewDefinitionEditor() {
  const { viewDefinitionId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [legacyShapeId, setLegacyShapeId] = useState("");
  const [targetConnectionId, setTargetConnectionId] = useState("");
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [joinGraph, setJoinGraph] = useState<JoinGraphEdge[]>([]);
  const [columnMappings, setColumnMappings] = useState<Record<string, ColumnMappingEntry>>({});
  const [error, setError] = useState<string | null>(null);

  const definitionQuery = useQuery({
    queryKey: ["view-definition", viewDefinitionId],
    queryFn: () => api.get<ViewDefinition>(`/view-definitions/${viewDefinitionId}`),
    enabled: Boolean(viewDefinitionId),
  });

  const versionsQuery = useQuery({
    queryKey: ["view-definition-versions", viewDefinitionId],
    queryFn: () =>
      api.get<ViewDefinitionVersion[]>(`/view-definitions/${viewDefinitionId}/versions`),
    enabled: Boolean(viewDefinitionId),
  });

  const legacyShapesQuery = useQuery({
    queryKey: ["legacy-shapes"],
    queryFn: () => api.get<LegacyShapeCapture[]>("/legacy-shapes"),
  });

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const activeLegacyShapeId = viewDefinitionId
    ? definitionQuery.data?.legacy_shape_capture_id
    : legacyShapeId;
  const legacyShape = legacyShapesQuery.data?.find((shape) => shape.id === activeLegacyShapeId);

  const activeTargetConnectionId = viewDefinitionId
    ? definitionQuery.data?.target_connection_id
    : targetConnectionId;

  const tablesQuery = useQuery({
    queryKey: ["schema", activeTargetConnectionId],
    queryFn: () => api.get<{ tables: string[] }>(`/connections/${activeTargetConnectionId}/schema`),
    enabled: Boolean(activeTargetConnectionId),
  });

  const tableColumnsQueries = useQueries({
    queries: selectedTables.map((table) => ({
      queryKey: ["schema", activeTargetConnectionId, table],
      queryFn: () =>
        api.get<{ columns: SchemaColumn[] }>(
          `/connections/${activeTargetConnectionId}/schema?table=${encodeURIComponent(table)}`,
        ),
      enabled: Boolean(activeTargetConnectionId) && Boolean(table),
    })),
  });

  const joinGraphTables = useMemo<JoinGraphTable[]>(
    () =>
      selectedTables.map((table, index) => ({
        name: table,
        columns: tableColumnsQueries[index]?.data?.columns?.map((c) => c.name) ?? [],
      })),
    [selectedTables, tableColumnsQueries],
  );

  const currentVersion = viewDefinitionId
    ? versionsQuery.data?.find((v) => v.id === definitionQuery.data?.current_version_id)
    : undefined;
  const legacyColumns = legacyShape?.columns.map((c) => c.name) ?? [];

  function toggleTable(table: string) {
    setSelectedTables((current) =>
      current.includes(table) ? current.filter((t) => t !== table) : [...current, table],
    );
  }

  function setMapping(legacyColumn: string, sourceTable: string, sourceColumn: string) {
    setColumnMappings((current) => ({
      ...current,
      [legacyColumn]: {
        legacy_column: legacyColumn,
        source_table: sourceTable || null,
        source_column_or_expression: sourceColumn,
      },
    }));
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const mappings = legacyColumns.map(
        (col) =>
          columnMappings[col] ?? {
            legacy_column: col,
            source_table: null,
            source_column_or_expression: "",
          },
      );
      if (viewDefinitionId) {
        return api.post<ViewDefinitionVersion>(`/view-definitions/${viewDefinitionId}/versions`, {
          join_graph: joinGraph,
          column_mappings: mappings,
        });
      }
      return api.post<ViewDefinition>("/view-definitions", {
        name,
        legacy_shape_capture_id: legacyShapeId,
        target_connection_id: targetConnectionId,
        join_graph: joinGraph,
        column_mappings: mappings,
      });
    },
    onSuccess: (result) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["view-definition-versions", viewDefinitionId] });
      queryClient.invalidateQueries({ queryKey: ["view-definitions"] });
      if (!viewDefinitionId && "id" in result) {
        navigate(`/view-definitions/${(result as ViewDefinition).id}`);
      }
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Save failed");
    },
  });

  const allColumnsMapped =
    legacyColumns.length > 0 &&
    legacyColumns.every(
      (col) => (columnMappings[col]?.source_column_or_expression ?? "").length > 0,
    );

  return (
    <main>
      <h1>{viewDefinitionId ? definitionQuery.data?.name : "New compatibility view"}</h1>

      {error && <p role="alert">{error}</p>}

      {!viewDefinitionId && (
        <>
          <section>
            <h2>1. Name the view</h2>
            <p>
              Must not equal the legacy shape's own table name (a view can't share a table's name).
            </p>
            <input
              aria-label="View name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </section>

          <section>
            <h2>2. Legacy shape (required output column shape)</h2>
            <select
              aria-label="Legacy shape"
              value={legacyShapeId}
              onChange={(event) => setLegacyShapeId(event.target.value)}
            >
              <option value="">Select a captured legacy shape…</option>
              {legacyShapesQuery.data?.map((shape) => (
                <option key={shape.id} value={shape.id}>
                  {shape.name} ({shape.table_name})
                </option>
              ))}
            </select>
            <p>
              No legacy shape yet? Capture one on the <Link to="/">table picker</Link>, then use{" "}
              <code>POST /legacy-shapes</code>.
            </p>
          </section>

          <section>
            <h2>3. Target connection (where the new-schema tables + deployed view live)</h2>
            <select
              aria-label="Target connection"
              value={targetConnectionId}
              onChange={(event) => {
                setTargetConnectionId(event.target.value);
                setSelectedTables([]);
              }}
            >
              <option value="">Select a connection…</option>
              {connectionsQuery.data?.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.name} ({connection.environment})
                </option>
              ))}
            </select>
          </section>
        </>
      )}

      {activeTargetConnectionId && (
        <section>
          <h2>4. New-schema tables</h2>
          <ul>
            {tablesQuery.data?.tables?.map((table) => (
              <li key={table}>
                <label>
                  <input
                    type="checkbox"
                    checked={selectedTables.includes(table)}
                    onChange={() => toggleTable(table)}
                  />
                  {table}
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {selectedTables.length > 0 && (
        <section>
          <h2>5. Join graph (FR-002)</h2>
          <JoinGraphCanvas
            tables={joinGraphTables}
            joinGraph={joinGraph}
            onJoinGraphChange={setJoinGraph}
          />
        </section>
      )}

      {legacyColumns.length > 0 && (
        <section>
          <h2>6. Column mapping (FR-003/FR-004)</h2>
          <table>
            <thead>
              <tr>
                <th>Legacy column</th>
                <th>Source table</th>
                <th>Source column / expression</th>
              </tr>
            </thead>
            <tbody>
              {legacyColumns.map((legacyColumn) => {
                const mapping = columnMappings[legacyColumn];
                return (
                  <tr key={legacyColumn}>
                    <td>{legacyColumn}</td>
                    <td>
                      <select
                        aria-label={`Source table for ${legacyColumn}`}
                        value={mapping?.source_table ?? ""}
                        onChange={(event) =>
                          setMapping(
                            legacyColumn,
                            event.target.value,
                            mapping?.source_column_or_expression ?? "",
                          )
                        }
                      >
                        <option value="">(raw expression)</option>
                        {selectedTables.map((table) => (
                          <option key={table} value={table}>
                            {table}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        aria-label={`Source column or expression for ${legacyColumn}`}
                        value={mapping?.source_column_or_expression ?? ""}
                        onChange={(event) =>
                          setMapping(legacyColumn, mapping?.source_table ?? "", event.target.value)
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!allColumnsMapped && <p>Every legacy column must be mapped before saving (FR-004).</p>}
        </section>
      )}

      <button
        type="button"
        onClick={() => saveMutation.mutate()}
        disabled={
          saveMutation.isPending ||
          !allColumnsMapped ||
          (!viewDefinitionId && (!name || !legacyShapeId || !targetConnectionId))
        }
      >
        Save view definition
      </button>

      {viewDefinitionId && (
        <section>
          <h2>Version history</h2>
          <ul>
            {versionsQuery.data?.map((version) => (
              <li key={version.id}>v{version.version_number}</li>
            ))}
          </ul>
          {currentVersion && (
            <Link to={`/view-definitions/${viewDefinitionId}/preview`}>
              Preview &amp; deploy current version →
            </Link>
          )}
        </section>
      )}
    </main>
  );
}
