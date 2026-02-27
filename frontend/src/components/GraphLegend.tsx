import { ENTITY_COLORS } from "../types";
import type { EntityType } from "../types";
import "./GraphLegend.css";

const LEGEND_ITEMS: { type: EntityType; label: string }[] = [
  { type: "gene", label: "Gene" },
  { type: "disease", label: "Disease" },
  { type: "drug", label: "Drug" },
  { type: "pathway", label: "Pathway" },
  { type: "protein", label: "Protein" },
];

export default function GraphLegend() {
  return (
    <div className="graph-legend">
      {LEGEND_ITEMS.map((item) => (
        <div key={item.type} className="graph-legend-item">
          <span
            className="graph-legend-dot"
            style={{ background: ENTITY_COLORS[item.type] }}
          />
          <span className="graph-legend-label">{item.label}</span>
        </div>
      ))}
    </div>
  );
}
