import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { api } from "../services/api";

interface RunLog {
  id: string;
  mapping_version_id: string;
  mode: "dry_run" | "execute";
  operator: string;
  outcome: string | null;
  source_rows_read: number;
  target_rows_written: number;
  retirement_records_written: number;
  untranslatable_rows_flagged: number;
  production_confirmed: boolean;
}

interface LocationState {
  justRanId?: string;
}

/** List + detail view of run_log_entry rows (FR-014), so a completed execution can be
 * audited/reconstructed later: which mapping version, what counts, what outcome. */
export function RunHistory() {
  const location = useLocation();
  const justRanId = (location.state as LocationState | null)?.justRanId;
  const [searchParams] = useSearchParams();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(justRanId ?? null);

  const mappingDefinitionId = searchParams.get("mapping_definition_id") ?? undefined;
  const mode = searchParams.get("mode") ?? undefined;

  const runsQuery = useQuery({
    queryKey: ["runs", mappingDefinitionId, mode],
    queryFn: () => {
      const params = new URLSearchParams();
      if (mappingDefinitionId) params.set("mapping_definition_id", mappingDefinitionId);
      if (mode) params.set("mode", mode);
      const qs = params.toString();
      return api.get<RunLog[]>(`/runs${qs ? `?${qs}` : ""}`);
    },
  });

  const runDetailQuery = useQuery({
    queryKey: ["run", selectedRunId],
    queryFn: () => api.get<RunLog>(`/runs/${selectedRunId}`),
    enabled: Boolean(selectedRunId),
  });

  return (
    <main>
      <h1>Run history</h1>

      <table>
        <thead>
          <tr>
            <th>Mode</th>
            <th>Outcome</th>
            <th>Source rows</th>
            <th>Target rows written</th>
            <th>Retirements written</th>
            <th>Flagged</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runsQuery.data?.map((run) => (
            <tr key={run.id}>
              <td>{run.mode}</td>
              <td>{run.outcome ?? "—"}</td>
              <td>{run.source_rows_read}</td>
              <td>{run.target_rows_written}</td>
              <td>{run.retirement_records_written}</td>
              <td>{run.untranslatable_rows_flagged}</td>
              <td>
                <button type="button" onClick={() => setSelectedRunId(run.id)}>
                  Details
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selectedRunId && runDetailQuery.data && (
        <section>
          <h2>Run detail</h2>
          <dl>
            <dt>Mapping version</dt>
            <dd>{runDetailQuery.data.mapping_version_id}</dd>
            <dt>Operator</dt>
            <dd>{runDetailQuery.data.operator}</dd>
            <dt>Production confirmed</dt>
            <dd>{runDetailQuery.data.production_confirmed ? "Yes" : "No"}</dd>
          </dl>
        </section>
      )}
    </main>
  );
}
