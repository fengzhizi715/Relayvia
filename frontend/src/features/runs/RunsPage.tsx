import { useEffect, useState } from "react";

import { useAppStore } from "../../app/store/useAppStore";
import { RunDetailPage } from "./RunDetailPage";
import { RunList } from "./RunList";

export function RunsPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const pendingRunId = useAppStore((state) => state.pendingRunId);
  const setPendingRunId = useAppStore((state) => state.setPendingRunId);

  useEffect(() => {
    if (pendingRunId) {
      setSelectedRunId(pendingRunId);
      setPendingRunId(null);
    }
  }, [pendingRunId, setPendingRunId]);

  if (selectedRunId) {
    return <RunDetailPage runId={selectedRunId} onBack={() => setSelectedRunId(null)} />;
  }
  return <RunList onSelect={setSelectedRunId} />;
}
