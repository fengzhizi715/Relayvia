import { useStore } from "@xyflow/react";

import { useTranslation, type TranslationKey } from "../../i18n";
import { PALETTE_ITEMS, type PaletteCategory } from "../factories/nodeFactory";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

const CATEGORY_ORDER: PaletteCategory[] = ["Data", "Agent", "Service", "Tool", "Logic", "Human"];

const CATEGORY_LABEL_KEYS: Record<PaletteCategory, TranslationKey> = {
  Data: "palette.category.data",
  Agent: "palette.category.agent",
  Service: "palette.category.service",
  Tool: "palette.category.tool",
  Logic: "palette.category.logic",
  Human: "palette.category.human",
};

export function NodePalette() {
  const { t } = useTranslation();
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
        <p className="eyebrow">{t("palette.eyebrow")}</p>
        <p className="field-hint">{t("palette.readOnly")}</p>
      </aside>
    );
  }

  return (
    <aside className="node-palette">
      <div className="node-palette-heading">
        <p className="eyebrow">{t("palette.heading")}</p>
        <h4>{t("palette.addNodes")}</h4>
      </div>
      {CATEGORY_ORDER.map((category) => {
        const items = PALETTE_ITEMS.filter((item) => item.category === category);
        if (items.length === 0) return null;
        return (
          <div className="palette-group" key={category}>
            <span className="palette-group-label">{t(CATEGORY_LABEL_KEYS[category])}</span>
            <div className="palette-items">
              {items.map((item) => (
                <button
                  className="palette-item"
                  key={`${item.type}.${item.subtype}`}
                  type="button"
                  title={t(item.descriptionKey)}
                  onClick={() => addNode(item.type, item.subtype, spawnPosition())}
                >
                  <span className="palette-item-glyph">{t(item.labelKey).slice(0, 2).toUpperCase()}</span>
                  <span className="palette-item-copy">
                    <strong>{t(item.labelKey)}</strong>
                    <small>{t(item.descriptionKey)}</small>
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
