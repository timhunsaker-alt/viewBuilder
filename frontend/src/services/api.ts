export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.details = body.error.details ?? {};
  }
}

const BASE_URL = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = (await response.json()) as ApiErrorBody;
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

// --- Legacy-shape compatibility view feature (002-legacy-compat-view) ---
//
// These mirror the API contract in specs/002-legacy-compat-view/contracts/api.md.
// Pages call `api.get`/`api.post` directly with these paths/types, the same pattern
// MappingEditor.tsx already uses for the 001 endpoints — no per-endpoint wrapper
// functions are introduced here, just the shared shapes.

export interface LegacyShapeColumn {
  name: string;
  type: string;
  nullable: boolean;
}

export interface LegacyShapeCapture {
  id: string;
  name: string;
  connection_id: string;
  table_name: string;
  columns: LegacyShapeColumn[];
  captured_at: string;
}

export interface DriftReport {
  drifted: boolean;
  added_columns: string[];
  removed_columns: string[];
  retyped_columns: string[];
}

export interface JoinGraphEdge {
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  join_type: "inner" | "left";
}

export interface ColumnMappingEntry {
  legacy_column: string;
  source_table: string | null;
  source_column_or_expression: string;
}

export interface ViewDefinition {
  id: string;
  name: string;
  legacy_shape_capture_id: string;
  target_connection_id: string;
  current_version_id: string | null;
}

export interface ViewDefinitionVersion {
  id: string;
  view_definition_id: string;
  version_number: number;
  join_graph: JoinGraphEdge[];
  column_mappings: ColumnMappingEntry[];
  generated_sql: string;
}

export interface ViewDeploymentLogEntry {
  id: string;
  view_definition_version_id: string;
  mode: "preview" | "deploy";
  operator: string;
  outcome: "completed" | "failed" | null;
  sample_rows: Record<string, unknown>[];
  column_diff: { added: string[]; removed: string[]; reordered: string[] } | null;
  production_confirmed: boolean;
  generated_sql: string;
}

// --- Reconciliation (User Story 3) ---

export interface DiscrepancyDetailEntry {
  identity: string | number;
  column: string | null;
  old_value: unknown;
  view_value: unknown;
}

export interface ReconciliationRun {
  id: string;
  view_definition_version_id: string;
  identity_column: string;
  outcome: "completed" | "partially_completed" | "failed" | null;
  rows_matched: number;
  rows_old_only: number;
  rows_view_only: number;
  rows_with_column_mismatch: number;
  row_inflation_flagged: boolean;
  discrepancy_detail: DiscrepancyDetailEntry[];
}

// --- XML field mappings & lookup (User Story 4) ---

export interface XmlFieldPathEntry {
  legacy_column: string;
  xpath: string;
  cast_type: string;
}

export interface XmlFieldMapping {
  id: string;
  legacy_shape_capture_id: string;
  xml_connection_id: string;
  xml_table_name: string;
  xml_identity_column: string;
  xml_payload_column: string;
  current_version_id: string | null;
}

export interface XmlFieldMappingVersion {
  id: string;
  xml_field_mapping_id: string;
  version_number: number;
  field_paths: XmlFieldPathEntry[];
}

export interface XmlLookupResult {
  identity: string;
  legacy_column: string;
  outcome: "found" | "field_missing" | "document_not_found";
  value?: string | null;
}
