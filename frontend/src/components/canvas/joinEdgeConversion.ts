import type { Edge } from "@xyflow/react";
import type { JoinGraphEdge } from "../../services/api";

function columnHandleId(table: string, column: string): string {
  return `${table}::${column}`;
}

export function joinGraphToEdges(joinGraph: JoinGraphEdge[]): Edge[] {
  return joinGraph.map((edge) => ({
    id: `${edge.left_table}.${edge.left_column}->${edge.right_table}.${edge.right_column}`,
    source: `table:${edge.left_table}`,
    sourceHandle: columnHandleId(edge.left_table, edge.left_column),
    target: `table:${edge.right_table}`,
    targetHandle: columnHandleId(edge.right_table, edge.right_column),
    data: { join_type: edge.join_type },
  }));
}

/**
 * The inverse of `joinGraphToEdges` — a React Flow edge's handle ids encode
 * `table::column`, so the join edge is reconstructed directly from them without
 * needing any other lookup (research.md §4).
 */
export function edgesToJoinGraph(edges: Edge[]): JoinGraphEdge[] {
  return edges
    .map((edge) => {
      const [leftTable, leftColumn] = (edge.sourceHandle ?? "").split("::");
      const [rightTable, rightColumn] = (edge.targetHandle ?? "").split("::");
      if (!leftTable || !leftColumn || !rightTable || !rightColumn) {
        return null;
      }
      const joinType = (edge.data?.join_type as "inner" | "left" | undefined) ?? "inner";
      return {
        left_table: leftTable,
        left_column: leftColumn,
        right_table: rightTable,
        right_column: rightColumn,
        join_type: joinType,
      };
    })
    .filter((edge): edge is JoinGraphEdge => edge !== null);
}
