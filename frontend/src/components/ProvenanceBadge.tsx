import "./ProvenanceBadge.css";

const BADGE_COLORS: Record<string, string> = {
  curated: "#27AE60",
  literature: "#2980B9",
  inferred: "#F39C12",
  "ai-generated": "#8E44AD",
};

const BADGE_LABELS: Record<string, string> = {
  curated: "CURATED",
  literature: "LITERATURE",
  inferred: "INFERRED",
  "ai-generated": "AI-GENERATED",
};

interface Props {
  type: string;
}

export default function ProvenanceBadge({ type }: Props) {
  const color = BADGE_COLORS[type] || BADGE_COLORS.inferred;
  const label = BADGE_LABELS[type] || type.toUpperCase();

  return (
    <span className="provenance-badge" style={{ background: color }}>
      {label}
    </span>
  );
}
