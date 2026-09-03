/** Recording the mid-study rule change, and reading it back. T07-C09 to C15.
 *
 * This screen has to exist before the five days start, not after. C09 puts the
 * change between the day-2 and day-3 records, so it gets written on the evening
 * of day 2 -- and if the feature is not deployed by then the ordering cannot be
 * produced at all and the five days start again.
 *
 * The two citations are picked from the plan's own execution records, filtered
 * to study days 1 and 2. The day number comes from the server, because the
 * boundary is a Seoul day and the browser may be anywhere; nothing here
 * recomputes it.
 */
import { FormEvent, useEffect, useState } from "react";
import type { Plan } from "../../api/plans";
import {
  ComparisonHalf,
  MetricDescriptor,
  RuleChange,
  Study,
  StudyExecution,
  getStudy,
  listRuleChanges,
  saveRuleChange,
} from "../../api/study";
import Select from "../../components/Select";

const seoul = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  dateStyle: "short",
  timeStyle: "short",
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";

/** A ratio, or the reason there isn't one.
 *
 * A day with nothing planned has no ratio (결측). Printing 0 would put an
 * invented number on the screen and, worse, one that reads as a bad day.
 */
function ratioText(value: number | null, unit: string) {
  return value === null ? "—" : `${value.toFixed(2)}${unit}`;
}

function executionLabel(row: StudyExecution) {
  return `${seoul.format(new Date(row.startedAt))} · ${row.actualMinutes}분 · ${row.taskContent}`;
}

function Half({ title, half, unit }: { title: string; half: ComparisonHalf; unit: string }) {
  return (
    <div className="rule-half">
      <h5>{title}</h5>
      <strong className="rule-ratio">{ratioText(half.ratio, unit)}</strong>
      <p>
        예상 {half.estimatedMinutes}분 · 실제 {half.actualMinutes}분 · {half.dayCount}일
        {half.daysWithoutRatio > 0 && ` · 계획 없는 날 ${half.daysWithoutRatio}일 제외`}
      </p>
    </div>
  );
}

function Comparison({ change }: { change: RuleChange }) {
  const { metric, before, after } = change.comparison;
  return (
    <div className="rule-comparison">
      {/* The metric is printed once, above both halves, because it is one
          metric. Labelling each side separately is how two labels end up
          disagreeing (T07-C13 to C15). */}
      <p className="rule-metric">
        {metric.name} · 단위 {metric.unit} · {metric.formula} · {metric.rounding}
      </p>
      <div className="rule-halves">
        <Half title="바꾸기 전 (1–2일차)" half={before} unit={metric.unit} />
        <Half title="바꾼 뒤 (3일차부터)" half={after} unit={metric.unit} />
      </div>
    </div>
  );
}

