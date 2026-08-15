import { useStore } from "@xyflow/react";

import { PALETTE_ITEMS, type PaletteCategory } from "../factories/nodeFactory";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

const CATEGORY_ORDER: PaletteCategory[] = ["Data", "Agent", "Service", "Tool", "Logic", "Human"];

export function NodePalette() {
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const addNode = useWorkflowBuilderStore((state) => state.addNode);

  const viewportX = useStore((state) => state.transform[0]);
  const viewportY = useStore((state) => state.transform[1]);
  const viewportZoom = useStore((state) => state.transform[2]);
  const width = useStore((state) => state.width);
  const height = useStore((state) => state.height);

  function spawnPosition(): { x: number; y: number } {
    if (width && height && viewportZoom) {
      const flowX = (width / 2 - viewportX) / viewportZoom;
      const flowY = (height / 2 - viewportY) / viewportZoom;
      return { x: flowX + (Math.random() - 0.5) * 60, y: flowY + (Math.random() - 0.5) * 60 };
    }
    return { x: 120, y: 120 };
  }

  if (readOnly) {
    return (
      <aside className="node-palette">
        <p className="eyebrow">PALETTE</p>
        <p className="field-hint">Read-only view. Nodes cannot be added.</p>
      </aside>
    );
  }

  return (
    <aside className="node-palette">
      <div className="node-palette-heading">
        <p className="eyebrow">NODE PALETTE</p>
        <h4>Add nodes</h4>
      </div>
      {CATEGORY_ORDER.map((category) => {
        const items = PALETTE_ITEMS.filter((item) => item.category === category);
        if (items.length === 0) return null;
        return (
          <div className="palette-group" key={category}>
            <span className="palette-group-label">{category}</span>
            <div className="palette-items">
              {items.map((item) => (
                <button
                  className="palette-item"
                  key={`${item.type}.${item.subtype}`}
                  type="button"
                  title={item.description}
                  onClick={() => addNode(item.type, item.subtype, spawnPosition())}
                >
                  <span className="palette-item-glyph">{item.label.slice(0, 2).toUpperCase()}</span>
                  <span className="palette-item-copy">
                    <strong>{item.label}</strong>
                    <small>{item.description}</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </aside>
  );
}
