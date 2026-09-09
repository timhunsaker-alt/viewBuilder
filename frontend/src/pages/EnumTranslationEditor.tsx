import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../services/api";

interface EnumEntry {
  code: string;
  translated_value: string;
}

interface EnumTranslationTable {
  id: string;
  name: string;
  current_version_id: string | null;
}

interface EnumTranslationVersion {
  id: string;
  version_number: number;
  entries: EnumEntry[];
}

/**
 * Create/edit reusable enum-translation tables (FR-006). Saving always creates a new,
 * immutable version rather than mutating the previous one's entries.
 */
export function EnumTranslationEditor() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [entries, setEntries] = useState<EnumEntry[]>([{ code: "", translated_value: "" }]);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);

  const tablesQuery = useQuery({
    queryKey: ["enum-translations"],
    queryFn: () => api.get<EnumTranslationTable[]>("/enum-translations"),
  });

  const selectedTable = tablesQuery.data?.find((t) => t.id === selectedTableId);

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<EnumTranslationTable>("/enum-translations", {
        name,
        entries: entries.filter((e) => e.code && e.translated_value),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["enum-translations"] });
      setName("");
      setEntries([{ code: "", translated_value: "" }]);
    },
  });

  const newVersionMutation = useMutation({
    mutationFn: () =>
      api.post<EnumTranslationVersion>(`/enum-translations/${selectedTableId}/versions`, {
        entries: entries.filter((e) => e.code && e.translated_value),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["enum-translations"] });
    },
  });

  function updateEntry(index: number, field: keyof EnumEntry, value: string) {
    setEntries((current) =>
      current.map((entry, i) => (i === index ? { ...entry, [field]: value } : entry)),
    );
  }

  return (
    <main>
      <h1>Enum Translation Tables</h1>

      <section>
        <h2>Existing tables</h2>
        <ul>
          {tablesQuery.data?.map((table) => (
            <li key={table.id}>
              <button type="button" onClick={() => setSelectedTableId(table.id)}>
                {table.name}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>{selectedTableId ? `Edit: ${selectedTable?.name}` : "New translation table"}</h2>
        {!selectedTableId && (
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
        )}

        <table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Translated value</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: rows are positionally edited, not reordered
              <tr key={index}>
                <td>
                  <input
                    value={entry.code}
                    onChange={(event) => updateEntry(index, "code", event.target.value)}
                  />
                </td>
                <td>
                  <input
                    value={entry.translated_value}
                    onChange={(event) => updateEntry(index, "translated_value", event.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <button
          type="button"
          onClick={() => setEntries((current) => [...current, { code: "", translated_value: "" }])}
        >
          Add row
        </button>

        {selectedTableId ? (
          <button type="button" onClick={() => newVersionMutation.mutate()}>
            Save new version
          </button>
        ) : (
          <button type="button" onClick={() => createMutation.mutate()} disabled={!name}>
            Create table
          </button>
        )}
      </section>
    </main>
  );
}
