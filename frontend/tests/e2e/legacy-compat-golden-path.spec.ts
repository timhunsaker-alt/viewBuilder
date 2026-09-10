import { type Page, expect, test } from "@playwright/test";

/**
 * End-to-end smoke test for the full 002-legacy-compat-view quickstart.md golden path
 * (T049):
 *   capture legacy shape → build join graph + column map → preview → deploy →
 *   reconcile → XML lookup
 *
 * This drives the real pages/selectors in `frontend/src/pages` and
 * `frontend/src/components/canvas` — it does not mock the API. Mirrors the skip-
 * cleanly pattern already used by `frontend/tests/e2e/golden-path.spec.ts` (001): it
 * requires a live backend (proxying `/api`, see `frontend/vite.config.ts`) and a real
 * MS SQL Server reachable at whatever `connection_config` the test creates, seeded per
 * `backend/docker/mssql-init/seed.sql`'s "002-legacy-compat-view fixture" tables
 * (`dbo.legacy_loan_application`, the 5-table `dbo.loan_*` replacement schema, and
 * `dbo.legacy_application_xml`). If no live SQL Server is reachable, this spec skips
 * rather than failing the whole suite.
 */

const CONNECTION_NAME = `e2e-legacy-compat-${Date.now()}`;

async function seedConnection(page: Page): Promise<string | null> {
  const response = await page.request.post("/api/v1/connections", {
    data: {
      name: CONNECTION_NAME,
      role: "either",
      environment: "dev",
      host: "localhost",
      port: 1433,
      database: "master",
      credential_ref: "e2e-local-sa",
    },
  });
  if (!response.ok()) {
    return null;
  }
  const body = (await response.json()) as { id: string };
  return body.id;
}

async function mssqlReachable(page: Page, connectionId: string): Promise<boolean> {
  const response = await page.request.get(`/api/v1/connections/${connectionId}/schema`);
  return response.ok();
}

// Every dbo.legacy_loan_application column → its source in the 5-table replacement
// schema (backend/docker/mssql-init/seed.sql), used to fill in the column-mapping
// table (FR-003/FR-004) exactly the way an engineer would on the real page.
const COLUMN_MAPPINGS: Array<{ legacyColumn: string; sourceTable: string; sourceColumn: string }> =
  [
    {
      legacyColumn: "application_id",
      sourceTable: "dbo.loan_application",
      sourceColumn: "application_id",
    },
    {
      legacyColumn: "applicant_first_name",
      sourceTable: "dbo.loan_applicant",
      sourceColumn: "first_name",
    },
    {
      legacyColumn: "applicant_last_name",
      sourceTable: "dbo.loan_applicant",
      sourceColumn: "last_name",
    },
    {
      legacyColumn: "applicant_ssn_last4",
      sourceTable: "dbo.loan_applicant",
      sourceColumn: "ssn_last4",
    },
    { legacyColumn: "applicant_email", sourceTable: "dbo.loan_applicant", sourceColumn: "email" },
    { legacyColumn: "applicant_phone", sourceTable: "dbo.loan_applicant", sourceColumn: "phone" },
    {
      legacyColumn: "loan_amount_cents",
      sourceTable: "dbo.loan_application",
      sourceColumn: "loan_amount_cents",
    },
    {
      legacyColumn: "loan_purpose",
      sourceTable: "dbo.loan_application",
      sourceColumn: "loan_purpose",
    },
    {
      legacyColumn: "interest_rate_bps",
      sourceTable: "dbo.loan_application",
      sourceColumn: "interest_rate_bps",
    },
    {
      legacyColumn: "term_months",
      sourceTable: "dbo.loan_application",
      sourceColumn: "term_months",
    },
    {
      legacyColumn: "collateral_description",
      sourceTable: "dbo.loan_collateral",
      sourceColumn: "description",
    },
    {
      legacyColumn: "collateral_value_cents",
      sourceTable: "dbo.loan_collateral",
      sourceColumn: "value_cents",
    },
    {
      legacyColumn: "collateral_type",
      sourceTable: "dbo.loan_collateral",
      sourceColumn: "collateral_type",
    },
    {
      legacyColumn: "underwriter_name",
      sourceTable: "dbo.loan_underwriting",
      sourceColumn: "underwriter_name",
    },
    {
      legacyColumn: "underwriting_decision",
      sourceTable: "dbo.loan_underwriting",
      sourceColumn: "decision",
    },
    {
      legacyColumn: "underwriting_score",
      sourceTable: "dbo.loan_underwriting",
      sourceColumn: "score",
    },
    {
      legacyColumn: "document_ref_number",
      sourceTable: "dbo.loan_document_ref",
      sourceColumn: "document_ref_number",
    },
    {
      legacyColumn: "application_date",
      sourceTable: "dbo.loan_application",
      sourceColumn: "application_date",
    },
    { legacyColumn: "status", sourceTable: "dbo.loan_application", sourceColumn: "status" },
  ];