function DayTable({ days, metric }: { days: Study["days"]; metric: MetricDescriptor }) {
  return (
    <div className="rule-days">
      <table>
        <caption>
          {metric.name} — {metric.formula} ({metric.timezone} 기준)
        </caption>
        <thead>
          <tr>
            <th scope="col">일차</th>
            <th scope="col">날짜</th>
            <th scope="col">예상</th>
            <th scope="col">실제</th>
            <th scope="col">기록</th>
            <th scope="col">{metric.name}</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{day.dayNumber}일차</th>
              <td>{day.date}</td>
              <td>{day.estimatedMinutes}분</td>
              <td>{day.actualMinutes}분</td>
              <td>{day.executionCount}건</td>
              <td>{ratioText(day.ratio, metric.unit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RuleChangePanel({ plan, revision }: { plan?: Plan; revision: number }) {
  const [study, setStudy] = useState<Study | null>(null);
  const [changes, setChanges] = useState<RuleChange[]>([]);
  const [reason, setReason] = useState("");
  const [ruleBefore, setRuleBefore] = useState("");
  const [ruleAfter, setRuleAfter] = useState("");
  const [day1, setDay1] = useState("");
  const [day2, setDay2] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!plan) {
      setStudy(null);
      setChanges([]);
      return;
    }
    let cancelled = false;
    Promise.all([getStudy(plan.id), listRuleChanges(plan.id)])
      .then(([loaded, recorded]) => {
        if (cancelled) return;
        setStudy(loaded);
        setChanges(recorded);
      })
      .catch((error) => {
        if (!cancelled) setMessage(errorText(error));
      });
    return () => {
      cancelled = true;
    };
  }, [plan?.id, revision]);

  if (!plan) return null;

  const day1Options = (study?.executions ?? []).filter((row) => row.dayNumber === 1);
  const day2Options = (study?.executions ?? []).filter((row) => row.dayNumber === 2);
  // Both days need a record before a change can cite them, and saying which one
  // is missing is more use than a disabled button with no explanation.
  const missing = [
    day1Options.length === 0 ? "1일차" : null,
    day2Options.length === 0 ? "2일차" : null,
  ].filter(Boolean);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!plan) return;
    setBusy(true);
    setMessage("");
    try {
      const saved = await saveRuleChange(plan.id, {
        reason,
        ruleBefore,
        ruleAfter,
        day1ExecutionId: day1,
        day2ExecutionId: day2,
      });
      setChanges((current) => [...current, saved]);
      setReason("");
      setRuleBefore("");
      setRuleAfter("");
      setOpen(false);
      setMessage("규칙 변경을 기록했습니다. 이제 3일차 기록을 남길 수 있습니다.");
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rule-change" aria-label="계획 규칙 변경">
      <h3>계획 규칙 변경</h3>
      <p className="rule-lede">
        1·2일차 기록을 근거로 규칙을 바꾸고, 바꾼 시각과 이유를 함께 남깁니다. 3일차 기록보다
        먼저 기록해야 합니다.
      </p>
      {message && (
        <p className="message" role="status">
          {message}
        </p>
      )}

      {study && <DayTable days={study.days} metric={study.metric} />}

      {changes.map((change) => (
        <article className="rule-record" key={change.id}>
          <p className="rule-when">{seoul.format(new Date(change.changedAt))}에 바꿈</p>
          <p className="rule-arrow">
            <span>{change.ruleBefore}</span> → <strong>{change.ruleAfter}</strong>
          </p>
          <p className="rule-reason">이유: {change.reason}</p>
          <p className="rule-citations">
            근거 기록 · 1일차 <code>{change.citedExecutionIds.day1}</code> · 2일차{" "}
            <code>{change.citedExecutionIds.day2}</code>
          </p>
          <Comparison change={change} />
        </article>
      ))}

      {changes.length === 0 && (
        <>
          <div className="actions">
            <button
              type="button"
              aria-expanded={open}
              aria-controls="rule-change-form"
              disabled={missing.length > 0}
              onClick={() => setOpen(!open)}
            >
              {open ? "규칙 변경 입력 닫기" : "규칙 변경 기록하기"}
            </button>
          </div>
          {missing.length > 0 && (
            <p className="rule-blocked">
              {missing.join("와 ")} 기록이 아직 없습니다. 근거로 삼을 실행 기록을 먼저 남기세요.
            </p>
          )}
        </>
      )}

      {open && changes.length === 0 && (
        <form id="rule-change-form" className="rule-form" onSubmit={submit}>
          <Select
            label="1일차 근거 기록"
            value={day1}
            options={day1Options.map((row) => ({ value: row.id, label: executionLabel(row) }))}
            onChange={setDay1}
          />
          <Select
            label="2일차 근거 기록"
            value={day2}
            options={day2Options.map((row) => ({ value: row.id, label: executionLabel(row) }))}
            onChange={setDay2}
          />
          <label>
            바꾸기 전 규칙
            <input value={ruleBefore} onChange={(event) => setRuleBefore(event.target.value)} required />
          </label>
          <label>
            바꾼 뒤 규칙
            <input value={ruleAfter} onChange={(event) => setRuleAfter(event.target.value)} required />
          </label>
          <label>
            바꾸는 이유
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} required />
          </label>
          {/* No field for the time: the server stamps it. A time the browser
              could send is a time it could send anything for, and C09 is
              entirely about when this happened relative to the records. */}
          <button className="primary" disabled={busy || !day1 || !day2}>
            {busy ? "기록하는 중…" : "규칙 변경 기록"}
          </button>
        </form>
      )}
    </section>
  );
}
