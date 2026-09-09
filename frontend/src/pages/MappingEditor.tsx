import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
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

interface EnumTranslationTable {
  id: string;
  name: string;
  current_version_id: string | null;
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

  const enumTranslationsQuery = useQuery({
    queryKey: ["enum-translations"],
    queryFn: () => api.get<EnumTranslationTable[]>("/enum-translations"),
  });

  function setLinkTranslation(index: number, translationVersionId: string | undefined) {
    setLinks((current) =>
      current.map((link, i) =>
        i === index
          ? translationVersionId
            ? { ...link, enumTranslationVersionId: translationVersionId }
            : { sourceColumn: link.sourceColumn, targetColumn: link.targetColumn }
          : link,
      ),
    );
  }

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

      {links.length > 0 && (
        <section>
          <h2>Column links</h2>
          <p>
            For a source column whose values are enum codes, attach a translation table so the
            target receives the human-readable value instead of the raw code (FR-005).
          </p>
          <table>
            <thead>
              <tr>
                <th>Source column</th>
                <th>Target column</th>
                <th>Enum translation</th>
              </tr>
            </thead>
            <tbody>
              {links.map((link, index) => (
                <tr key={`${link.sourceColumn}->${link.targetColumn}`}>
                  <td>{link.sourceColumn}</td>
                  <td>{link.targetColumn}</td>
                  <td>
                    <select
                      value={link.enumTranslationVersionId ?? ""}
                      onChange={(event) =>
                        setLinkTranslation(index, event.target.value || undefined)
                      }
                    >
                      <option value="">None</option>
                      {enumTranslationsQuery.data
                        ?.filter((t) => t.current_version_id)
                        .map((t) => (
                          <option key={t.id} value={t.current_version_id ?? ""}>
                            {t.name}
                          </option>
                        ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

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
          <Link to={`/mappings/${mappingId}/dry-run`}>Run dry run</Link>
        </section>
      )}
    </main>
  );
}
