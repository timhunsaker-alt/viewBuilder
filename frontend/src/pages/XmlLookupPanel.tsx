import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ApiError, type XmlFieldMapping, type XmlLookupResult, api } from "../services/api";

interface ViewDefinition {
  id: string;
  legacy_shape_capture_id: string;
}

/**
 * XML fallback lookup (User Story 4, FR-011/FR-012): for a legacy column flagged by
 * reconciliation, find (or configure) the XML field mapping for that column and run
 * the lookup, distinguishing found/field_missing/document_not_found. Reachable from a
 * flagged row in ReconciliationResults.tsx via ?identity=&legacy_column= query params.
 */
export function XmlLookupPanel() {
  const { viewDefinitionId } = useParams();
  const [searchParams] = useSearchParams();

  const [identity, setIdentity] = useState(searchParams.get("identity") ?? "");
  const [legacyColumn, setLegacyColumn] = useState(searchParams.get("legacy_column") ?? "");
  const [selectedMappingId, setSelectedMappingId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<XmlLookupResult | null>(null);

  // Configuration state for creating a new field-path entry when none exists yet
  // (US4 AC4) — added incrementally, one legacy column at a time.
  const [xpath, setXpath] = useState("");
  const [castType, setCastType] = useState("NVARCHAR(4000)");

  const definitionQuery = useQuery({
    queryKey: ["view-definition", viewDefinitionId],
    queryFn: () => api.get<ViewDefinition>(`/view-definitions/${viewDefinitionId}`),
    enabled: Boolean(viewDefinitionId),
  });

  const mappingsQuery = useQuery({
    queryKey: ["xml-field-mappings"],
    queryFn: () => api.get<XmlFieldMapping[]>("/xml-field-mappings"),
  });

  const relevantMappings = mappingsQuery.data?.filter(
    (m) => m.legacy_shape_capture_id === definitionQuery.data?.legacy_shape_capture_id,
  );

  const selectedMapping = mappingsQuery.data?.find((m) => m.id === selectedMappingId);

  const lookupMutation = useMutation({
    mutationFn: () =>
      api.post<XmlLookupResult>(`/xml-field-mappings/${selectedMappingId}/lookup`, {
        identity,
        legacy_column: legacyColumn,
      }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "mapping_invalid") {
        setError(
          `No XML field path is configured yet for "${legacyColumn}" — add one below, then look up again.`,
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Lookup failed");
      }
    },
  });

  const addFieldPathMutation = useMutation({
    mutationFn: () => {
      // T053 fix: GET /xml-field-mappings/{id} now returns the current version's
      // `field_paths` directly (see services/api.ts's XmlFieldMapping.field_paths), so
      // this panel merges the new entry into what's already configured instead of
      // clobbering every previously-added column's path with a version that only
      // carries this one (each version is the *complete* field_paths list — Principle
      // II versions are immutable, not diffed/merged server-side).
      const existing = selectedMapping?.field_paths ?? [];
      const merged = [
        ...existing.filter((entry) => entry.legacy_column !== legacyColumn),
        { legacy_column: legacyColumn, xpath, cast_type: castType },
      ];
      return api.post(`/xml-field-mappings/${selectedMappingId}/versions`, {
        field_paths: merged,
      });
    },
    onSuccess: () => {
      setError(null);
      lookupMutation.mutate();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Adding field path failed");
    },
  });

  return (
    <main>
      <h1>XML fallback lookup</h1>
      <p>
        For a column flagged by reconciliation, check whether the value actually exists in the
        legacy XML documents (FR-011/FR-012).
      </p>

      <section>
        <label htmlFor="xml-mapping">XML field mapping</label>
        <select
          id="xml-mapping"
          aria-label="XML field mapping"
          value={selectedMappingId}
          onChange={(event) => setSelectedMappingId(event.target.value)}
        >
          <option value="">Select a mapping for this legacy shape…</option>
          {relevantMappings?.map((mapping) => (
            <option key={mapping.id} value={mapping.id}>
              {mapping.xml_table_name}
            </option>
          ))}
        </select>

        <label htmlFor="identity">Identity</label>
        <input
          id="identity"
          aria-label="Identity"
          value={identity}
          onChange={(event) => setIdentity(event.target.value)}
        />

        <label htmlFor="legacy-column">Legacy column</label>
        <input
          id="legacy-column"
          aria-label="Legacy column"
          value={legacyColumn}
          onChange={(event) => setLegacyColumn(event.target.value)}
        />

        <button
          type="button"
          onClick={() => lookupMutation.mutate()}
          disabled={lookupMutation.isPending || !selectedMappingId || !identity || !legacyColumn}
        >
          Run lookup
        </button>
      </section>

      {error && <p role="alert">{error}</p>}

      {error?.startsWith("No XML field path") && (
        <section>
          <h2>Configure a field path (US4 AC4)</h2>
          <label htmlFor="xpath">XPath</label>
          <input
            id="xpath"
            aria-label="XPath"
            placeholder="(/Application/CollateralValue)[1]"
            value={xpath}
            onChange={(event) => setXpath(event.target.value)}
          />
          <label htmlFor="cast-type">Cast type</label>
          <input
            id="cast-type"
            aria-label="Cast type"
            value={castType}
            onChange={(event) => setCastType(event.target.value)}
          />
          <button
            type="button"
            onClick={() => addFieldPathMutation.mutate()}
            disabled={addFieldPathMutation.isPending || !xpath}
          >
            Save field path &amp; look up
          </button>
        </section>
      )}

      {result && (
        <section>
          <h2>Result</h2>
          <ul>
            <li>Outcome: {result.outcome}</li>
            {result.outcome === "found" && <li>Value found in XML: {result.value}</li>}
            {result.outcome === "field_missing" && (
              <li>Document exists, but this field is absent from it.</li>
            )}
            {result.outcome === "document_not_found" && (
              <li>No XML document exists at all for this identity.</li>
            )}
          </ul>
        </section>
      )}
    </main>
  );
}
