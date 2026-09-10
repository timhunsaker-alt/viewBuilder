import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JoinGraphCanvas } from "../../src/components/canvas/JoinGraphCanvas";
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
      },
    ]);
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
