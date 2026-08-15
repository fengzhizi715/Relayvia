type StatusBadgeProps = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
};

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}
