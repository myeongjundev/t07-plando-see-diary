import { request } from "./http";

export type Priority = "high" | "medium" | "low";

export interface Plan {
  id: string;
  title: string;
  startDate: string;
  endDate: string;
  priority: Priority;
  successCriterion: string;
  estimatedMinutes: number;
  durationUnit: "minutes";
  carriedImprovement: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PlanInput {
  title: string;
  startDate: string;
  endDate: string;
  priority: Priority;
  successCriterion: string;
  estimatedMinutes: number;
  carriedImprovement: string | null;
}

export interface PlanRevision extends Plan {
  revisionId: string;
  planId: string;
  revisionNumber: number;
  replacedAt: string;
}

export async function listPlans(): Promise<Plan[]> {
  return (await request<{ plans: Plan[] }>("/api/plans")).plans;
}

export async function createPlan(input: PlanInput): Promise<Plan> {
  return (
    await request<{ plan: Plan }>("/api/plans", {
      method: "POST",
      body: JSON.stringify(input),
    })
  ).plan;
}

export async function updatePlan(id: string, input: Partial<PlanInput>): Promise<Plan> {
  return (
    await request<{ plan: Plan }>(`/api/plans/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    })
  ).plan;
}

export async function listPlanRevisions(id: string): Promise<PlanRevision[]> {
  return (await request<{ revisions: PlanRevision[] }>(`/api/plans/${id}/revisions`)).revisions;
}
