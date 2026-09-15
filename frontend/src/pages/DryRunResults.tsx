import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ProductionGuard } from "../components/shared/ProductionGuard";
import { ApiError, api } from "../services/api";

interface SampleRow {
  source: Record<string, unknown>;
  target: Record<string, unknown> | null;
  untranslatable_columns: string[];
}

interface RunLog {
  id: string;
  mode: "dry_run" | "execute";
  outcome: string | null;
  source_rows_read: number;
  target_rows_written: number;
  retirement_records_written: number;
  untranslatable_rows_flagged: number;
  sample_rows: SampleRow[];
  production_confirmed: boolean;
}

interface MappingDefinition {
  id: string;
  name: string;
  source_connection_id: string;
  target_connection_id: string;
}

interface Connection {
  id: string;
  environment: "dev" | "test" | "prod";
}

/**
 * Preview of a dry-run (US4) or completed execution (US5). For a dry-run, the "would
 * write" count is derived as source_rows_read - untranslatable_rows_flagged — the
 * persisted target_rows_written/retirement_records_written fields are always 0 for a
 * dry-run (read-only preview policy: a dry-run performs zero writes).
 */
export function DryRunResults() {
  const { mappingId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunLog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mappingQuery = useQuery({
    queryKey: ["mapping", mappingId],
    queryFn: () => api.get<MappingDefinition>(`/mappings/${mappingId}`),
    enabled: Boolean(mappingId),
  });

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const isProduction = Boolean(
    mappingQuery.data &&
      connectionsQuery.data?.some(
        (connection) =>
          (connection.id === mappingQuery.data?.source_connection_id ||
            connection.id === mappingQuery.data?.target_connection_id) &&
          connection.environment === "prod",
      ),
  );

  const dryRunMutation = useMutation({
    mutationFn: () => api.post<RunLog>(`/mappings/${mappingId}/dry-run`, {}),
    onSuccess: (result) => {
      setRun(result);
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Dry run failed");
    },
  });

  const executeMutation = useMutation({
    mutationFn: () =>
      api.post<RunLog>(`/mappings/${mappingId}/execute`, {
        confirm_production: isProduction,
      }),
    onSuccess: (result) => {
      navigate("/runs", { state: { justRanId: result.id } });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "production_confirmation_required") {
        setError(
          "This mapping targets a production connection. Check the confirmation box below and execute again.",
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Execution failed");
      }
    },
  });

  const wouldWriteCount = run ? run.source_rows_read - run.untranslatable_rows_flagged : undefined;

  return (
    <main>
      <h1>Dry run preview</h1>

      <button
        type="button"
        onClick={() => dryRunMutation.mutate()}
        disabled={dryRunMutation.isPending}
      >
        Run dry run
      </button>

      {error && <p role="alert">{error}</p>}

      {run && (
        <>
          <section>
            <h2>Counts</h2>
            <ul>
              <li>Source rows read: {run.source_rows_read}</li>
              <li>Would write: {wouldWriteCount}</li>
              <li>Untranslatable rows flagged: {run.untranslatable_rows_flagged}</li>
            </ul>
          </section>

          <section>
            <h2>Sample rows</h2>
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Target (translated)</th>
                  <th>Untranslatable columns</th>
                </tr>
              </thead>
              <tbody>
                {run.sample_rows.map((row, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: sample rows have no stable id
                  <tr key={i}>
                    <td>{JSON.stringify(row.source)}</td>
                    <td>{row.target ? JSON.stringify(row.target) : "—"}</td>
                    <td>{row.untranslatable_columns.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2>Execute</h2>
            <ProductionGuard
              isProduction={isProduction}
              actionLabel="Execute for real"
              pendingLabel="Executing…"
              isPending={executeMutation.isPending}
              onConfirm={() => executeMutation.mutate()}
              description={
                mappingQuery.data
                  ? `Mapping "${mappingQuery.data.name}" reads from or writes to a connection tagged production.`
                  : undefined
              }
            />
          </section>
        </>
      )}
    </main>
  );
}
