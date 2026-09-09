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
import { edgesToLinks, linksToEdges } from "./linkEdgeConversion";

export interface ColumnMappingLink {
  sourceColumn: string;
  targetColumn: string;
  enumTranslationVersionId?: string;
}

interface ColumnNodeData {
  label: string;
  columnName: string;
}

function ColumnNode({ data, side }: { data: ColumnNodeData; side: "source" | "target" }) {
  return (
    <div className="column-node" data-side={side}>
      {side === "target" && <Handle type="target" position={Position.Left} id={data.columnName} />}
      <span>{data.label}</span>
      {side === "source" && <Handle type="source" position={Position.Right} id={data.columnName} />}
    </div>
  );
}

const nodeTypes = {
  sourceColumn: (props: { data: ColumnNodeData }) => <ColumnNode {...props} side="source" />,
  targetColumn: (props: { data: ColumnNodeData }) => <ColumnNode {...props} side="target" />,
};

interface MappingCanvasProps {
  sourceColumns: string[];
  targetColumns: string[];
  links: ColumnMappingLink[];
  onLinksChange: (links: ColumnMappingLink[]) => void;
}

/**
 * Renders source columns and target columns as two columns of nodes; a user-drawn edge
 * between a source column's handle and a target column's handle becomes a column mapping
 * link (FR-003). Removing an edge removes the corresponding link.
 */
export function MappingCanvas({
  sourceColumns,
  targetColumns,
  links,
  onLinksChange,
}: MappingCanvasProps) {
  const initialNodes = useMemo<Node[]>(() => {
    const sourceNodes = sourceColumns.map((column, index) => ({
      id: `source:${column}`,
      type: "sourceColumn",
      position: { x: 0, y: index * 60 },
      data: { label: column, columnName: column },
    }));
    const targetNodes = targetColumns.map((column, index) => ({
      id: `target:${column}`,
      type: "targetColumn",
      position: { x: 400, y: index * 60 },
      data: { label: column, columnName: column },
    }));
    return [...sourceNodes, ...targetNodes];
  }, [sourceColumns, targetColumns]);

  const initialEdges = useMemo<Edge[]>(() => linksToEdges(links), [links]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => setNodes(initialNodes), [initialNodes, setNodes]);

  const emitLinksFromEdges = useCallback(
    (nextEdges: Edge[]) => onLinksChange(edgesToLinks(nextEdges)),
    [onLinksChange],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((current) => {
        const next = addEdge(connection, current);
        emitLinksFromEdges(next);
        return next;
      });
    },
    [setEdges, emitLinksFromEdges],
  );

  const handleEdgesChange: typeof onEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      const hasRemoval = changes.some((change) => change.type === "remove");
      if (hasRemoval) {
        setEdges((current) => {
          emitLinksFromEdges(current);
          return current;
        });
      }
    },
    [onEdgesChange, setEdges, emitLinksFromEdges],
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
