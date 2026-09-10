import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { ProductionGuard } from "../components/shared/ProductionGuard";
import { ApiError, type ViewDeploymentLogEntry, api } from "../services/api";

interface ViewDefinition {
  id: string;
  name: string;
  target_connection_id: string;
}

interface Connection {
  id: string;
  environment: "dev" | "test" | "prod";
}

/**
 * Preview (zero-DDL, FR-005) and deploy (real CREATE OR ALTER VIEW, FR-006) for a
 * compatibility view's current version. Mirrors DryRunResults.tsx's preview-then-
 * confirm-then-execute shape from 001, adapted to this feature's mode names.
 */
export function ViewPreviewResults() {
  const { viewDefinitionId } = useParams();
  const [preview, setPreview] = useState<ViewDeploymentLogEntry | null>(null);
  const [deployResult, setDeployResult] = useState<ViewDeploymentLogEntry | null>(null);
  const [error, setError] = useState<string | null>(null);

  const definitionQuery = useQuery({
    queryKey: ["view-definition", viewDefinitionId],
    queryFn: () => api.get<ViewDefinition>(`/view-definitions/${viewDefinitionId}`),
    enabled: Boolean(viewDefinitionId),
  });

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const isProduction = Boolean(
    connectionsQuery.data?.some(
      (connection) =>
        connection.id === definitionQuery.data?.target_connection_id &&
        connection.environment === "prod",
    ),
  );

  const previewMutation = useMutation({
    mutationFn: () =>
      api.post<ViewDeploymentLogEntry>(`/view-definitions/${viewDefinitionId}/preview`, {}),
    onSuccess: (result) => {
      setPreview(result);
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Preview failed");
    },
  });

  const deployMutation = useMutation({
    mutationFn: () =>
      api.post<ViewDeploymentLogEntry>(`/view-definitions/${viewDefinitionId}/deploy`, {
        confirm_production: isProduction,
      }),
    onSuccess: (result) => {
      setDeployResult(result);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "production_confirmation_required") {
        setError(
          "This view targets a production connection. Check the confirmation box below and deploy again.",
        );
      } else if (err instanceof ApiError && err.code === "schema_mismatch") {
        setError(
          `The legacy shape has drifted since it was captured: ${err.message}. Re-capture it before deploying.`,
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Deploy failed");
      }
    },
  });

  return (
    <main>
      <h1>Preview &amp; deploy: {definitionQuery.data?.name}</h1>

      <button
        type="button"
        onClick={() => previewMutation.mutate()}
        disabled={previewMutation.isPending}
      >
        Run preview
      </button>

      {error && <p role="alert">{error}</p>}

      {preview && (
        <>
          <section>
            <h2>Generated SQL</h2>
            <pre>{preview.generated_sql}</pre>
          </section>

          <section>
            <h2>Sample rows</h2>
            <table>
              <thead>
                <tr>
                  {preview.sample_rows[0] &&
                    Object.keys(preview.sample_rows[0]).map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.map((row, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: sample rows have no stable id
                  <tr key={i}>
                    {Object.values(row).map((value, j) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: sample rows have no stable id
                      <td key={j}>{String(value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2>Deploy</h2>
            <p>
              Deploys the exact SQL shown above as a real <code>CREATE OR ALTER VIEW</code>. Nothing
              is deployed until this step (Constitution Principle I).
            </p>
            <ProductionGuard
              isProduction={isProduction}
              actionLabel="Deploy for real"
              pendingLabel="Deploying…"
              isPending={deployMutation.isPending}
              onConfirm={() => deployMutation.mutate()}
              description={
                definitionQuery.data
                  ? `View "${definitionQuery.data.name}" targets a connection tagged production.`
                  : undefined
              }
            />
          </section>
        </>
      )}

      {deployResult && (
        <section>
          <h2>Deploy result</h2>
          <p>Outcome: {deployResult.outcome}</p>
        </section>
      )}
    </main>
  );
}
