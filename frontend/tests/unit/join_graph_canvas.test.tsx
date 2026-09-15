import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JoinGraphCanvas, layoutJoinGraphNodes } from "../../src/components/canvas/JoinGraphCanvas";
import { edgesToJoinGraph, joinGraphToEdges } from "../../src/components/canvas/joinEdgeConversion";

describe("JoinGraphCanvas", () => {
  it("renders a node with every column for each table", () => {
    render(
      <JoinGraphCanvas
        tables={[
          { name: "dbo.loan_application", columns: ["application_id", "status"] },
          { name: "dbo.loan_applicant", columns: ["application_id", "first_name"] },
        ]}
        joinGraph={[]}
        onJoinGraphChange={vi.fn()}
      />,
    );
    expect(screen.getByText("dbo.loan_application")).toBeInTheDocument();
    expect(screen.getByText("dbo.loan_applicant")).toBeInTheDocument();
    expect(screen.getByText("first_name")).toBeInTheDocument();
  });

  it("converts a join edge into a React Flow edge referencing table::column handles", () => {
    const edges = joinGraphToEdges([
      {
        left_table: "dbo.loan_application",
        left_column: "application_id",
        right_table: "dbo.loan_applicant",
        right_column: "application_id",
        join_type: "inner",
      },
    ]);
    expect(edges).toEqual([
      {
        id: "dbo.loan_application.application_id->dbo.loan_applicant.application_id",
        source: "table:dbo.loan_application",
        sourceHandle: "dbo.loan_application::application_id",
        target: "table:dbo.loan_applicant",
        targetHandle: "dbo.loan_applicant::application_id",
        data: { join_type: "inner" },
        label: "INNER JOIN",
        labelStyle: { fill: "#16385e", fontWeight: 700, fontSize: 11 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.92 },
        labelBgPadding: [5, 3],
      },
    ]);
  });

  it("lays out table pairs with enough vertical room for their fields", () => {
    const nodes = layoutJoinGraphNodes([
      { name: "dbo.loan_application", columns: Array.from({ length: 12 }, (_, i) => `a${i}`) },
      { name: "dbo.loan_applicant", columns: Array.from({ length: 4 }, (_, i) => `b${i}`) },
      { name: "dbo.loan_collateral", columns: ["application_id"] },
      { name: "dbo.loan_underwriting", columns: ["application_id", "decision"] },
    ]);

    expect(nodes[0].position).toEqual({ x: 0, y: 0 });
    expect(nodes[1].position).toEqual({ x: 390, y: 0 });
    expect(nodes[2].position.y).toBeGreaterThan(300);
    expect(nodes).toHaveLength(4);
    expect(nodes[3].position).toEqual({ x: 390, y: nodes[2].position.y });
  });

  it("converts edges back into join-graph edges, and removing an edge removes its join", () => {
    const edges = joinGraphToEdges([
      {
        left_table: "dbo.loan_application",
        left_column: "application_id",
        right_table: "dbo.loan_applicant",
        right_column: "application_id",
        join_type: "inner",
      },
      {
        left_table: "dbo.loan_application",
        left_column: "application_id",
        right_table: "dbo.loan_collateral",
        right_column: "application_id",
        join_type: "left",
      },
    ]);
    const remaining = edges.filter(
      (edge) =>
        edge.id !== "dbo.loan_application.application_id->dbo.loan_collateral.application_id",
    );
    expect(edgesToJoinGraph(remaining)).toEqual([
      {
        left_table: "dbo.loan_application",
        left_column: "application_id",
        right_table: "dbo.loan_applicant",
        right_column: "application_id",
        join_type: "inner",
      },
    ]);
  });

  it("calls onJoinGraphChange with an empty array when there are no joins drawn", () => {
    const onJoinGraphChange = vi.fn();
    render(
      <JoinGraphCanvas
        tables={[{ name: "dbo.loan_application", columns: ["application_id"] }]}
        joinGraph={[]}
        onJoinGraphChange={onJoinGraphChange}
      />,
    );
    expect(onJoinGraphChange).not.toHaveBeenCalled();
  });
});
