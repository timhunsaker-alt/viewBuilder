import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type LegacyShapeCapture, type ViewDefinition, api } from "../services/api";

interface Connection {
  id: string;
  name: string;
  environment: "dev" | "test" | "prod";
}

/**
 * The saved compatibility-view definitions. A definition is shown here whether it
 * has only been saved or has subsequently been deployed; opening it returns to its
 * editor, version history, preview, and deployment actions.
 */
export function ViewDefinitions() {
  const definitionsQuery = useQuery({
    queryKey: ["view-definitions"],
    queryFn: () => api.get<ViewDefinition[]>("/view-definitions"),
  });
  const legacyShapesQuery = useQuery({
    queryKey: ["legacy-shapes"],
    queryFn: () => api.get<LegacyShapeCapture[]>("/legacy-shapes"),
  });
  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const legacyShapeName = (id: string) =>
    legacyShapesQuery.data?.find((shape) => shape.id === id)?.name ?? "Unknown legacy shape";
  const connectionName = (id: string) => {
    const connection = connectionsQuery.data?.find((item) => item.id === id);
    return connection ? `${connection.name} (${connection.environment})` : "Unknown connection";
  };

  return (
    <main>
      <div className="view-definitions-header">
        <div>
          <h1>Compatibility views</h1>
          <p>Open a saved view definition to edit, preview, deploy, or reconcile it.</p>
        </div>
        <Link className="button-link" to="/view-definitions/new">
          Create compatibility view
        </Link>
      </div>

      {definitionsQuery.isLoading && <p>Loading compatibility views…</p>}
      {definitionsQuery.isError && (
        <p role="alert">Could not load compatibility views. Please try again.</p>
      )}

      {definitionsQuery.data?.length === 0 && (
        <section className="empty-state">
          <h2>No compatibility views yet</h2>
          <p>Create one from a captured legacy shape to begin mapping its replacement schema.</p>
          <Link to="/legacy-shapes/new">Capture an old table's shape →</Link>
        </section>
      )}

      {definitionsQuery.data && definitionsQuery.data.length > 0 && (
        <table aria-label="Compatibility views">
          <thead>
            <tr>
              <th>Name</th>
              <th>Legacy shape</th>
              <th>Target connection</th>
              <th>Current version</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {definitionsQuery.data.map((definition) => (
              <tr key={definition.id}>
                <td>{definition.name}</td>
                <td>{legacyShapeName(definition.legacy_shape_capture_id)}</td>
                <td>{connectionName(definition.target_connection_id)}</td>
                <td>{definition.current_version_id ? "Saved" : "Not saved"}</td>
                <td>
                  <Link to={`/view-definitions/${definition.id}`}>Open →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
