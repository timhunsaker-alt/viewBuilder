import {
  Background,
  type Connection,
  Controls,
  type Edge,
  Handle,
  MiniMap,
  type Node,
  Position,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
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
      <div className="join-graph-table-node__header">
        <strong>{data.label}</strong>
        <span>{data.columns.length} fields</span>
      </div>
      <ul className="join-graph-table-node__columns">
        {data.columns.map((column) => (
          <li key={column} data-column={column}>
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

function estimateNodeHeight(table: JoinGraphTable): number {
  return 58 + Math.max(table.columns.length, 1) * 27;
}

/** Places tables in readable pairs, with vertical space based on their field counts. */
export function layoutJoinGraphNodes(tables: JoinGraphTable[]): Node[] {
  let nextRowY = 0;
  return tables.map((table, index) => {
    const isLeftColumn = index % 2 === 0;
    const previousTable = isLeftColumn ? undefined : tables[index - 1];
    const position = {
      x: isLeftColumn ? 0 : 390,
      y: isLeftColumn ? nextRowY : nextRowY,
    };

    if (!isLeftColumn) {
      nextRowY +=
        Math.max(estimateNodeHeight(previousTable ?? table), estimateNodeHeight(table)) + 72;
    }
    if (isLeftColumn && index === tables.length - 1) {
      nextRowY += estimateNodeHeight(table) + 72;
    }

    return {
      id: `table:${table.name}`,
      type: "joinTable",
      position,
      data: { label: table.name, columns: table.columns },
    };
  });
}

/**
 * Renders every selected new-schema table as a node with one row per column; a
 * user-drawn edge between two columns' handles becomes a join edge (FR-002). Removing
 * an edge removes the corresponding join. Reachability (no orphan table) is validated
 * server-side (view_definition_service.validate_join_graph) when the definition is
 * saved — this component only captures what the user drew.
 */
export function JoinGraphCanvas({ tables, joinGraph, onJoinGraphChange }: JoinGraphCanvasProps) {
  const initialNodes = useMemo<Node[]>(() => layoutJoinGraphNodes(tables), [tables]);

  const initialEdges = useMemo<Edge[]>(() => joinGraphToEdges(joinGraph), [joinGraph]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Table schema responses arrive independently. Preserve an operator's drag position
  // while their column lists fill in, adding only genuinely new tables at a sensible spot.
  useEffect(() => {
    setNodes((current) => {
      const positions = new Map(current.map((node) => [node.id, node.position]));
      return initialNodes.map((node) => ({
        ...node,
        position: positions.get(node.id) ?? node.position,
      }));
    });
  }, [initialNodes, setNodes]);

  // A saved view supplies its joins after the editor loads its current version. Keep
  // the canvas synchronized with that external value as well as with newly drawn edges.
  useEffect(() => setEdges(initialEdges), [initialEdges, setEdges]);

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
      setEdges((current) => {
        const next = applyEdgeChanges(changes, current);
        if (changes.some((change) => change.type === "remove")) {
          emitJoinGraphFromEdges(next);
        }
        return next;
      });
    },
    [setEdges, emitJoinGraphFromEdges],
  );

  return (
    <div className="join-graph-workspace">
      <div className="join-graph-workspace__toolbar">
        <div>
          <strong>Connect matching fields</strong>
          <span>Drag tables to arrange them. Draw from a field on one table to its match.</span>
        </div>
        <span className="join-graph-workspace__summary">
          {tables.length} tables · {joinGraph.length} joins
        </span>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        snapToGrid
        snapGrid={[16, 16]}
        defaultEdgeOptions={{ type: "smoothstep", style: { stroke: "#2f6fe0", strokeWidth: 2 } }}
      >
        <Background gap={16} size={1} />
        <MiniMap pannable zoomable nodeColor="#eaf1fd" maskColor="rgba(10, 31, 61, 0.12)" />
        <Controls />
      </ReactFlow>
    </div>
  );
}
