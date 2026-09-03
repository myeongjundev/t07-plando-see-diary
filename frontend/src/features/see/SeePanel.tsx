import { FormEvent, useEffect, useRef, useState } from "react";
import type { Plan } from "../../api/plans";
import { createNextPlan, getSummary, listReflections, Metric, NextPlanInput, Period, Reflection, saveReflection, Summary } from "../../api/reflections";
import DateField from "../../components/DateField";
import Select from "../../components/Select";
import RuleChangePanel from "./RuleChangePanel";

const METRICS: { key: Metric; label: string; unit: string }[] = [
  { key: "taskCount", label: "할 일", unit: "개" },
  { key: "completedCount", label: "완료", unit: "개" },
  { key: "overdueCount", label: "지연", unit: "개" },
  { key: "blockedTaskCount", label: "막힘", unit: "개" },
  { key: "estimatedMinutes", label: "예상 시간", unit: "분" },
  { key: "actualMinutes", label: "실제 시간", unit: "분" },
  { key: "varianceMinutes", label: "차이 (실제 − 예상)", unit: "분" },
];
const seoul = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "short" });
// 회고 목록에 늘 펼쳐 두는 최근 건수. 카드 하나가 143px이라 그냥 두면 열 건에
// 1,000px이 붙고, 회고 아래의 내보내기 구획이 통째로 밀린다. 목록에 뚜껑을 씌우는
// 대신 접는 이유는 카드가 펼쳐지면 «다음 계획» 폼이 되기 때문이다 — 스크롤 상자
// 안에 폼을 가두는 건 길이보다 나쁘다.
const RECENT_REFLECTIONS = 3;
const errorText = (error: unknown) => error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
// Variance is the only metric whose sign carries meaning, so it is the only one
// that takes a semantic colour. Keep the ASCII hyphen for negatives (T06-C32).
const metricTone = (key: Metric, value: number) =>
  key !== "varianceMinutes" || value === 0 ? "" : value > 0 ? " over" : " under";
const metricValue = (key: Metric, value: number, unit: string) =>
  `${key === "varianceMinutes" && value > 0 ? "+" : ""}${value}${unit}`;
