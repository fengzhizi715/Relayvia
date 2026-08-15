type ResourceEmptyStateProps = {
  title: string;
  message: string;
  actionLabel: string;
  onAction: () => void;
};

export function ResourceEmptyState({ title, message, actionLabel, onAction }: ResourceEmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-icon">+</div>
      <h3>{title}</h3>
      <p>{message}</p>
      <button className="button button--primary" onClick={onAction} type="button">
        {actionLabel}
      </button>
    </div>
  );
}