const NEW_SCHEMA_TABLES = [
  "dbo.loan_application",
  "dbo.loan_applicant",
  "dbo.loan_collateral",
  "dbo.loan_underwriting",
  "dbo.loan_document_ref",
];

// Star join: every satellite table joins back to dbo.loan_application on
// application_id (research.md §4).
const JOIN_EDGES: Array<{ leftTable: string; rightTable: string }> = [
  { leftTable: "dbo.loan_applicant", rightTable: "dbo.loan_application" },
  { leftTable: "dbo.loan_collateral", rightTable: "dbo.loan_application" },
  { leftTable: "dbo.loan_underwriting", rightTable: "dbo.loan_application" },
  { leftTable: "dbo.loan_document_ref", rightTable: "dbo.loan_application" },
];

async function drawJoinEdge(page: Page, leftTable: string, rightTable: string) {
  const sourceHandle = page
    .locator(`.react-flow__handle[data-handleid="${leftTable}::application_id"]`)
    .first();
  const targetHandle = page
    .locator(`.react-flow__handle[data-handleid="${rightTable}::application_id"]`)
    .first();
  await expect(sourceHandle).toBeVisible();
  await expect(targetHandle).toBeVisible();
  const sourceBox = await sourceHandle.boundingBox();
  const targetBox = await targetHandle.boundingBox();
  if (sourceBox && targetBox) {
    await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, {
      steps: 10,
    });
    await page.mouse.up();
  }
}