// A single total would read as a mismatch: 막힘 shows 2 tasks but is backed by
// 2 tasks and 3 logs. Name each kind instead.
function evidenceLabel(source?: { taskIds: string[]; executionIds: string[] }) {
  const tasks = source?.taskIds.length ?? 0;
  const logs = source?.executionIds.length ?? 0;
  if (tasks && logs) return `근거 할 일 ${tasks} · 기록 ${logs}`;
  if (tasks) return `근거 할 일 ${tasks}건`;
  if (logs) return `근거 기록 ${logs}건`;
  return "근거 없음";
}
function nextDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function NextPlanForm({ plan, reflection, onCreated }: { plan: Plan; reflection: Reflection; onCreated: (plan: Plan, row: Reflection) => void }) {
  const [input, setInput] = useState<NextPlanInput>({
    title: `${plan.title.slice(0, 150)} · 다음 계획`, startDate: nextDate(reflection.periodEnd, 1),
    endDate: nextDate(reflection.periodEnd, 7), priority: plan.priority,
    estimatedMinutes: plan.estimatedMinutes, successCriterion: plan.successCriterion,
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const inFlight = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setMessage("");
    try { const result = await createNextPlan(reflection.id, input); onCreated(result.plan, result.reflection); }
    catch (error) { setMessage(errorText(error)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <form className="inline-edit" onSubmit={submit}>
    <p>다음 계획에 전달할 개선점: <strong>{reflection.improvement}</strong></p>
    <label>다음 계획 이름<input maxLength={160} required value={input.title} onChange={(e) => setInput({ ...input, title: e.target.value })} /></label>
    <div className="grid two">
      <DateField label="다음 계획 시작일" required value={input.startDate} onChange={(startDate) => setInput({ ...input, startDate })} />
      <DateField label="다음 계획 종료일" required value={input.endDate} onChange={(endDate) => setInput({ ...input, endDate })} />
      <Select label="다음 계획 우선순위" value={input.priority} options={[{ value: "high", label: "높음" }, { value: "medium", label: "보통" }, { value: "low", label: "낮음" }]} onChange={(priority) => setInput({ ...input, priority: priority as Plan["priority"] })} />
      <label>다음 계획 예상 시간(분)<input type="number" min={0} max={1000000} step={1} required value={input.estimatedMinutes} onChange={(e) => setInput({ ...input, estimatedMinutes: Number(e.target.value) })} /></label>
    </div>
    <label>다음 계획 성공 기준<input required maxLength={500} value={input.successCriterion} onChange={(e) => setInput({ ...input, successCriterion: e.target.value })} /></label>
    <button className="primary" disabled={busy}>{busy ? "생성 중…" : "개선점을 담아 다음 계획 생성"}</button>
    {message && <p role="alert" className="message">{message}</p>}
  </form>;
}

function PlanReview({ plan, revision, onPlanCreated, onOpenPlan }: { plan: Plan; revision: number; onPlanCreated: (plan: Plan) => void; onOpenPlan: (id: string) => void }) {
  const [period, setPeriod] = useState<Period | null>(null);
  const [draftPeriod, setDraftPeriod] = useState<Period>({ periodStart: plan.startDate, periodEnd: plan.endDate });
  const [summary, setSummary] = useState<Summary | null>(null);
  const [reflections, setReflections] = useState<Reflection[]>([]);
  const [selected, setSelected] = useState<Metric | null>(null);
  const [improvement, setImprovement] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [allReflections, setAllReflections] = useState(false);
  const [nextId, setNextId] = useState<string | null>(null);
  const inFlight = useRef(false);
  // 계획을 바꾸면 접힌 상태로 돌아온다. 집계 새로고침에는 반응하지 않는다 —
  // 펼쳐 둔 목록이 새로고침마다 닫히면 그게 더 성가시다.
  useEffect(() => { setAllReflections(false); }, [plan.id]);
  useEffect(() => {
    let cancelled = false;
    setSummary(null); setMessage("");
    Promise.all([getSummary(plan.id, period), listReflections(plan.id)])
      .then(([data, rows]) => { if (!cancelled) { setSummary(data); setReflections(rows); } })
      .catch((error: unknown) => { if (!cancelled) setMessage(errorText(error)); });
    return () => { cancelled = true; };
  }, [plan.id, period, revision, reload]);
  function applyPeriod(event: FormEvent) {
    event.preventDefault(); setSelected(null); setPeriod({ ...draftPeriod });
  }
  async function submitReflection(event: FormEvent) {
    event.preventDefault();
    if (!summary || inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try {
      const row = await saveReflection(plan.id, { periodStart: summary.periodStart, periodEnd: summary.periodEnd, improvement });
      setReflections((current) => [...current, row]); setImprovement("");
      setMessage("회고를 저장했습니다. 개선점을 다음 계획으로 이어 보세요.");
    } catch (error) { setMessage(errorText(error)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  const source = selected && summary ? summary.sources[selected] : null;
  // 목록은 오래된 것이 위, 최근이 아래다(API가 created_at 오름차순). 그래서 «최근
  // N건»은 뒤에서 N개이고, 이전 것을 여는 단추는 목록 위에 놓인다.
  // 접힐 수 있는 건수는 펼침 여부와 무관하게 센다. 펼쳤을 때 0으로 만들면 단추가
  // 사라져 다시 접을 방법이 없어진다.
  const hiddenReflections = Math.max(0, reflections.length - RECENT_REFLECTIONS);
  const visibleReflections = allReflections || hiddenReflections === 0
    ? reflections
    : reflections.slice(-RECENT_REFLECTIONS);
  return <>
    <form className="period-form" onSubmit={applyPeriod}>
      <div className="grid two">
        <DateField label="집계 시작일" required value={draftPeriod.periodStart} onChange={(periodStart) => setDraftPeriod({ ...draftPeriod, periodStart })} />
        <DateField label="집계 종료일" required value={draftPeriod.periodEnd} onChange={(periodEnd) => setDraftPeriod({ ...draftPeriod, periodEnd })} />
      </div>
      <div className="actions"><button type="submit">마감일 기간 적용</button><button type="button" onClick={() => { setSelected(null); setPeriod(null); setReload((v) => v + 1); }}>계획 전체 보기</button><button type="button" onClick={() => setReload((v) => v + 1)}>집계 새로고침</button></div>
    </form>
    <p className="time-rule">기간은 할 일의 마감일 기준(양 끝 날짜 포함)입니다. 실제 시간은 대상 할 일에 연결된 모든 실행 기록을 합산합니다.</p>
    {message && <p role="status" className="message">{message}</p>}
    {!summary ? <p className="empty">{message ? "조건을 확인하고 다시 조회하세요." : "집계를 불러오는 중입니다."}</p> : <>
      <p>{summary.scope === "plan" ? "계획 전체" : `${summary.periodStart} — ${summary.periodEnd}`} · 지연 판단: 서울 {summary.today} 이전 마감인 미완료 할 일</p>
      <div className="metric-grid" aria-label="돌아보기 집계">
        {METRICS.map((metric) => <button key={metric.key} aria-pressed={selected === metric.key} onClick={() => setSelected(metric.key)} className={`metric-card${metricTone(metric.key, summary[metric.key])}`}>
          <span>{metric.label}</span><strong>{metricValue(metric.key, summary[metric.key], metric.unit)}</strong><small>{evidenceLabel(summary.sources[metric.key])}</small>
        </button>)}
      </div>
      {source && <section className="source-records" aria-label="집계 근거 기록">
        <h3>{METRICS.find((metric) => metric.key === selected)?.label} · 근거 기록</h3>
        <p>막힘은 이유가 있는 할 일을 한 번씩 셉니다. 차이는 실제 시간에서 예상 시간을 뺀 값입니다.</p>
        {source.taskIds.length === 0 && source.executionIds.length === 0 && <p>집계에 포함된 기록이 없습니다.</p>}
        {summary.records.tasks.filter((task) => source.taskIds.includes(task.id)).map((task) => <article key={task.id}>
          <strong>{task.content}</strong><p>{task.status === "completed" ? "완료" : "진행 중"} · 마감 {task.dueDate} · 예상 {task.estimatedMinutes}분</p><small>할 일 ID: {task.id}</small>
        </article>)}
        {summary.records.executions.filter((log) => source.executionIds.includes(log.id)).map((log) => <article key={log.id}>
          <strong>실제 {log.actualMinutes}분</strong><p>{seoul.format(new Date(log.startedAt))} → {seoul.format(new Date(log.endedAt))} (서울)</p>
          <p>막힌 이유: {log.blockerReason || "없음"}</p><small>실행 ID: {log.id}<br />할 일 ID: {log.taskId}</small>
        </article>)}
      </section>}
      <form className="reflection-form" onSubmit={submitReflection}>
        <h3>다음에 바꿀 한 가지</h3><p>회고 기간: {summary.periodStart} — {summary.periodEnd}</p>
        <label>개선할 점 한 줄<input required maxLength={500} value={improvement} onChange={(e) => setImprovement(e.target.value)} placeholder="작업을 30분 단위로 나눈다" /></label>
        <button className="primary" disabled={busy}>{busy ? "저장 중…" : "회고 저장"}</button>
      </form>
    </>}
    <section className="reflection-list" aria-label="저장된 회고">
      <h3>회고 기록</h3>{reflections.length === 0 && <p>아직 저장된 회고가 없습니다.</p>}
      {hiddenReflections > 0 && (
        <button type="button" className="done-toggle" aria-expanded={allReflections}
                onClick={() => setAllReflections(!allReflections)}>
          {allReflections ? "이전 회고 접기" : `이전 회고 ${hiddenReflections}건 더 보기`}
        </button>
      )}
      {visibleReflections.map((row) => <article key={row.id}>
        <p>{row.periodStart} — {row.periodEnd}</p><strong>{row.improvement}</strong>
        {row.nextPlanId ? <p><a href={`#plan-${row.nextPlanId}`} onClick={() => onOpenPlan(row.nextPlanId!)}>개선점을 담은 다음 계획 보기</a></p> : <div className="actions"><button onClick={() => setNextId(nextId === row.id ? null : row.id)}>{nextId === row.id ? "다음 계획 입력 닫기" : "이 회고로 다음 계획 만들기"}</button></div>}
        {nextId === row.id && !row.nextPlanId && <NextPlanForm plan={plan} reflection={row} onCreated={(next, updated) => {
          setReflections((current) => current.map((item) => item.id === updated.id ? updated : item));
          setNextId(null); onPlanCreated(next); setMessage("개선 문장을 그대로 담은 다음 계획을 만들었습니다.");
        }} />}
      </article>)}
    </section>
  </>;
}

export default function SeePanel({ plan, revision, onPlanCreated, onOpenPlan }: { plan?: Plan; revision: number; onPlanCreated: (plan: Plan) => void; onOpenPlan: (id: string) => void }) {
  return <section className="panel see-panel flow-section" id="see-step" tabIndex={-1} aria-label="See 돌아보기">
    <div className="section-heading"><div><span>03</span><h2>See · 돌아보고 이어가기</h2></div><p>숫자의 근거를 확인하고, 개선점을 다음 계획으로 옮깁니다.</p></div>
    {!plan ? <p>먼저 계획을 저장하세요.</p> : <>
      <p className="selected-plan-name">현재 계획: <strong>{plan.title}</strong></p>
      <PlanReview key={plan.id} plan={plan} revision={revision} onPlanCreated={onPlanCreated} onOpenPlan={onOpenPlan} />
      {/* Inside See because changing the rule is a looking-back action, and it
          belongs next to the aggregate it is argued from. It has to be
          deployed before the evening of day 2 or C09's ordering cannot be
          produced at all. */}
      <RuleChangePanel key={`rule-${plan.id}`} plan={plan} revision={revision} />
    </>}
  </section>;
}
