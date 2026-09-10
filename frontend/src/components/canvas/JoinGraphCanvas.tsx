import {
  Background,
  type Connection,
  Controls,
  type Edge,
  Handle,
  type Node,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo } from "react";
import type { JoinGraphEdge } from "../../services/api";
import { edgesToJoinGraph, joinGraphToEdges } from "./joinEdgeConversion";

export interface JoinGraphTable {
  name: string;
  columns: string[];
}

interface TableNodeData {
  label: string;
  columns: string[];
}

/**
 * A multi-source-table node: one row per column, each row carrying both a target
 * handle (left) and a source handle (right) so a join edge can be drawn between any
 * two tables' columns in either direction (research.md §4) — distinct from
 * MappingCanvas's single-direction source-column/target-column split, since here
 * every table plays both roles depending on which side of a given join it's on.
 */
function TableNode({ data }: { data: TableNodeData }) {
  return (
    <div className="join-graph-table-node">
      <strong>{data.label}</strong>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {data.columns.map((column) => (
          <li key={column} data-column={column} style={{ position: "relative" }}>
            <Handle
              type="target"
              position={Position.Left}
              id={`${data.label}::${column}`}
              style={{ top: "auto" }}
            />
            <span>{column}</span>
            <Handle
              type="source"
              position={Position.Right}
              id={`${data.label}::${column}`}
              style={{ top: "auto" }}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

const nodeTypes = { joinTable: TableNode };

interface JoinGraphCanvasProps {
  tables: JoinGraphTable[];
  joinGraph: JoinGraphEdge[];
  onJoinGraphChange: (joinGraph: JoinGraphEdge[]) => void;
}

/**
 * Renders every selected new-schema table as a node with one row per column; a
 * user-drawn edge between two columns' handles becomes a join edge (FR-002). Removing
 * an edge removes the corresponding join. Reachability (no orphan table) is validated
 * server-side (view_definition_service.validate_join_graph) when the definition is
 * saved — this component only captures what the user drew.
 */
export function JoinGraphCanvas({ tables, joinGraph, onJoinGraphChange }: JoinGraphCanvasProps) {
  const initialNodes = useMemo<Node[]>(
    () =>
      tables.map((table, index) => ({
        id: `table:${table.name}`,
        type: "joinTable",
        position: { x: (index % 3) * 260, y: Math.floor(index / 3) * 220 },
        data: { label: table.name, columns: table.columns },
      })),
    [tables],
  );

  const initialEdges = useMemo<Edge[]>(() => joinGraphToEdges(joinGraph), [joinGraph]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => setNodes(initialNodes), [initialNodes, setNodes]);

  const emitJoinGraphFromEdges = useCallback(
    (nextEdges: Edge[]) => onJoinGraphChange(edgesToJoinGraph(nextEdges)),
    [onJoinGraphChange],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((current) => {
        const next = addEdge({ ...connection, data: { join_type: "inner" } }, current);
        emitJoinGraphFromEdges(next);
        return next;
      });
    },
    [setEdges, emitJoinGraphFromEdges],
  );

  const handleEdgesChange: typeof onEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      const hasRemoval = changes.some((change) => change.type === "remove");
      if (hasRemoval) {
        setEdges((current) => {
          emitJoinGraphFromEdges(current);
          return current;
        });
      }
    },
    [onEdgesChange, setEdges, emitJoinGraphFromEdges],
  );

  return (
    <div style={{ height: 500, border: "1px solid #ccc" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
