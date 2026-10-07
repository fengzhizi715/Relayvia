import { useEffect } from "react";

import { useTranslation } from "../i18n";

/** Pull the page back to the last valid page when the total shrinks (e.g. the
 * current page was emptied by an archive or a concurrent change). `total`
 * must stay undefined until the current page's response is known, otherwise a
 * page change would clamp itself back before its own data arrives. */
export function usePageClamp(page: number, pageSize: number, total: number | undefined, onPageChange: (page: number) => void) {
  useEffect(() => {
    if (total === undefined) return;
    const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1);
    if (page > lastPage) onPageChange(lastPage);
  }, [page, pageSize, total, onPageChange]);
}

type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
};

export function Pagination({ page, pageSize, total, onPageChange, disabled = false }: PaginationProps) {
  const { t } = useTranslation();
  if (total <= 0) return null;

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(page, 0), pageCount - 1);
  const start = current * pageSize + 1;
  const end = Math.min(total, (current + 1) * pageSize);

  return (
    <nav className="pagination" aria-label={t("pagination.label")}>
      <button
        className="button button--small"
        disabled={disabled || current <= 0}
        onClick={() => onPageChange(current - 1)}
        type="button"
      >
        {t("pagination.previous")}
      </button>
      <span className="pagination-status">
        {t("pagination.pageOf", { page: current + 1, pages: pageCount })} · {t("pagination.range", { start, end, total })}
      </span>
      <button
        className="button button--small"
        disabled={disabled || current >= pageCount - 1}
        onClick={() => onPageChange(current + 1)}
        type="button"
      >
        {t("pagination.next")}
      </button>
    </nav>
  );
}
