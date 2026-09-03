import { request } from "./http";

/** The metric, as the server describes it. Never re-derived on this side.
 *
 * The unit and the formula are rendered from these fields rather than written
 * into the markup, so a screen showing "배" is showing what the server computed
 * with, not a label that happens to agree with it today (T07-C13 to C15).
 */
export interface MetricDescriptor {
  key: string;
  name: string;
  unit: string;
  formula: string;
  rounding: string;
  timezone: string;
}

export interface StudyDay {
  dayNumber: number;
  date: string;
  estimatedMinutes: number;
  actualMinutes: number;
  executionCount: number;
  /** null when nothing was planned that day: 결측, not zero. */
  ratio: number | null;
}

export interface StudyExecution {
  id: string;
  taskId: string;
  taskContent: string;
  dayNumber: number;
  startedAt: string;
  endedAt: string;
  actualMinutes: number;
  blockerReason: string;
}

export interface Study {
  planId: string;
  metric: MetricDescriptor;
  startDate: string;
  endDate: string;
  days: StudyDay[];
  executions: StudyExecution[];
}

export interface ComparisonHalf {
  dayCount: number;
  daysWithoutRatio: number;
  estimatedMinutes: number;
  actualMinutes: number;
  ratio: number | null;
  days: StudyDay[];
}

export interface RuleChange {
  id: string;
  planId: string;
  changedAt: string;
  reason: string;
  ruleBefore: string;
  ruleAfter: string;
  citedExecutionIds: { day1: string; day2: string };
  createdAt: string;
  comparison: {
    metric: MetricDescriptor;
    before: ComparisonHalf;
    after: ComparisonHalf;
  };
}

export interface RuleChangeInput {
  reason: string;
  ruleBefore: string;
  ruleAfter: string;
  day1ExecutionId: string;
  day2ExecutionId: string;
}

export function getStudy(planId: string) {
  return request<Study>(`/api/plans/${planId}/study`);
}

export async function listRuleChanges(planId: string) {
  return (await request<{ ruleChanges: RuleChange[] }>(`/api/plans/${planId}/rule-changes`))
    .ruleChanges;
}

export async function saveRuleChange(planId: string, input: RuleChangeInput) {
  return (
    await request<{ ruleChange: RuleChange }>(`/api/plans/${planId}/rule-changes`, {
      method: "POST",
      body: JSON.stringify(input),
    })
  ).ruleChange;
}
