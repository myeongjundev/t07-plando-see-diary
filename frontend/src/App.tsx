import { FormEvent, useEffect, useState } from "react";
import {
  createPlan,
  listPlanRevisions,
  listPlans,
  Plan,
  PlanInput,
  PlanRevision,
  updatePlan,
} from "./api/plans";
import TaskPanel from "./features/tasks/TaskPanel";
import SeePanel from "./features/see/SeePanel";
import ExportPanel from "./features/export/ExportPanel";
import AccountPanel from "./features/account/AccountPanel";
import ThemeToggle from "./ThemeToggle";
import AccountBar from "./auth/AccountBar";
import PlanGauge from "./features/plans/PlanGauge";
import { getSummary, Summary } from "./api/reflections";
import useActiveStep from "./useActiveStep";
import DateField from "./components/DateField";
import Select from "./components/Select";

const STEP_IDS = ["plan-step", "do-step", "see-step"] as const;

// 계획 목록의 정렬 축. 「최신순」은 API가 준 생성 순서를 뒤집은 것이라 비교 함수가
// 없고, 나머지 둘만 아래에서 정한다.
type PlanSort = "recent" | "priority" | "due";

const PRIORITY_RANK: Record<Plan["priority"], number> = { high: 0, medium: 1, low: 2 };

// 동점 꼬리는 Do 구획의 고정 정렬 규칙(T06-C20)과 같은 모양으로 둔다 — 우선순위 →
// 마감일 → 생성 시각 → ID. 목록마다 다른 꼬리를 쓰면 한 화면에 정렬 규칙이 둘이 된다.
// endDate는 YYYY-MM-DD이고 createdAt은 서버가 언제나 UTC(+00:00)로 직렬화하므로,
// 문자열 비교가 곧 시간 순서다.
const PLAN_COMPARATORS: Record<Exclude<PlanSort, "recent">, (a: Plan, b: Plan) => number> = {
  priority: (a, b) =>
    PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
    a.endDate.localeCompare(b.endDate) ||
    a.createdAt.localeCompare(b.createdAt) ||
    a.id.localeCompare(b.id),
  due: (a, b) =>
    a.endDate.localeCompare(b.endDate) ||
    PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
    a.createdAt.localeCompare(b.createdAt) ||
    a.id.localeCompare(b.id),
};

const EMPTY_PLAN: PlanInput = {
  title: "T06 프로젝트 완주",
  startDate: "2026-09-01",
  endDate: "2026-09-07",
  priority: "high",
  successCriterion: "44개 검사 통과",
  estimatedMinutes: 600,
  carriedImprovement: null,
};

