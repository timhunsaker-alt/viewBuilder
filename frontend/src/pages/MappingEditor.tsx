import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { type ColumnMappingLink, MappingCanvas } from "../components/canvas/MappingCanvas";
import { api } from "../services/api";

interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
}

interface MappingVersion {
  id: string;
  version_number: number;
  column_links: ColumnMappingLink[];
}

interface MappingDefinition {
  id: string;
  name: string;
  current_version_id: string;
}

interface LocationState {
  connectionId?: string;
  table?: string;
}

export function MappingEditor() {
  const { mappingId } = useParams();
  const location = useLocation();
  const state = (location.state as LocationState | null) ?? {};
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [links, setLinks] = useState<ColumnMappingLink[]>([]);

  const mappingQuery = useQuery({
    queryKey: ["mapping", mappingId],
    queryFn: () => api.get<MappingDefinition>(`/mappings/${mappingId}`),
    enabled: Boolean(mappingId),
  });

  const versionsQuery = useQuery({
    queryKey: ["mapping-versions", mappingId],
    queryFn: () => api.get<MappingVersion[]>(`/mappings/${mappingId}/versions`),
    enabled: Boolean(mappingId),
  });

  const sourceSchemaQuery = useQuery({
    queryKey: ["schema", state.connectionId, state.table],
    queryFn: () =>
      api.get<{ columns: SchemaColumn[] }>(
        `/connections/${state.connectionId}/schema?table=${encodeURIComponent(state.table ?? "")}`,
      ),
    enabled: Boolean(state.connectionId) && Boolean(state.table),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (mappingId) {
        return api.post<MappingVersion>(`/mappings/${mappingId}/versions`, { column_links: links });
      }
      return api.post<MappingDefinition>("/mappings", {
        name,
        kind: "column_mapping",
        source_connection_id: state.connectionId,
        source_table: state.table,
        target_connection_id: state.connectionId,
        target_table: state.table,
        column_links: links,
        row_identity_column: sourceSchemaQuery.data?.columns?.[0]?.name ?? "",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mapping-versions", mappingId] });
      queryClient.invalidateQueries({ queryKey: ["mappings"] });
    },
  });

  const sourceColumns = sourceSchemaQuery.data?.columns?.map((c) => c.name) ?? [];
  const targetColumns = sourceSchemaQuery.data?.columns?.map((c) => c.name) ?? [];

  return (
    <main>
      <h1>{mappingId ? mappingQuery.data?.name : "New Mapping"}</h1>

      {!mappingId && (
        <label>
          Mapping name
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
      )}

      <MappingCanvas
        sourceColumns={sourceColumns}
        targetColumns={targetColumns}
        links={links}
        onLinksChange={setLinks}
      />

      <button
        type="button"
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending || links.length === 0}
      >
        Save mapping
      </button>

      {mappingId && (
        <section>
          <h2>Version history</h2>
          <ul>
            {versionsQuery.data?.map((version) => (
              <li key={version.id}>v{version.version_number}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
