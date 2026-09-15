import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewDefinitions } from "../../src/pages/ViewDefinitions";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ViewDefinitions />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ViewDefinitions", () => {
  it("lists saved compatibility views and links to their editor", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => {
        const path = new URL(input, "http://localhost").pathname;
        const bodyByPath: Record<string, unknown> = {
          "/api/v1/view-definitions": [
            {
              id: "view-1",
              name: "dbo.legacy_loan_application_view",
              legacy_shape_capture_id: "shape-1",
              target_connection_id: "connection-1",
              current_version_id: "version-1",
            },
          ],
          "/api/v1/legacy-shapes": [
            { id: "shape-1", name: "Loan application", table_name: "dbo.legacy_loan_application" },
          ],
          "/api/v1/connections": [
            { id: "connection-1", name: "Development SQL", environment: "dev" },
          ],
        };
        return Promise.resolve(
          new Response(JSON.stringify(bodyByPath[path]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );

    renderPage();

    expect(await screen.findByText("dbo.legacy_loan_application_view")).toBeInTheDocument();
    expect(screen.getByText("Loan application")).toBeInTheDocument();
    expect(screen.getByText("Development SQL (dev)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open →" })).toHaveAttribute(
      "href",
      "/view-definitions/view-1",
    );
  });

  it("gives a clear next step when no views have been saved", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );

    renderPage();

    expect(await screen.findByText("No compatibility views yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Capture an old table's shape →" })).toHaveAttribute(
      "href",
      "/legacy-shapes/new",
    );
  });
});