function App() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState<PlanInput>(EMPTY_PLAN);
  const [history, setHistory] = useState<Record<string, PlanRevision[]>>({});
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [editMinutes, setEditMinutes] = useState(0);
  const [message, setMessage] = useState("계획을 불러오는 중입니다.");
  const [busy, setBusy] = useState(false);
  const [dataRevision, setDataRevision] = useState(0);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [showNewPlan, setShowNewPlan] = useState(false);
  const [planQuery, setPlanQuery] = useState("");
  const [planSort, setPlanSort] = useState<PlanSort>("recent");
  const [loading, setLoading] = useState(true);
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId) ?? plans[0];
  // 어느 계획의 집계인지 함께 들고 있는다. 받아오는 동안 화면을 비우지 않으려면
  // 남아 있는 값이 지금 계획의 것인지 구별할 수 있어야 한다.
  const [planSummary, setPlanSummary] = useState<{ planId: string; data: Summary } | null>(null);
  // 계획이 쌓여도 Plan 구획이 Do·See를 아래로 밀지 않도록, 선택된 하나만 카드로 펼치고
  // 나머지는 한 줄로 접는다. 최근에 만든 것이 위로 오게 뒤집는다.
  const otherPlans = plans.filter((plan) => plan.id !== selectedPlan?.id).reverse();
  // 목록은 19rem에서 스크롤로 넘어간다. 그 전까지는 눈으로 찾는 게 빠르므로,
  // 스크롤이 시작될 즈음부터 검색을 내놓는다. 줄에 보이는 것이 이름이라
  // 이름만 찾는다 — 안 보이는 값까지 걸리면 왜 걸렸는지 알 수 없다.
  const planNeedle = planQuery.trim().toLowerCase();
  const visibleOtherPlans = planNeedle
    ? otherPlans.filter((plan) => plan.title.toLowerCase().includes(planNeedle))
    : otherPlans;
  // 「최신순」은 이미 뒤집힌 순서 그대로다. 나머지 둘만 복사해서 정렬한다 — 원본을
  // 제자리에서 정렬하면 다음 렌더의 「최신순」이 그 결과를 물려받는다.
  const sortedOtherPlans = planSort === "recent"
    ? visibleOtherPlans
    : [...visibleOtherPlans].sort(PLAN_COMPARATORS[planSort]);
  const activeStep = useActiveStep(STEP_IDS);

  // 선택한 계획의 예상 대비 실제. See는 기간 필터가 걸린 집계를 따로 들고 있어서
  // 공유하지 않는다. 카드는 언제나 계획 전체를 보여줘야 하므로 기간 없는 집계를
  // 따로 가져온다.
  //
  // 받아오기 전에 값을 비우면 카드가 무너졌다 다시 선다. 게다가 dataRevision은
  // TaskPanel이 목록을 새로 읽을 때마다 오르고, 계획을 바꾸면 TaskPanel이 다시
  // 마운트되며 곧바로 한 번 읽는다. 그래서 클릭 한 번에 이 효과가 두 번 돌았고,
  // 비우기가 두 번 일어나 카드 높이가 310 → 231 → 264 → 231 → 264로 튀었다.
  // 이제 비우지 않고, 도착한 값에 계획 ID를 붙여 둔 뒤 지금 계획의 것일 때만 그린다.
  useEffect(() => {
    if (!selectedPlan) {
      setPlanSummary(null);
      return;
    }
    const planId = selectedPlan.id;
    let cancelled = false;
    getSummary(planId, null)
      .then((data) => { if (!cancelled) setPlanSummary({ planId, data }); })
      .catch(() => { if (!cancelled) setPlanSummary(null); });
    return () => { cancelled = true; };
  }, [selectedPlan?.id, dataRevision]);

  function goToStep(id: string) {
    requestAnimationFrame(() => {
      const section = document.getElementById(id);
      section?.scrollIntoView({ block: "start" });
      section?.focus({ preventScroll: true });
    });
  }

  function acceptPlan(plan: Plan, nextStep: string) {
    setPlans((current) => current.some((item) => item.id === plan.id) ? current : [...current, plan]);
    setSelectedPlanId(plan.id);
    setShowNewPlan(false);
    goToStep(nextStep);
  }

  async function refresh() {
    try {
      setPlans(await listPlans());
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "계획을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const plan = await createPlan(form);
      setMessage("계획을 서버 데이터베이스에 저장했습니다.");
      acceptPlan(plan, "do-step");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "계획을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  function beginRevise(plan: Plan) {
    setEditingPlanId(plan.id);
    setEditMinutes(plan.estimatedMinutes);
  }

  async function revise(event: FormEvent, plan: Plan) {
    event.preventDefault();
    const minutes = editMinutes;
    if (!Number.isInteger(minutes) || minutes < 0) {
      setMessage("예상 시간은 0 이상의 정수 분이어야 합니다.");
      return;
    }
    try {
      await updatePlan(plan.id, { estimatedMinutes: minutes });
      const revisions = await listPlanRevisions(plan.id);
      setHistory((current) => ({ ...current, [plan.id]: revisions }));
      setEditingPlanId(null);
      setMessage("계획을 고쳤고 이전 값은 수정 이력에 남겼습니다.");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "계획을 고치지 못했습니다.");
    }
  }

  async function toggleHistory(planId: string) {
    if (history[planId]) {
      setHistory((current) => {
        const next = { ...current };
        delete next[planId];
        return next;
      });
      return;
    }
    try {
      const revisions = await listPlanRevisions(planId);
      setHistory((current) => ({ ...current, [planId]: revisions }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "수정 이력을 불러오지 못했습니다.");
    }
  }

  return (
    <main>
      <div className="page-top">
        <header className="hero">
          <p className="eyebrow">PLAN · DO · SEE</p>
          <h1>플랜두씨 다이어리</h1>
          <p>계획한 나와 실제의 차이를 기록하고, 다음 계획을 더 정확하게 만듭니다.</p>
        </header>
        <div className="page-top-actions">
          <AccountBar />
          <ThemeToggle />
        </div>
      </div>

      <div className="workflow-bar">
        {selectedPlan && (
          <Select
            className="plan-picker"
            label="현재 계획"
            searchable
            value={selectedPlan.id}
            options={plans.map((plan) => ({ value: plan.id, label: plan.title }))}
            onChange={setSelectedPlanId}
          />
        )}
        <nav className="step-nav" aria-label="Plan Do See 단계 이동">
          <a href="#plan-step" aria-current={activeStep === "plan-step" ? "step" : undefined} aria-label="01 Plan · 계획"><span>01 Plan</span><span>계획</span></a>
          <a href="#do-step" aria-current={activeStep === "do-step" ? "step" : undefined} aria-label="02 Do · 실행"><span>02 Do</span><span>실행</span></a>
          <a href="#see-step" aria-current={activeStep === "see-step" ? "step" : undefined} aria-label="03 See · 회고"><span>03 See</span><span>회고</span></a>
        </nav>
      </div>

      <section className="panel flow-section" id="plan-step" tabIndex={-1} aria-label="Plan 계획">
        <div className="section-heading">
          <div><span>01</span><h2>Plan · 계획</h2></div>
          <p>계획을 선택해 이어가거나 새 계획을 세워 보세요.</p>
        </div>
        {message && <p className="message" role="status">{message}</p>}
        <section className="plan-list" aria-label="저장된 계획">
          {selectedPlan && (
            <article className="plan-card selected" id={`plan-${selectedPlan.id}`} key={selectedPlan.id}>
              <div className="plan-top"><span className={`priority ${selectedPlan.priority}`}>{selectedPlan.priority}</span><span>{selectedPlan.startDate} — {selectedPlan.endDate}</span></div>
              <h3>{selectedPlan.title}</h3>
              <p>{selectedPlan.successCriterion}</p>
              <strong>계획 예상 {selectedPlan.estimatedMinutes}분</strong>
              <div className="plan-gauge-slot">
                {planSummary?.planId === selectedPlan.id && <PlanGauge summary={planSummary.data} />}
              </div>
              {selectedPlan.carriedImprovement && <p className="carried-improvement">이전 회고의 개선점: <strong>{selectedPlan.carriedImprovement}</strong></p>}
              <div className="actions"><button className="use-plan" onClick={() => goToStep("do-step")}>이 계획으로 실행</button><button onClick={() => beginRevise(selectedPlan)}>예상 시간 수정</button><button onClick={() => void toggleHistory(selectedPlan.id)}>수정 이력</button></div>
              {editingPlanId === selectedPlan.id && <form className="inline-edit" onSubmit={(event) => void revise(event, selectedPlan)}><label>새 예상 시간(분)<input type="number" min="0" value={editMinutes} onChange={(event) => setEditMinutes(Number(event.target.value))} autoFocus /></label><div className="actions"><button className="primary">수정 저장</button><button type="button" onClick={() => setEditingPlanId(null)}>취소</button></div></form>}
              {history[selectedPlan.id] && <div className="history"><h4>처음 계획 기록</h4>{history[selectedPlan.id].length === 0 ? <p>아직 수정 이력이 없습니다.</p> : history[selectedPlan.id].map((item) => <p key={item.revisionId}>#{item.revisionNumber} · {item.estimatedMinutes}분 · {item.successCriterion}</p>)}</div>}
            </article>
          )}
        </section>

        {otherPlans.length > 0 && (
          <section className="plan-others" aria-label="다른 계획">
            <div className="plan-others-head">
              <h3>{planNeedle
                ? `다른 계획 ${visibleOtherPlans.length}개 · 전체 ${otherPlans.length}개`
                : `다른 계획 ${otherPlans.length}개`}</h3>
              {otherPlans.length > 5 && (
                <div className="plan-filters">
                  <input
                    className="plan-search"
                    type="search"
                    value={planQuery}
                    onChange={(event) => setPlanQuery(event.target.value)}
                    placeholder="계획 이름 검색"
                    aria-label="계획 이름 검색"
                  />
                  <Select
                    className="plan-sort"
                    ariaLabel="계획 정렬 기준"
                    value={planSort}
                    options={[{ value: "recent", label: "최신순" }, { value: "priority", label: "중요도순" }, { value: "due", label: "마감 임박순" }]}
                    onChange={(next) => setPlanSort(next as PlanSort)}
                  />
                </div>
              )}
            </div>
            <div className="plan-other-list">
              {visibleOtherPlans.length === 0 && <p className="plan-none">이름이 맞는 계획이 없습니다.</p>}
              {sortedOtherPlans.map((plan) => (
                <button type="button" className="plan-row" id={`plan-${plan.id}`} key={plan.id} onClick={() => { setSelectedPlanId(plan.id); setPlanQuery(""); }}>
                  <span className={`priority ${plan.priority}`}>{plan.priority}</span>
                  <span className="plan-row-title">{plan.title}</span>
                  <span className="plan-row-dates">{plan.startDate} — {plan.endDate}</span>
                  <span className="plan-row-est">계획 예상 {plan.estimatedMinutes}분</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {!loading && plans.length === 0 && <p className="empty">첫 계획을 세워 보세요. 저장하면 할 일을 입력할 수 있습니다.</p>}
        {plans.length > 0 && <div className="actions new-plan-action">
          <button type="button" aria-expanded={showNewPlan} aria-controls="new-plan-form" disabled={busy} onClick={() => setShowNewPlan(!showNewPlan)}>{showNewPlan ? "새 계획 입력 닫기" : "+ 새 계획 만들기"}</button>
        </div>}
        {!loading && (plans.length === 0 || showNewPlan) && <section id="new-plan-form" className="new-plan-form" aria-label="새 계획 입력">
          <h3>새 계획 세우기</h3>
          <form onSubmit={submit}>
            <label>계획 이름<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label>
            <div className="grid two">
              <DateField label="시작일" value={form.startDate} onChange={(startDate) => setForm({ ...form, startDate })} required />
              <DateField label="종료일" value={form.endDate} onChange={(endDate) => setForm({ ...form, endDate })} required />
            </div>
            <div className="grid two">
              <Select label="우선순위" value={form.priority} options={[{ value: "high", label: "높음" }, { value: "medium", label: "보통" }, { value: "low", label: "낮음" }]} onChange={(priority) => setForm({ ...form, priority: priority as PlanInput["priority"] })} />
              <label>예상 시간(분)<input type="number" min="0" value={form.estimatedMinutes} onChange={(event) => setForm({ ...form, estimatedMinutes: Number(event.target.value) })} required /></label>
            </div>
            <label>성공 기준<textarea value={form.successCriterion} onChange={(event) => setForm({ ...form, successCriterion: event.target.value })} required /></label>
            <button className="primary" disabled={busy}>{busy ? "저장 중…" : "계획 저장"}</button>
          </form>
        </section>}
      </section>
      <TaskPanel key={selectedPlan?.id ?? "empty"} plan={selectedPlan} onDataChange={() => setDataRevision((value) => value + 1)} />
      <SeePanel plan={selectedPlan} revision={dataRevision} onPlanCreated={(plan) => acceptPlan(plan, "plan-step")} onOpenPlan={setSelectedPlanId} />
      <ExportPanel />
      <AccountPanel />
    </main>
  );
}

export default App;
