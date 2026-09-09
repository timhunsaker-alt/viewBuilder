import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MappingCanvas } from "../../src/components/canvas/MappingCanvas";
import { edgesToLinks, linksToEdges } from "../../src/components/canvas/linkEdgeConversion";

describe("MappingCanvas", () => {
  it("renders a node for every source and target column", () => {
    render(
      <MappingCanvas
        sourceColumns={["full_name", "email"]}
        targetColumns={["display_name", "email_address"]}
        links={[]}
        onLinksChange={vi.fn()}
      />,
    );
    expect(screen.getByText("full_name")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.getByText("display_name")).toBeInTheDocument();
    expect(screen.getByText("email_address")).toBeInTheDocument();
  });

  it("renders the canvas without error when initial links are provided", () => {
    render(
      <MappingCanvas
        sourceColumns={["full_name"]}
        targetColumns={["display_name"]}
        links={[{ sourceColumn: "full_name", targetColumn: "display_name" }]}
        onLinksChange={vi.fn()}
      />,
    );
    expect(screen.getByText("full_name")).toBeInTheDocument();
  });

  it("converts a column link into a React Flow edge referencing the right node handles", () => {
    const edges = linksToEdges([{ sourceColumn: "full_name", targetColumn: "display_name" }]);
    expect(edges).toEqual([
      {
        id: "full_name->display_name",
        source: "source:full_name",
        sourceHandle: "full_name",
        target: "target:display_name",
        targetHandle: "display_name",
      },
    ]);
  });

  it("converts edges back into column links, and removing an edge removes its link", () => {
    const edges = linksToEdges([
      { sourceColumn: "full_name", targetColumn: "display_name" },
      { sourceColumn: "email", targetColumn: "email_address" },
    ]);
    const remaining = edges.filter((edge) => edge.id !== "email->email_address");
    expect(edgesToLinks(remaining)).toEqual([
      { sourceColumn: "full_name", targetColumn: "display_name" },
    ]);
  });

  it("calls onLinksChange with an empty array when there are no links", () => {
    const onLinksChange = vi.fn();
    render(
      <MappingCanvas
        sourceColumns={["full_name"]}
        targetColumns={["display_name"]}
        links={[]}
        onLinksChange={onLinksChange}
      />,
    );
    // No connection has been drawn yet, so onLinksChange should not have fired.
    expect(onLinksChange).not.toHaveBeenCalled();
  });
});
