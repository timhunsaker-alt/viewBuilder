import type { Edge } from "@xyflow/react";
import type { ColumnMappingLink } from "./MappingCanvas";

export function linksToEdges(links: ColumnMappingLink[]): Edge[] {
  return links.map((link) => ({
    id: `${link.sourceColumn}->${link.targetColumn}`,
    source: `source:${link.sourceColumn}`,
    sourceHandle: link.sourceColumn,
    target: `target:${link.targetColumn}`,
    targetHandle: link.targetColumn,
  }));
}

export function edgesToLinks(edges: Edge[]): ColumnMappingLink[] {
  return edges.map((edge) => ({
    sourceColumn: edge.sourceHandle ?? "",
    targetColumn: edge.targetHandle ?? "",
  }));
}
