import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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

/**
 * Preview of a dry-run (US4) or completed execution (US5). For a dry-run, the "would
 * write" count is derived as source_rows_read - untranslatable_rows_flagged — the
 * persisted target_rows_written/retirement_records_written fields are always 0 for a
 * dry-run (Constitution Principle I: a dry-run performs zero writes).
 */
export function DryRunResults() {
  const { mappingId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmProduction, setConfirmProduction] = useState(false);

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
        confirm_production: confirmProduction,
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
            <label>
              <input
                type="checkbox"
                checked={confirmProduction}
                onChange={(event) => setConfirmProduction(event.target.checked)}
              />
              I confirm this run may touch a production connection
            </label>
            <button
              type="button"
              onClick={() => executeMutation.mutate()}
              disabled={executeMutation.isPending}
            >
              Execute for real
            </button>
          </section>
        </>
      )}
    </main>
  );
}
