import { useQuery } from "@tanstack/react-query";

import { getActions, getAgents, getServices, type Agent, type Service, type ServiceAction } from "../../api/client";

/**
 * Shared TanStack Query hooks for the Builder. Registry data is cached once and
 * shared across every node card and inspector, avoiding N+1 requests.
 */
export function useAgents(): { agents: Agent[]; isLoading: boolean } {
  const query = useQuery({ queryKey: ["agents"], queryFn: getAgents });
  return { agents: query.data ?? [], isLoading: query.isLoading };
}

export function useServices(): { services: Service[]; isLoading: boolean } {
  const query = useQuery({ queryKey: ["services"], queryFn: getServices });
  return { services: query.data ?? [], isLoading: query.isLoading };
}

export function useServiceActions(
  serviceId: string | null,
): { actions: ServiceAction[]; isLoading: boolean } {
  const query = useQuery({
    queryKey: ["service-actions", serviceId],
    queryFn: () => getActions(serviceId!),
    enabled: Boolean(serviceId),
  });
  return { actions: query.data ?? [], isLoading: query.isLoading };
}

export function useServiceActionsForServices(
  serviceIds: string[],
): { byService: Map<string, ServiceAction[]>; actionsById: Map<string, ServiceAction>; isLoading: boolean } {
  const key = [...new Set(serviceIds)].sort();
  const query = useQuery({
    queryKey: ["service-actions-bulk", key],
    queryFn: async () => {
      const results = await Promise.all(
        key.map(async (serviceId) => ({ serviceId, actions: await getActions(serviceId) })),
      );
      return new Map(results.map((result) => [result.serviceId, result.actions]));
    },
    enabled: key.length > 0,
  });

  const byService = query.data ?? new Map<string, ServiceAction[]>();
  const actionsById = new Map<string, ServiceAction>();
  for (const actions of byService.values()) {
    for (const action of actions) actionsById.set(action.id, action);
  }
  return { byService, actionsById, isLoading: query.isLoading };
}