test.describe("legacy-compat golden path: capture shape → join graph + column map → preview → deploy → reconcile → XML lookup", () => {
  test("full quickstart.md flow against a live backend + seeded MS SQL Server", async ({
    page,
  }) => {
    const connectionId = await seedConnection(page);
    test.skip(connectionId === null, "backend not reachable at the expected proxy target");
    // biome-ignore lint/style/noNonNullAssertion: skipped above when null
    const reachable = await mssqlReachable(page, connectionId!);
    test.skip(
      !reachable,
      "no live MS SQL Server / ODBC driver reachable in this environment — " +
        "see backend/docker/docker-compose.yml + quickstart.md for the seeded fixture " +
        "this test exercises when one is available",
    );

    // 1. Capture the legacy shape (quickstart.md step 1) via the API — there is no
    //    legacy-shape-capture form in the UI (mirrors 001's connection-creation gap).
    const legacyShapeResponse = await page.request.post("/api/v1/legacy-shapes", {
      data: {
        name: `e2e-legacy-loan-shape-${Date.now()}`,
        connection_id: connectionId,
        table_name: "dbo.legacy_loan_application",
      },
    });
    expect(legacyShapeResponse.ok()).toBe(true);
    const legacyShape = (await legacyShapeResponse.json()) as { id: string };

    // 2. Open the view-definition editor and fill in name / legacy shape / target
    //    connection (quickstart.md step 2).
    await page.goto("/view-definitions/new");
    await expect(page.getByRole("heading", { name: "New compatibility view" })).toBeVisible();
    const viewName = `e2e_loan_compat_view_${Date.now()}`;
    await page.getByLabel("View name").fill(viewName);
    await page.getByLabel("Legacy shape").selectOption(legacyShape.id);
    await page.getByLabel("Target connection").selectOption(connectionId as string);

    // 3. Select the 5 normalized replacement tables.
    for (const table of NEW_SCHEMA_TABLES) {
      await page.getByRole("listitem").filter({ hasText: table }).getByRole("checkbox").check();
    }
    await expect(page.getByText("5. Join graph")).toBeVisible();

    // 4. Draw the star join graph (FR-002) — every satellite table to
    //    dbo.loan_application on application_id.
    for (const edge of JOIN_EDGES) {
      await drawJoinEdge(page, edge.leftTable, edge.rightTable);
    }

    // 5. Column mapping (FR-003/FR-004): map every legacy column to its source.
    await expect(page.getByText("6. Column mapping")).toBeVisible();
    for (const mapping of COLUMN_MAPPINGS) {
      await page
        .getByLabel(`Source table for ${mapping.legacyColumn}`)
        .selectOption(mapping.sourceTable);
      await page
        .getByLabel(`Source column or expression for ${mapping.legacyColumn}`)
        .fill(mapping.sourceColumn);
    }
    await expect(page.getByText("Every legacy column must be mapped")).toHaveCount(0);

    // 6. Save the view definition.
    const saveButton = page.getByRole("button", { name: "Save view definition" });
    await expect(saveButton).toBeEnabled();
    await saveButton.click();
    await expect(page).toHaveURL(/\/view-definitions\/[0-9a-f-]+$/);
    await expect(page.getByRole("heading", { name: "Version history" })).toBeVisible();
    const viewDefinitionUrl = page.url();
    const viewDefinitionId = viewDefinitionUrl.split("/view-definitions/")[1];

    // 7. Preview (FR-005, zero DDL) then deploy (FR-006) — quickstart.md steps 4-5.
    await page.getByRole("link", { name: /Preview & deploy current version/ }).click();
    await expect(page.getByRole("heading", { name: /Preview & deploy/ })).toBeVisible();
    await page.getByRole("button", { name: "Run preview" }).click();
    await expect(page.getByRole("heading", { name: "Generated SQL" })).toBeVisible();
    await expect(page.locator("pre")).toContainText("CREATE OR ALTER VIEW");

    const deployButton = page.getByRole("button", { name: "Deploy for real" });
    await expect(deployButton).toBeVisible();
    // dev connection, so ProductionGuard renders a plain button (no confirmation
    // dialog) — same pattern as 001's golden-path.spec.ts step 7.
    await expect(page.getByTestId("production-guard")).toHaveCount(0);
    await deployButton.click();
    await expect(page.getByRole("heading", { name: "Deploy result" })).toBeVisible();
    await expect(page.getByText(/Outcome: completed/)).toBeVisible();

    // 8. Reconcile the deployed view against the still-live old table (FR-009,
    //    quickstart.md step 6) — a clean deploy is expected to report zero
    //    discrepancies.
    await page.goto(`/view-definitions/${viewDefinitionId}/reconcile`);
    await expect(page.getByRole("heading", { name: /Reconcile:/ })).toBeVisible();
    await page.getByLabel("Identity column").selectOption("application_id");
    await page.getByRole("button", { name: "Run reconciliation" }).click();
    await expect(page.getByRole("heading", { name: "Counts" })).toBeVisible();
    await expect(page.getByText("Clean reconciliation — zero discrepancies.")).toBeVisible();

    // 9. XML fallback lookup (FR-011/FR-012, quickstart.md step 7): configure a field
    //    path and confirm the "field_missing" outcome for application_id 5, whose
    //    seeded XML document deliberately omits <CollateralValue> (mirroring that same
    //    row's NULL collateral value_cents in the normalized schema).
    const xmlMappingResponse = await page.request.post("/api/v1/xml-field-mappings", {
      data: {
        legacy_shape_capture_id: legacyShape.id,
        xml_connection_id: connectionId,
        xml_table_name: "dbo.legacy_application_xml",
        xml_identity_column: "application_id",
        xml_payload_column: "xml_payload",
        field_paths: [],
      },
    });
    expect(xmlMappingResponse.ok()).toBe(true);
    const xmlMapping = (await xmlMappingResponse.json()) as { id: string };

    await page.goto(
      `/view-definitions/${viewDefinitionId}/xml-lookup?identity=5&legacy_column=collateral_value_cents`,
    );
    await expect(page.getByRole("heading", { name: "XML fallback lookup" })).toBeVisible();
    await page.getByLabel("XML field mapping").selectOption(xmlMapping.id);
    await page.getByRole("button", { name: "Run lookup" }).click();
    await expect(page.getByText(/No XML field path is configured yet/)).toBeVisible();
    await page.getByLabel("XPath").fill("(/Application/CollateralValue)[1]");
    await page.getByLabel("Cast type").fill("BIGINT");
    await page.getByRole("button", { name: "Save field path & look up" }).click();
    await expect(page.getByText("Outcome: field_missing")).toBeVisible();
    await expect(
      page.getByText("Document exists, but this field is absent from it."),
    ).toBeVisible();
  });
});
