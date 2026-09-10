import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, type ReconciliationRun, api } from "../services/api";

interface ViewDefinition {
  id: string;
  name: string;
  legacy_shape_capture_id: string;
}

interface LegacyShapeCapture {
  id: string;
  columns: { name: string }[];
}

/**
 * Reconcile a deployed compatibility view against its still-live old table (User
 * Story 3, FR-009): counts of matched/old-only/view-only rows plus per-row/column
 * discrepancy detail. Each flagged row/column links through to the XML lookup panel
 * (User Story 4) so an engineer can immediately check whether the gap is a genuine
 * migration bug or expected (the value never existed anywhere, per FR-011/FR-012).
 */
export function ReconciliationResults() {
  const { viewDefinitionId } = useParams();
  const [identityColumn, setIdentityColumn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReconciliationRun | null>(null);

  const definitionQuery = useQuery({
    queryKey: ["view-definition", viewDefinitionId],
    queryFn: () => api.get<ViewDefinition>(`/view-definitions/${viewDefinitionId}`),
    enabled: Boolean(viewDefinitionId),
  });

  const legacyShapeQuery = useQuery({
    queryKey: ["legacy-shape", definitionQuery.data?.legacy_shape_capture_id],
    queryFn: () =>
      api.get<LegacyShapeCapture>(
        `/legacy-shapes/${definitionQuery.data?.legacy_shape_capture_id}`,
      ),
    enabled: Boolean(definitionQuery.data?.legacy_shape_capture_id),
  });

  const historyQuery = useQuery({
    queryKey: ["reconciliations", viewDefinitionId],
    queryFn: () =>
      api.get<ReconciliationRun[]>(`/view-definitions/${viewDefinitionId}/reconciliations`),
    enabled: Boolean(viewDefinitionId),
  });

  const reconcileMutation = useMutation({
    mutationFn: () =>
      api.post<ReconciliationRun>(`/view-definitions/${viewDefinitionId}/reconcile`, {
        identity_column: identityColumn,
      }),
    onSuccess: (run) => {
      setResult(run);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "not_deployed") {
        setError("This view has never been successfully deployed — deploy it before reconciling.");
      } else {
        setError(err instanceof ApiError ? err.message : "Reconciliation failed");
      }
    },
  });

  const shown = result ?? historyQuery.data?.[historyQuery.data.length - 1] ?? null;
  const hasDiscrepancies = shown
    ? shown.rows_old_only > 0 ||
      shown.rows_view_only > 0 ||
      shown.rows_with_column_mismatch > 0 ||
      shown.row_inflation_flagged
    : false;

  return (
    <main>
      <h1>Reconcile: {definitionQuery.data?.name}</h1>
      <p>
        Compares the deployed view&apos;s live output against the legacy table it was built to
        reproduce, keyed by an identity column (FR-009).
      </p>

      <section>
        <label htmlFor="identity-column">Identity column</label>
        <select
          id="identity-column"
          aria-label="Identity column"
          value={identityColumn}
          onChange={(event) => setIdentityColumn(event.target.value)}
        >
          <option value="">Select the shared identity/key column…</option>
          {legacyShapeQuery.data?.columns.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => reconcileMutation.mutate()}
          disabled={reconcileMutation.isPending || !identityColumn}
        >
          Run reconciliation
        </button>
      </section>

      {error && <p role="alert">{error}</p>}

      {shown && (
        <>
          <section>
            <h2>Counts</h2>
            <ul>
              <li>Rows matched: {shown.rows_matched}</li>
              <li>Old-table-only rows: {shown.rows_old_only}</li>
              <li>View-only rows: {shown.rows_view_only}</li>
              <li>Rows with a column mismatch: {shown.rows_with_column_mismatch}</li>
              <li>
                Row inflation flagged (FR-014):{" "}
                {shown.row_inflation_flagged
                  ? "yes — a join produced >1 view row per identity"
                  : "no"}
              </li>
            </ul>
            {!hasDiscrepancies && <p>Clean reconciliation — zero discrepancies.</p>}
          </section>

          {hasDiscrepancies && (
            <section>
              <h2>Discrepancy detail</h2>
              <table>
                <thead>
                  <tr>
                    <th>Identity</th>
                    <th>Column</th>
                    <th>Old value</th>
                    <th>View value</th>
                    <th>Investigate in XML</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.discrepancy_detail.map((entry, i) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: discrepancy entries have no stable id
                    <tr key={i}>
                      <td>{String(entry.identity)}</td>
                      <td>{entry.column ?? "(row presence)"}</td>
                      <td>{String(entry.old_value)}</td>
                      <td>{String(entry.view_value)}</td>
                      <td>
                        {entry.column && (
                          <Link
                            to={`/view-definitions/${viewDefinitionId}/xml-lookup?identity=${encodeURIComponent(
                              String(entry.identity),
                            )}&legacy_column=${encodeURIComponent(entry.column)}`}
                          >
                            Look up in XML →
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      <section>
        <h2>Reconciliation history</h2>
        <ul>
          {historyQuery.data?.map((run) => (
            <li key={run.id}>
              {run.identity_column}: matched {run.rows_matched}, old-only {run.rows_old_only},
              view-only {run.rows_view_only}, mismatched {run.rows_with_column_mismatch}
              {run.row_inflation_flagged ? " (row inflation flagged)" : ""}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
