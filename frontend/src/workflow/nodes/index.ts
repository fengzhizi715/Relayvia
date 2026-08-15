import type { NodeTypes } from "@xyflow/react";

import { AgentNode } from "./AgentNode";
import { ConditionNode } from "./ConditionNode";
import { DataNode } from "./DataNode";
import { HumanNode } from "./HumanNode";
import { MergeNode } from "./MergeNode";
import { ParallelNode } from "./ParallelNode";
import { RouterNode } from "./RouterNode";
import { ServiceNode } from "./ServiceNode";
import { ToolNode } from "./ToolNode";
import { WaitNode } from "./WaitNode";

export const nodeTypes: NodeTypes = {
  agent: AgentNode,
  service: ServiceNode,
  tool: ToolNode,
  condition: ConditionNode,
  parallel: ParallelNode,
  merge: MergeNode,
  router: RouterNode,
  wait: WaitNode,
  human: HumanNode,
  data: DataNode,
};
