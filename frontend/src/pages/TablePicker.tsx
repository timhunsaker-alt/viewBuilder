import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";

interface Connection {
  id: string;
  name: string;
  role: "source" | "target" | "either";
  environment: "dev" | "test" | "prod";
}

interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
}

interface SchemaResponse {
  tables?: string[];
  columns?: SchemaColumn[];
}

export function TablePicker() {
  const [connectionId, setConnectionId] = useState<string>("");
  const [table, setTable] = useState<string>("");

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => api.get<Connection[]>("/connections"),
  });

  const tablesQuery = useQuery({
    queryKey: ["schema", connectionId],
    queryFn: () => api.get<SchemaResponse>(`/connections/${connectionId}/schema`),
    enabled: Boolean(connectionId),
  });

  const columnsQuery = useQuery({
    queryKey: ["schema", connectionId, table],
    queryFn: () =>
      api.get<SchemaResponse>(
        `/connections/${connectionId}/schema?table=${encodeURIComponent(table)}`,
      ),
    enabled: Boolean(connectionId) && Boolean(table),
  });

  return (
    <main>
      <h1>viewBuilder</h1>
      <p>
        <Link to="/setup">Set up a connection →</Link>
        {" · "}
        <Link to="/legacy-shapes/new">Capture an old table's shape →</Link>
        {" · "}
        <Link to="/view-definitions/new">Build a legacy-shape compatibility view →</Link>
        {" · "}
        <Link to="/view-definitions">View saved compatibility views →</Link>
      </p>
      <section>
        <h2>1. Choose a connection</h2>
        <select
          aria-label="Choose a connection"
          value={connectionId}
          onChange={(event) => {
            setConnectionId(event.target.value);
            setTable("");
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

      {connectionId && (
        <section>
          <h2>2. Choose a source table</h2>
          {tablesQuery.isLoading && <p>Loading tables…</p>}
          <select
            aria-label="Choose a source table"
            value={table}
            onChange={(event) => setTable(event.target.value)}
          >
            <option value="">Select a table…</option>
            {tablesQuery.data?.tables?.map((tableName) => (
              <option key={tableName} value={tableName}>
                {tableName}
              </option>
            ))}
          </select>
        </section>
      )}

      {table && (
        <section>
          <h2>Columns in {table}</h2>
          <ul>
            {columnsQuery.data?.columns?.map((column) => (
              <li key={column.name}>
                {column.name}: {column.type} {column.nullable ? "" : "(not null)"}
              </li>
            ))}
          </ul>
          <Link to="/mappings/new" state={{ connectionId, table }}>
            Continue to mapping canvas →
          </Link>
          {" · "}
          <Link to="/retirement/new" state={{ connectionId, table }}>
            Configure retirement mapping →
          </Link>
        </section>
      )}
    </main>
  );
}
