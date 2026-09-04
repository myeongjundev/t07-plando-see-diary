# T07 project status (T06 history retained below)

Updated: 2026-09-04 KST

## 2026-09-04 Step 16 — idle and absolute expiry, now tested

- The logic was already in `app/services/sessions.py` and had been since step 4;
  what was missing was the acceptance test the matrix promises. Three added to
  `test_t07_refresh_rotation.py`:
  - `test_c111_idle_expiry` — a session past the idle window is refused by the
    guard even though its access token is still signed and still in date, cannot
    be revived by refresh, and its 401 is byte-identical to the one an unknown
    token gets.
  - `test_rotation_restarts_the_idle_clock` — `last_used_at` is written only by
    rotation, so a session in daily use never idles out.
  - `test_the_absolute_limit_refuses_a_session_used_a_moment_ago` — the
    companion to `test_c111_absolute_expiry_survives_rotation`, which showed the
    limit is not extended but never showed it actually bites.
- Time is made by moving the row into the past rather than by lowering
  `IDLE_TTL_SECONDS`. A one-second TTL proves the setting is read; C111 asks
  whether the limit is enforced in all three places that decide whether a
  session is still a session — the guard, the pre-check, and rotation.
- Only `test_c111_idle_expiry` carries the `test_c` prefix. The other two are
  not named in the matrix, and the guard reserves that prefix.
- Fixed criteria with a passing automated test: 34/47.

Commands run:

- `backend/.venv/Scripts/python.exe -m pytest backend/tests` — **263 passed, 3
  skipped**.

Remaining: steps 17, 18, 20, 21, and the two human blockers unchanged (T06
submission, then the deploy that starts the five-day clock).

Handoff target: step 17 — the password-change endpoint. The service layer and
`test_c114_password_change_revokes_all_sessions` already exist and pass; what is
missing is the route, its re-authentication, and the lock ordering that keeps it
from deadlocking with rotation.

## 2026-09-04 Step 15 — database-backed login throttle

- `app/services/throttle.py` implements design section 6 against the existing
  `login_attempts` table: a 15-minute window, a lock at 5 failures for one
  (email, ip_hash) pair or 20 for the address alone, 60 seconds doubling to a
  15-minute ceiling, and release of that pair's failures on a successful login.
- Wired into `app/api/auth.py::login` **before** the account lookup and Argon2
  verification, so an address that exists and one that does not reach the same
  429 by the same route. The refusal carries `Retry-After` and a message that
  does not say an account exists; that unfriendliness is deliberate and belongs
  in the guide's section ⑥.
- Requests refused while locked are written as `blocked` and never counted, so
  an attacker cannot hold a victim at the ceiling by continuing to knock.
  Failures against unregistered addresses and unparseable bodies are counted,
  so "this address never locks" is not an enumeration oracle.
- A successful login clears only that (email, ip_hash) pair. The address-wide
  count survives on purpose: otherwise one account of the attacker's own resets
  the global limit at will.
- Rows past 24 hours are deleted from the login path with 1/100 probability.
  Render Free has no cron.
- Noted while testing: `MAX_LOCK` equals `WINDOW`, so serving out the 60 → 120
  → 240 → 480 second ladder ages the earliest failures out of the window and
  the ceiling is reached by arithmetic rather than by a real request sequence.
  The ladder is therefore tested on `_lock_for` directly; everything else is
  tested through the endpoint.
- New: `backend/tests/acceptance/test_t07_login_throttle.py`, 14 tests. None use
  the `test_c` prefix — no fixed criterion names throttling, and the matrix
  guard reserves that prefix.
- No schema change, no migration, no new table in the export contract. The
  frontend needed no change: `CredentialsPage` already renders the server's
  message, so the 429 text appears as written.

Commands run:

- `backend/.venv/Scripts/python.exe -m pytest backend/tests` — **260 passed, 3
  skipped** (was 246 passed, 3 skipped).
- `npm --prefix frontend test` — 19 passed.
- `npm --prefix frontend run build` — built.
- `backend/.venv/Scripts/python.exe backend/scripts/audit_secrets.py` — 0
  findings over the worktree, frontend build, and 1091 Git objects.

Remaining: steps 16 (idle/absolute expiry — the logic is already in
`sessions.py`; what is missing is `test_c111_idle_expiry`), 17, 18, 20, 21, and
the two human blockers unchanged from the 2026-09-04 handoff (T06 submission,
then the deploy that starts the five-day clock).

Handoff target: step 16, then 17.

## 2026-09-04 T06 production ID inventory fixed for claim

- Read the still-public T06 `/api/export` in memory and retained IDs only; no
  database URL, full export file, password, or diary body was stored.
- The deployed snapshot has 7 plans and 8 tasks. `render.yaml` now fixes all 7
  plan IDs into disjoint claim/exclude lists: 3 retained plans and 4 empty test
  plans. The lists exactly cover the deployed plan set.
- The retained main plan has 8 task rows. Six active rows stay; two T06
  verification artifacts that were already soft-deleted are identified by
  fixed task ID for hard deletion during claim.
- `claim_t06_data.py` refuses task cleanup unless the row belongs to an
  unowned plan selected for claim and is already soft-deleted. This prevents
  an ID typo from deleting active diary work. Its 11 focused tests pass.
- This turn only prepared the lists and safeguards. No live database row was
  changed; mutation still requires `BOOT_TASK=claim_t06_data` with `--apply`.

## 2026-09-03 T07 authentication design review resolved

- Kept the user-selected Access JWT + rotating opaque Refresh architecture, but
  made row locking and password-change/logout race ordering part of the design.
- Removed DB-bound CSRF. Protected writes use authentication then `__Host-`
  double-submit; signup/login use JSON plus Origin checks; refresh authenticates
  its opaque token before CSRF validation.
- Exempted `/api/live` from authentication, expanded ownership from single-item
  guards to collections, aggregates, creation and export, and specified the
  reflection FK changes required for account deletion.
- Split T06 data claim and `plans.user_id NOT NULL` into separate deploys.
- Moved the plan-rule-change API/UI into the pre-study stage and fixed one
  observation plan ID as the scope of the exact five-day record.
- Expanded the Argon2 benchmark to concurrent latency and peak RSS, made login
  lock state transitions explicit, and bounded secret/log absence claims to
  reproducible scan surfaces.
- No authentication implementation was started in this review. The concurrently
  committed T07 acceptance-matrix work was not modified by the design edits.

## 2026-09-03 handoff written for the academy PC

- `docs/process/ACADEMY-HANDOFF-2026-09-03.md` covers what to do next on another
  machine. The 2026-09-02 academy handoff is kept and marked as the older of the two;
  `docs/README.md` now lists both with the newer one first.
- Written for a machine that has none of this one's state. `backend/instance/` is
  gitignored, so a fresh clone has no plans at all, and `frontend/.env.local` — the
  dev proxy target — does not travel either. Both are called out, and the two local
  database backups are named as unavailable there rather than left to be looked for.
- `tools/seed_screenshot_fixture.py` promoted out of scratch. It seeds the synthetic
  data the README screenshots use, with due dates relative to today so the aggregate
  lands on 할 일 5 · 완료 3 · 지연 1 · 막힘 2 · 예상 300분 · 실제 260분 · 차이 -40분 —
  the figures the alt text already claims. Screenshots are now reproducible anywhere
  rather than depending on one machine's database.
- Also corrected while writing it: the pre-existing academy handoff pointed at
  `design/css-token-layer` as the branch to continue from, which no longer exists.
- Remaining work is two items, both the user's: rewrite the three judgment lines in
  their own voice (D-019), then paste the two URLs and two blocks into the form.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-03 pushed, tag moved, deploy confirmed

- The 2026-09-02 UI pass is on `origin/main` as eight change commits plus one for
  the documents. Every one of the eight was checked out and built on its own before
  pushing, and the reconstructed tree was compared against the verified working copy
  with `diff -r`: 21 source files and both documents identical byte for byte.
- `main` = `origin/main` = `t06-submission` = `65ac0530ab14458e4d5f636e89f000c83d29b4f8`.
  The tag was force-updated (`7e72f6d` → `cc76ae4`), which rewrites a published ref;
  it was moved deliberately because `docs/SUBMISSION.md` defines the tag as pointing
  at the commit Render is serving.
- Render had already rebuilt when this was checked. Confirmed on the public app, not
  just locally: zero native `select`, zero native date or datetime inputs, three
  `.select-field` and two `.date-field` present, the gauge drawing segments with no
  `.plan-gauge-tick` left, and the public-data warning verbatim on the first screen.
  Served assets `index-MZVl8FZ4.js` and `index-CGU0rIJc.css` match the local build.
- `docs/SUBMISSION.md` named the previous build's asset filenames as evidence for the
  claim that the tag tracks the deployed code, so it contradicted itself after the
  deploy. Corrected, along with the feature summary. Editing a document does not
  change the bundle, so those asset hashes stay valid.
- Still outstanding for an actual submission: `python tools/generate_verification.py`
  has not been re-run, so the verification record and the submission PDF's asset
  names remain at the `ae9510c` state.

## 2026-09-02 the dropdowns are ours too

- Same situation as the calendar: a `select`'s open list is browser chrome, so the
  closed box followed our tokens while the open list stayed an OS widget. All seven
  are now `Select`, and `document.querySelectorAll('select').length` is 0 (D-054).
- The list is capped at 19rem, the same height as the plan list, the task lists and
  the plan picker's own siblings. With ten plans it holds 304px of a 388px list and
  scrolls inside.
- The plan picker gets a search field, which is the thing native could not do — its
  type-ahead matches a first letter only. Typing 마이그레이션 narrowed ten plans to one;
  a query matching nothing gives 이름이 맞는 항목이 없습니다.
- Verified: opens with ArrowDown/Enter/Space from the button, ArrowUp/Down move,
  Home/End jump, Enter picks, Escape closes and returns focus to the button, outside
  click closes, the selected option is scrolled into view, and `aria-activedescendant`
  tracks the focused row. On a list without a search field, typing 완 moved to 완료 —
  the native type-ahead behaviour, kept.
- End to end: picking 완료 on the 상태 filter left one task row, and 전체 restored the
  list, so T06-C19 still holds through the new control.
- Found and fixed in this change's own code, then found again in `DateField`: both
  computed the next focused item from the `active` value of the current render, so
  three fast arrow presses batched into one move. Both now use the updater form —
  three ArrowDowns move three rows, three ArrowRights move three days.
- Heights match their neighbours: 48px next to the task-tool inputs, 37px next to the
  plan search. The workflow bar grew 106px → 113px because a button follows
  `line-height` where a `select` does not; trimming the picker's padding put it at
  38px against the step nav's 37px and the bar back to 109px. That bar is sticky, so
  the height is not free.
- Contrast, both themes: option text 16.56:1 / 14.57:1, the selected option on
  `--accent-soft` 4.77:1 / 5.61:1, button text 16.56:1 / 14.57:1. No horizontal
  overflow at 1280px or 375px, and the popup stays inside the viewport at both.
- The mobile cost is real and was accepted knowingly: a native `select` opens the OS
  sheet with large touch targets. Option rows take 12px padding under 720px, which
  brings them from 39px to about 45px, but that is mitigation, not parity.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-02 the gauge baseline is a seam, not a tick

- The user asked for something better than the black tick. Two faults, not one: the
  tick was `--ink` and 18px tall over an 8px track, the strongest contrast on the
  card; and the whole bar was `--crit` when over, so 계획대로 쓴 90분 was painted the
  same red as the 75분 that overran.
- The bar is now three segments on one scale — 계획 (`--ink-3`), 초과 (`--crit`) past
  the baseline, and 아낀 자리 as a `--good` hatch between the fill and the baseline.
  The baseline is where two of them meet, so the tick element is gone rather than
  restyled (D-053). A `--line-2` hairline underneath shows through only where no
  segment covers it.
- Observed across four plans, all percentages of the track:

  | plan | 예상 / 실제 | 계획 | 초과 | 아낀 자리 | hairline |
  |---|---|---|---|---|---|
  | 합성 카드 3 | 90 / 165 | 0–60% | 60–100%, clipped | — | covered |
  | 합성 카드 4 | 300 / 260 | 0–52% | — | 52–60% hatched | at the hatch's edge |
  | 합성 카드 4 · 다음 | 270 / 0 | — | — | — | visible alone at 59.9% |
  | 합성 계획 A | no data | — | — | — | empty state |

  The third row is the case the hairline was kept for: nothing is drawn yet, and
  without it the plan's position would vanish from the track.
- No hatch when 실제 is 0. It is not a saving — the plan has not started, and green
  hatching would have the screen congratulate it.
- Colours confirmed in both themes: planned `#667382` / `#9aa6b5`, over `#d6473c` /
  `#ef8279`, seam a 2px border in the card colour, hairline `--line-2`. Every segment
  is 8px, the same height as the track, so nothing protrudes any more. The heading's
  left swatch changed from the black tick shape to an `--ink-3` square to match the
  segment it now names.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-02 old reflections fold away

- Chose folding over a height cap, as the user picked from the three options
  recorded in the entry below (D-052). The three most recent stay on screen and the
  rest sit behind 「이전 회고 N건 더 보기」, the same `.done-toggle` the completed-task
  group uses — one gesture, one control.
- Measured with five reflections on 합성 카드 3, two of them added locally to get
  past three:

  | | shown | section | 내보내기 starts at | document |
  |---|---|---|---|---|
  | collapsed | 3 | 505px | 3,389px | 3,676px |
  | expanded | 5 | 791px | 3,676px | 3,963px |
  | collapsed again | 3 | 505px | 3,389px | 3,676px |

  `aria-expanded` flips with it.
- The reason a cap was refused holds up on screen: opening 이 회고로 다음 계획 만들기
  grows the section to 1,014px with `overflow-y: visible` and `max-height: none`, so
  the form is never trapped in a scroll box.
- That also closed the last unverified `DateField` usage — 다음 계획 시작일 and
  종료일 render as our component inside that form.
- Found and fixed while testing, in this change's own code: `hiddenReflections` was
  computed as `allReflections ? 0 : …`, so the button vanished once expanded and the
  list could not be folded again. The count is now independent of the expanded flag.
- Collapsing resets when the plan changes but not on 집계 새로고침 — a list that
  re-folded on every refresh would be worse than the length.
- 53 backend tests pass and the frontend production build passes.
- Local-only synthetic rows added while verifying: two reflections (합성 회고 4·5) on
  합성 카드 3. Gitignored database.

## 2026-09-02 the plan gauge gets a fixed baseline

- The user said the gauge read unnaturally. It did, and the cause was the scale:
  `span = Math.max(estimated, actual)` gave the larger value 100% of the track.
  Two consequences, both bad, both invisible until you compare two plans:
  the tick sat at 54.5% when over and at 100% when under, so the reference line
  moved; and any overrun filled the bar completely, so magnitude lived only in the
  tick position, whose relation to the overrun is `예상/실제` — an inverse.
- The tick now stands at a fixed 60% and the fill is `실제 / 예상 × 60%`, so the
  fill length is «how many times the plan», read linearly (D-051). Beyond 1.67× the
  bar clamps at 100% and takes a torn right edge, because a silently clipped bar
  reads as one that happens to be full.
- No tick when the estimate is zero. Drawing one would have the screen assert a
  reference that is not there.
- Observed across four plans, tick at 59.9% in every one:

  | plan | 예상 / 실제 | fill | note |
  |---|---|---|---|
  | 합성 카드 3 | 90 / 165 | 100%, clipped | +75분 더 걸렸습니다 |
  | 합성 카드 4 | 300 / 260 | 52% | -40분 덜 걸렸습니다 |
  | 합성 카드 4 · 다음 | 270 / 0 | 0.2% (2px floor) | 아직 실행 기록이 없습니다 |
  | 합성 계획 A | no data | — | empty state |

  Under the old scale the 300 / 260 case filled 86.7% with the tick at 100%; the
  shortfall was almost invisible. It now reads as a bar stopping short of the line.
- T06-C32 re-checked: the variance sentence still prints `-40분` with the ASCII hyphen.
- 53 backend tests pass and the frontend production build passes.
- Note on the numbers on screen: 실제 165분 on 합성 카드 3 includes the 90-minute
  execution log saved while verifying the time picker. Local database only.

## 2026-09-02 answered: the reflection list grows without limit too

- Asked what happens to 회고 기록 as entries accumulate. Same shape as the task list
  before D-048: `.reflection-list` has `max-height: none` and `overflow-y: visible`.
- Measured with three reflections: each card 135px on a 143px pitch, the section
  451px, and 내 자료 내보내기 begins at 3,336px. Ten reflections would add about
  1,000px, and the reflections sit between See and the export panel, so everything
  below moves down by that much.
- Not changed yet — it needs a decision the task list did not, because each card can
  expand into the 다음 계획 form. Capping the section puts that form inside a scroll
  box, which is worse than the length it fixes. Options worth weighing: cap the list
  but let the expanded card escape the cap, show the most recent few with a 「더
  보기」, or leave it and accept the growth since reflections accrue far more slowly
  than tasks.

## 2026-09-02 execution log times use the same picker

- The last two native controls, the `datetime-local` inputs on the execution-log
  form, now use `DateField` with a new `withTime` flag (D-050). No native date or
  datetime input is left anywhere in the app.
- One component, not two: the same popover gains a 시/분/초 row and its footer button
  becomes 「지금」 (Seoul now) instead of 「오늘」. Picking a day keeps the time and
  leaves the popover open, since the time is entered next.
- The stored value keeps the native shape `YYYY-MM-DDTHH:MM:SS`, so
  `ExecutionPanel`'s `${value}+09:00` and the D-012 UTC path are untouched. The text
  box shows a space instead of the `T` because a person reads and edits it.
- Verified end to end, which is the check that matters here: typed 서울
  `2026-09-02 09:00:00` → `10:30:00` with 90분, saved, and the list rendered back
  `2026. 09. 02. 09:00:00 → 2026. 09. 02. 10:30:00 (서울)`. The API stores
  `2026-09-02T00:00:00+00:00 → 2026-09-02T01:30:00+00:00`, which is exactly those
  Seoul times in UTC. The record count went 1 → 2 and the form cleared.
- Also observed: the popover carries the time row and 「지금/닫기」; picking a day
  leaves it open and sets `2026-09-02 00:00:00`; 시=10, 분=35, 초=7 gives
  `2026-09-02 10:35:07`; 시=99 clamps to 23; a value typed without seconds is
  accepted and completed; empty plus `required` reports invalid.
- Layout and contrast: popup 262×388 at 1280px and 318px wide at 375px, inside the
  viewport at both, no horizontal overflow. Time row label and separators 4.84:1
  light / 6.99:1 dark, the number boxes 16.6:1 / 14.6:1.
- Removed the now-dead `input[type="datetime-local"]` rule from the 480px block.
- 53 backend tests pass and the frontend production build passes.
- The verification left one extra synthetic execution log on the local SQLite
  database. It is local only and gitignored.

## 2026-09-02 the date picker is ours now

- The user asked to redesign the See period calendar. Reported first that the
  calendar in question is not ours: it is Chrome's popup for `input[type="date"]`
  and no CSS selector reaches it. Offered three routes; the user chose building our
  own, applied to all seven date inputs rather than to See alone (D-049).
- New `frontend/src/components/DateField.tsx` and `frontend/src/lib/date.ts`. All
  seven `input[type="date"]` are gone — plan start/end, task due date, See period
  start/end, next-plan start/end. The two `datetime-local` inputs on execution logs
  are untouched and still native; replacing those means also building a time picker.
- Typing is kept. The field is a text input with `pattern`, and the value is only
  pushed upward once the text is a real date.
- `seoulToday()` moved out of `TaskPanel` into `lib/date.ts`, so the D-008 timezone
  rule now has one definition that both the due-date marks and the calendar's
  «today» read from.
- Verified in the browser, no native picker left on screen:

  | check | result |
  |---|---|
  | popup structure | `role="dialog"`, 6 rows × 7 cells, 일–토, one tabbable cell |
  | keyboard | →+1, ↓+7, PageDown +1 month, Home → week start, Escape closes and returns focus to the toggle |
  | select | clicking 2026-09-04 sets the field and closes the popup |
  | typing | `2026-09-06` typed straight in is accepted |
  | outside click | closes |
  | end to end | 09-05–09-07 applied gives all-zero aggregates, 계획 전체 보기 restores 할 일 1 / 예상 90분 / 실제 75분 / 차이 -15분 |
  | layout | popup 262px at 1280px and 318px at 375px, inside the viewport in both, `scrollWidth` 1265 / 375 |

- Two things found and fixed while checking, not cosmetic:
  - `pattern="\d{4}-\d{2}-\d{2}"` accepted `2026-02-31`; `checkValidity()` returned
    true for a date that does not exist. `setCustomValidity` now rejects it, and a
    half-typed `2026-09-3` with it.
  - Outside-month days were `--ink-3` at `opacity: .55`, which measured 2.14:1 in
    light and 3.02:1 in dark. They are clickable buttons, so 4.5:1 applies. Dropping
    the opacity puts them at 4.84:1 and 6.99:1.
- Rest of the popup measured: day 16.6:1 / 14.6:1, selected day on accent 5.41:1 /
  6.88:1, weekday header 4.84:1 / 6.99:1, footer 7.11:1 / 7.61:1 (light / dark).
- T06-C32 re-checked: the variance still prints `-15분` with the ASCII hyphen.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-02 the task lists scroll instead of growing

- The user asked whether the task list grows without limit. It did: `.task-list`
  had `max-height: none`, and its `overflow: hidden` was there to clip the rounded
  corners, not to scroll. At 56px a row, nine tasks added about 506px and twenty
  about 1,122px, all of it pushing See down.
- Recommended capping only the completed group and leaving the active list free,
  on the grounds that the active list is the working surface rather than an archive.
  The user chose the plan list's treatment for both, for the rhythm of two boxes the
  same height on one screen. Done that way (D-048).
- `.task-list` now takes `max-height: 19rem` and `overflow-y: auto`, the same pair
  `.plan-other-list` has used since D-032. The old `overflow: hidden` is gone —
  `overflow-y: auto` clips the radius by itself.
- Observed at 1280px on a plan with nine tasks: the active list holds at 304px with
  341px of content and a scrollbar, the completed group (three rows, 170px) stays
  under the cap with none, rows keep their 56–57px height inside the grid, and
  `scrollWidth` is 1265 at `innerWidth` 1280. 19rem shows five rows and half of the
  sixth, so the cut row itself says there is more below.
- Cost accepted rather than hidden: at 375px task rows go to 110px in the two-line
  layout, so the same 304px box shows about 2.7 task rows where the plan list shows
  4.2. Raising the cap on narrow screens would fix the count and break the equal
  heights that motivated the change, so it was left alone and recorded here.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-02 completed tasks are filled green, not struck through

- The user asked for the strikethrough to go and the row to be coloured instead.
  Agreed on the reason as well as the look: the struck-out title is the one thing a
  reader still needs, since reopening a task (T06-C12) and matching execution logs
  to it both start from its content (D-047).
- `.task-row.completed` now takes `--good-soft`; the title drops the
  `text-decoration` and moves from `--ink-3` to `--ink-2`. A new `--good-soft-2` in
  both palettes carries the hover, because the row already sits on `--good-soft` and
  the shared `--surface-2` hover would have removed the green.
- Measured on a completed row, both themes, transitions disabled:

  | | light | dark |
  |---|---|---|
  | row background | `#e7f7f2` (active rows `#ffffff`) | `#102b25` (active `#171b21`) |
  | title on row | 6.43:1 | 6.63:1 |
  | priority badge, due mark | 5.32:1 | 5.95:1 |

  `text-decoration-line` reads `none` in both.
- Completion is still not signalled by colour alone: the filled check circle is
  unchanged, so the row reads as done without relying on the tint.
- 53 backend tests pass and the frontend production build passes.
- Tooling note for whoever picks this up: while the Browser pane is hidden,
  `document.hidden` is true, the page is throttled, and CSS transitions freeze
  mid-flight — `getComputedStyle` then returns the stale animated colour and
  screenshots return an old frame. Inject
  `*{transition:none !important}` before reading colours, or open the pane.

## 2026-09-02 the plan list's priority filter is gone

- Removed at the user's request, right after the sort control landed. 중요도순
  answers the same question and answers it better: the filter hid every other plan
  to show one priority, while the sort keeps all nine rows on screen in priority
  order, so where the «보통» plans sit is still visible (D-046, superseding D-044).
- The section below this one describes the filter as present. That was true when it
  was written; this entry is what stands.
- The empty-list message goes back to `이름이 맞는 계획이 없습니다.` and the heading
  counts matches against the total only while a search is active.
- 375px got better rather than worse: the three controls used to wrap onto two lines
  and the heading ran 100px tall; search and sort now fit one line at 61px, both
  37px. At 1280px they run 296 + 112px inside the 974px head, `scrollWidth` 1265.
- Observed: 마감 임박순 with the search on `계획` returned seven rows in due order
  (09-04, 09-05, 09-06, 09-08, 09-09, 09-10, 09-14) and the heading read
  `다른 계획 7개 · 전체 9개`; a query matching nothing gave `다른 계획 0개 · 전체 9개`
  and the name message. No `.plan-priority` node is left in the DOM or the stylesheet.
- 53 backend tests pass and the frontend production build passes.

## 2026-09-02 the plan list can be ordered, not just filtered

- The user asked what a sort control on the plan list should offer beyond 최신순
  and 중요도순. Recommended 마감 임박순 as the third and only addition: the row
  already printed `2026-09-01 — 2026-09-07` and nothing could act on it, and
  priority is the intent recorded when the plan was written while the deadline is
  the pressure now. 예상 시간순 and 이름순 were declined — the first drives no
  decision, the second is what the search field already does. The user agreed.
- `최신순` is the default and is the previous order unchanged (the reversed API
  array). The other two sort a copy; sorting in place would have leaked the new
  order into the next render of 최신순. Both end with Do's tie-break chain —
  우선순위 → 마감일 → 생성 시각 → ID (D-045).
- Observed with ten plans in the local database, priority filter cleared:
  중요도순 gave high(09-04, 09-05, 09-07, 09-07), high(09-14), medium(09-06, 09-09),
  low(09-08, 09-10) — the two 09-07 highs split by creation time, as the chain says.
  마감 임박순 gave 09-04, 09-05, 09-06, 09-07, 09-07, 09-08, 09-09, 09-10, 09-14.
  With the priority filter on `high` the sort applied to the five survivors only and
  the heading still read `다른 계획 5개 · 전체 9개`.
- Found while checking by eye: the third control was 6px shorter than the other two
  at 375px. Flex `stretch` had equalised the first two because they shared a line;
  the sort control wraps alone under 640px and had nothing to match. `line-height`
  does not fix it — Chrome ignores it on `select` — so the three now carry a
  `min-height` floor. All three measure 37px at both widths.
- Layout: the controls run 291 + 125 + 112px inside a 974px head at 1280px, one
  line, `scrollWidth` 1265. At 375px search and priority hold the first line and
  sort takes the second, no horizontal overflow.
- Locked elements re-checked: the public-data warning verbatim on the first screen,
  the Do sort-rule string `우선순위(높음→보통→낮음) → 마감일 → 생성 시각 → ID`
  untouched, `high` rendering as a literal with `text-transform: none`.
- 53 backend tests pass and the frontend production build passes.
- The local `backend/instance/t06.db` had dropped to four plans, below the
  «more than five other plans» gate, which is why the filter looked missing. Six
  synthetic plans (합성 계획 A–F) were added to bring it to ten. It is gitignored,
  so another machine still has to seed its own.

## 2026-09-02 task rows use the width they already had

- Measured the Do section next: each task row ran 249px and six tasks filled
  1,979px, while roughly 70% of every row's width sat empty. The action buttons and
  the execution-log toggle were stacked under the content because the row was a
  two-column grid, so vertical space paid for what horizontal space was wasting.
- Rows are now three columns — status, body, actions — with 내용 수정, 삭제 and the
  log toggle sharing the previously empty right column. Nothing was hidden behind a
  hover: those two buttons back T06-C10 and C13 and a grader has to be able to find
  them.
- The log toggle moved out of `ExecutionPanel` into that group, and the panel is
  mounted only while open, so a closed row no longer pays for a divider and a full
  button row. One panel is open at a time now.
- Row height 249px → 114px (92px without tags), Do section 1,979px → 1,171px, whole
  document 4,565px → 3,758px, with the same six tasks.
- Found and fixed while checking by eye: button styling was scoped to
  `.actions button`, so the buttons in the new container rendered as unstyled native
  controls. The rule and its hover and danger variants now cover both containers.
- Verified: opening a row mounts the panel with its four fields, save button and
  completion history, the toggle label flips, and closing unmounts it. Acceptance
  elements re-checked at 1280px and 375px — warning on the first screen, sort rule,
  priority literals with `text-transform: none`, twelve plan anchors, no overflow.
  53 tests and the frontend build pass.

## 2026-09-02 plan list and task form stop crowding the page

- The user asked what happens as plans accumulate. Measured: every plan was drawn
  as a full card in a two-column grid with no cap, so each pair added about 330px.
  With 12 plans the list ran roughly 1,980px and Do began past 2,600px — plan
  history nobody revisits was pushing Do and See, the two screens used daily, off
  the page. The list was also ordered oldest-first, so the newest plan sat last.
- Now the selected plan keeps its full card with the gauge, and the rest collapse
  into one-line rows (priority, title, dates, estimate) in a list capped at 19rem
  with internal scrolling, newest first. Measured again with 12 plans: the list is
  304px and Do begins at 1,256px, and the height no longer grows with plan count.
- The one-line rows keep `id="plan-<id>"`, because SeePanel's "다음 계획 보기" link
  jumps to that anchor; dropping it for unselected plans would have broken the jump
  for exactly the plan that link targets. Verified 12 anchors present.
- The task form was always fully expanded, so every visit that only wanted to read
  the list scrolled past four fields. It is now a title field with «추가» and a
  «자세히» toggle for due date, priority, estimate and tags; a hint states the
  defaults a bare add will use. Form height 143px collapsed against 346px expanded.
- Tags were free text only, which lets one tag split across spellings. The detail
  panel now lists the tags already used in the plan as chips; clicking one appends
  it and clicking it again does not duplicate it. Verified through the UI.
- Quick add verified end to end through the UI: typing a title and submitting
  created the task, it appeared in the list, and the field cleared.
- Acceptance-critical elements re-checked at 1280px and 375px: public warning fully
  on the first screen, sort rule present, priority literals `high`/`medium`/`low`
  with `text-transform: none`, no document or element overflow. 53 tests and the
  frontend build pass.

## 2026-09-02 documentation and tooling filed by lifecycle

- `docs/` had grown to 19 flat files with nothing distinguishing a standing rule from
  a one-day note, including four filenames containing HANDOFF and three documents
  that declare themselves superseded in their own headers. A reader could not tell
  which was authoritative.
- Split by lifecycle. `docs/` now holds the ten standing references; `docs/process/`
  holds the six handoffs, reviews and dated checklists; `docs/archive/` holds the
  three superseded ones. `docs/README.md` is a new index that says which layer is
  binding and, for each archived document, why it was set aside.
- `PROJECT-SKELETON.md` was archived despite its ACTIVE header: it is a
  pre-implementation plan whose tree names nine directories that do not exist
  (`tests/integration`, `frontend/src/components`, `features/do`, `pages`, and
  others), so it cannot serve as a structure guide. Its substantive parts —
  dependency direction and work slices — are carried by `FLASK-ARCHITECTURE.md`.
- `DEPLOYMENT.md` stayed: it documents the local Docker Compose stack, which
  `RENDER-NEON.md` does not cover. Its status line still described the hosted
  deployment as pending and now states its actual scope.
- `capture_screenshots.mjs` moved from `backend/scripts/` to a new top-level
  `tools/`. It is a Node script that produces README images and has nothing to do
  with the Python backend.
- All 12 cross-references to the moved paths were rewritten and every relative link
  in `README.md` and `docs/README.md` was resolved against the working tree. 53
  tests, the frontend build, the secret scan and `git diff --check` pass; the build
  output is unchanged.
- Not done yet, and deliberately left until after submission: `STATUS.md` is 481
  lines and is really a changelog wearing a status file's name; `design/` sits at the
  repository root beside things that ship; `ThemeToggle.tsx`, `theme.ts` and
  `useActiveStep.ts` sit loose in `src/` while `PlanGauge.tsx` is filed under
  `features/`; and the Plan UI lives in `App.tsx` while Do, See and Export each have
  their own panel.

## 2026-09-02 README rebuilt as a portfolio front page

- The README was a text-only status page: it opened with an internal handoff link,
  carried a stray `1` in the title, still said final submission verification was in
  progress, and showed none of the interface. It is the first thing anyone opening
  the submitted source URL reads.
- Rewritten around the screens. Hero, See and Do screenshots; the design direction
  comparison and why C was chosen; and five implementation notes that link to the
  code they describe — database-enforced duplicate completion, aggregates that
  return their own evidence, UTC storage with Seoul judgement, the same-origin CSP
  and public-data warning, and migrations that run before the server binds.
- Screenshots are synthetic per AGENTS.md rule 3. A local backend was seeded to the
  numbers the acceptance matrix documents (5 tasks, 3 completed, 1 overdue, 2
  blocked, 300 estimated, 260 actual, -40 variance) so the See screen shows the same
  figures as the fixture, plus a second plan carrying a reflection line.
- Captured with headless Chrome over CDP at 2x, clipped per section, in both themes;
  the browser pane cannot save files or paint scrolled content. The generator is kept
  at `tools/capture_screenshots.mjs` so the shots can be regenerated.
  Light and dark pairs are served through `<picture>` so GitHub follows the reader's
  theme.
- Every relative link and image path in the README was resolved against the working
  tree. Coverage quoted from a fresh run: 53 passed, 92%.
- Documentation only; no application code and no build output change.

## 2026-09-02 migration deprecation warning removed

- `migrations/env.py` carried Flask-Migrate's stock `get_engine()`, which tries
  `db.get_engine()` first for Flask-SQLAlchemy<3. That call still resolves on 3.x, so
  the fallback never ran and each migration emitted a DeprecationWarning instead —
  the 12 warnings the suite had been reporting. The method is due for removal in
  Flask-SQLAlchemy 3.2, and `deploy/start.sh` runs `flask db upgrade` under `set -eu`
  before serving, so its removal would stop the service from starting rather than
  fail quietly. pyproject pins Flask-SQLAlchemy>=3.1,<4, so the legacy branch was
  unreachable by the project's own constraint (D-031).
- Now calls `db.engine` directly. The suite reports 53 passed and no warnings at all,
  down from 12.
- Migration behaviour re-checked because this file is on the deployment's startup
  path: a fresh SQLite database upgraded through all four revisions, a repeated
  upgrade was a no-op, `db check` reported no new operations, and `db current` showed
  the head revision. Offline mode (`db upgrade --sql`) still emits all eight tables,
  which exercises the same function through `get_engine_url`. Running the migration
  commands under `-W error::DeprecationWarning` raised nothing.
- PostgreSQL is covered by the deployment itself: startup migrations run before
  Waitress serves, so a broken `env.py` would prevent the service from coming up.

## 2026-09-02 dev proxy target is configurable

- `frontend/vite.config.ts` hard-coded the dev proxy to `http://127.0.0.1:5000`, so
  when another app holds port 5000 there was no way to move the backend: following
  the documented local run steps sent `/api` to whatever else was listening. This is
  live on this machine, where `flask-board` occupies 5000.
- `T06_API_TARGET` now overrides the target, defaulting to the previous value. Read
  through Vite's `loadEnv` with a `T06_` prefix rather than `process.env`, which
  avoids adding `@types/node` for one lookup; `loadEnv` picks up both shell variables
  and `.env` files.
- Verified both paths against a backend on 5055 while `flask-board` held 5000. With
  the variable set, `/api/live` through the dev server returned the T06 payload and
  `/api/plans` returned T06 plans. Without it, the same request returned exactly what
  port 5000 returns directly, confirming the default is unchanged.
- Build output is byte-identical (`index-CpPmN_2E.js`, `index-B6MuCkAg.css`): the
  change affects only the dev server, and the deployment has no proxy at all because
  Flask serves the API and the built frontend from one origin.
- `docs/DEVELOPMENT.md` and `docs/process/ACADEMY-HANDOFF.md` now show the port-conflict path.
- 53 backend tests, the frontend build and `git diff --check` pass.

## 2026-09-02 smooth step navigation

- Step navigation animated instead of jumping (D-029). Both paths were instant: the
  step-bar anchors and `goToStep`'s `scrollIntoView`, neither of which set a
  behaviour, and `scroll-behavior` appeared nowhere in the stylesheet. One
  declaration on `:root` covers both, because `scrollIntoView` without an explicit
  behaviour follows the CSS. The step links also gained a 150ms background/colour
  transition so the current-step marker glides.
- The reduced-motion block previously disabled only `transition`. Animating a
  4000px document is exactly the movement that setting exists to stop, so it now
  restores `scroll-behavior: auto` as well.
- Verified: computed `scroll-behavior` is `smooth`; the reduced-motion rule sits at
  stylesheet index 562 against the `:root` rule at 396, so at equal specificity it
  wins whenever the query matches. Anchor landings clear the sticky bar in both
  layouts — desktop puts the section top at 148 against a 106px bar (42px spare),
  375px against a 131px bar (16px spare), with every section heading visible.
- The animation could not be observed here: the browser pane cannot perform scroll
  animations, and there is no reduced-motion emulation, so the cascade order is the
  evidence for the reduced-motion half. Notably `scrollTo` stopped taking effect in
  the pane once smooth was set, which is itself a sign the declaration applies.
  The user confirmed on the deployed app that the scroll animates and the step marker
  travels, which also closes the earlier open item on the scroll spy firing.
- 53 backend tests and the frontend build pass. CSS only; no TypeScript changed.

## 2026-09-02 step bar marks the section being read

- Considered porting the T05 floating section rail and decided against it (D-028).
  T06 has three sections and a sticky step bar that also carries the plan picker, so
  a rail would duplicate navigation and compete with the public warning for the first
  screen. The scroll spy inside it was worth taking: the three links looked identical
  and `aria-current` appeared nowhere in the codebase, so nothing on screen or in a
  screen reader said which section was being read.
- Bug found while building it, not present in T05. The T05 rail captures its section
  elements once in the effect. `TaskPanel` here is keyed on the plan id and remounts
  whenever the plan changes, so the captured `#do-step` becomes a detached node whose
  `getBoundingClientRect()` returns zeros — which reads as "already past the marker"
  and pins Do as permanently active. Found by instrumenting the hook and seeing that
  one section's measured top was `0` at every scroll position. Fixed by looking the
  elements up on every measurement; the instrumentation was removed afterwards.
- Verification was constrained. The browser pane fires no `scroll` events, no
  IntersectionObserver and no ResizeObserver callbacks at all, including the initial
  ones, and the real browser cannot reach the sandboxed local server. So the decision
  rule was extracted into a pure function and exercised directly under node against
  the measured layout (viewport 900, document 4458, section tops 374/1147/3152): all
  nine boundary cases pass, and the bottom guard is shown to be load-bearing —
  without it a short last section never activates. The wiring was then driven by
  dispatching `scroll` after each programmatic scroll, which exercises listener,
  measurement, state and DOM together.
- Results: 0/500/886 give Plan, 887 gives Do exactly at the boundary, 1500/2891 give
  Do, 3400 and the document end give See, and after switching plans `#do-step`
  measures 1147 rather than 0 with judgement correct again. Active link is
  `#1b64da` on white in light and `#6f9cf0` on `#0f1216` in dark. At 375px no
  overflow and scrolling down then back to the top returns to Plan. Public warning
  still on the first screen; priority still renders the literal `high`.
- Not verified here: that the browser itself emits `scroll` and ResizeObserver
  callbacks. That is browser-guaranteed rather than application code, but it means
  the feature should be scrolled once on the deployed site to confirm.
- 53 backend tests, the frontend build and `git diff --check` pass. Presentation only.

## 2026-09-02 plan-card estimate-vs-actual gauge

- The last open design item shipped (D-027). The selected plan card now carries a
  bar with a tick at the estimate and fill at the actual, so the gap reads before the
  numbers. Under fills short of the tick in `--good`, over runs past it in `--crit`,
  the same rule the See variance card uses; the signed figure keeps the ASCII hyphen.
- Selected card only. Actual minutes exist only on `/api/plans/<id>/see`, one call
  per plan, so a gauge on every card would fan out a request per plan on every first
  paint of a free-tier deployment. App owns one period-less summary fetch for the
  selected plan; SeePanel keeps its own period-aware fetch untouched, because a card
  representing the whole plan must not follow a period filter.
- Two problems found and fixed while checking by eye. The tick disappeared into the
  fill when actual exceeded the estimate, reading as a seam rather than a marker, so
  it now stands proud of the track with a `--surface` halo and the heads carry
  matching swatches. And the card's existing estimate line is the plan's own figure
  while the gauge uses the task-estimate sum (D-014) — different numbers sitting
  together, so both are now named: `계획 예상 300분` and `할 일 예상 300분`.
- Verified on the built frontend served by Flask against a seeded database: under
  (260 of 300) fills 86.7% with the tick at 99.8% in `--good`; over (520 of 300)
  fills 100% with the tick at 57.5% in `--crit`; switching plans moves the gauge to
  the newly selected card; a plan with no tasks shows the empty message and no bar.
  Light and dark both correct. At 375px no document or element overflow and both
  head labels stay on one line. Public warning still fully on the first screen,
  priority still renders the literal `high` with `text-transform: none`, and the sort
  rule is unchanged.
- 53 backend tests and the frontend build pass. Presentation only; no API, contract
  or migration change.

## 2026-09-02 submission tag moved onto the deployed toggle build

- Deploying the light/dark toggle left the `t06-submission` tag on the previous
  build, so the submitted source no longer matched the running product: a reader
  building from the tag would have got a screen with no theme button. T06-C01 itself
  only requires the URLs to open without authentication, but this project's own rule
  is that the submitted source is the code being served.
- The user confirmed the assignment is not yet submitted, so the tag was moved onto
  the deployed commit rather than leaving the mismatch. The claim that the tagged
  tree is byte-identical to `1d0e0f7` was removed — it stopped being true when the
  toggle shipped. The document now records the deployed asset names instead.
- Verified after the move: the tag resolves to the commit whose build Render serves
  (`index-CemQlsng.js`, `index-DZQlTvwW.css`), the tag tree opens without
  authentication, and its `docs/SUBMISSION.md` carries no placeholders.

## 2026-09-02 light/dark toggle

- Header toggle switches the theme manually (D-026). Two states, starting from the
  system preference; the choice persists in `localStorage` (`t06-theme`) and then
  overrides the system. Storage access is wrapped in try/catch for private windows.
- The strict CSP (`script-src 'self'`) rules out the usual inline pre-paint script,
  so `main.tsx` applies the stored choice before the first render and the
  `prefers-color-scheme` block is reduced to `--ground`/`--ink` under
  `:root:not([data-theme])` purely as a pre-mount fallback. The CSP was not changed.
- The dark palette now lives in one block, `:root[data-theme="dark"]`, because JS
  always writes a concrete value. `color-scheme` is set per theme so native date
  inputs follow.
- Verified on the built frontend served by Flask (production shape, port 5055):
  system light with no stored value starts light; the button switches to dark and
  stores `dark`; a reload keeps dark against a light system; the reverse case
  (system dark, stored `light`) also holds. `color-scheme` tracked the theme both
  ways. At 1280px no overflow, toggle at the top right. At 375px no document or
  element overflow, the toggle wraps below the title, and the public warning stays
  fully within the first screen (T06-C82, bottom 294 of 812). Priority still renders
  the literal `high` with `text-transform: none` (T06-C05, C15), the sort rule and
  the signed variance with its evidence counts are unchanged in both themes.
- 53 backend tests, `npm run build` and `git diff --check` passed. Presentation only.

## 2026-09-02 submission source URL correction

- The submitted Source URL pointed at application commit `1d0e0f7`. That tree's
  `docs/SUBMISSION.md` still read "not ready to submit", named an older commit as its
  own source, and carried both T06-C60 judgment lines as placeholders. A reader
  opening the submitted source would have read the placeholders, so T06-C59 and
  T06-C60 were not actually satisfied at the submitted URL.
- Fixed by tagging the submitted commit `t06-submission` and pointing the Source URL
  at the tag. A tag name can be written into the document before the commit exists,
  so the URL and the file it lives in stay consistent; a hash cannot.
- The tagged commit changes documentation only. `frontend/` and `backend/` are
  byte-identical to `1d0e0f7`, the code Render built and is serving as
  `index-Dc4X5YZr.js` and `index-BLGnwQPS.css`.
- Review of the Codex submission work also re-checked its recorded numbers against
  the live API: See `5 / 3 / 0 / 1 / 600 / 390 / -210`, the export's seven record
  counts, the retained `600` plan revision, and the reflection line carried into the
  next plan byte-for-byte. All matched. An earlier local reading of `6 / 601 / -211`
  was the transient state while the script-shaped verification task existed.
- The T06-C60 judgment and rejected-advice lines were raised with the user, who
  confirmed them as written.

## 2026-09-02 public completion verification

- Public Neon data now contains the real safe plan `T06 프로젝트 완주`, five
  linked tasks, three execution logs, three completed tasks, one reflection and
  one next plan carrying the approved improvement line.
- Plan estimate changed from 600 to 540 under the same UUID; revision history
  retained the original 600 and survived refresh.
- Task create/edit/complete/reopen/delete/search/filter/sort behavior was exercised
  on the deployed app. A temporary high-priority `backend`, `test` task was removed,
  leaving the five real tasks unchanged.
- Repeated activation of the first completion control left one completion event;
  See increased once. Three real tasks remain completed after refresh.
- See currently reports task 5, completed 3, overdue 0, blocked 1, estimated 600,
  actual 390 and variance -210. All seven cards exposed their exact source IDs or
  an empty evidence result.
- The approved reflection is `공개 환경의 저장·새로고침·집계 검증 시간을 구현 일정에 미리 포함한다.`
  The linked next plan carries the exact line and both records survived refresh.
- Script-shaped input rendered literally and was deleted after verification.
- `/api/export` returned two plans, one plan revision, seven tasks including two
  soft-deleted verification records, eight tag links, four completion events,
  three execution logs and one reflection. No real export file was committed.
- Working source, Git history, current public HTML/JS/CSS and API responses passed
  the common-secret pattern scan. Backend 53 tests, frontend production build and
  `git diff --check` passed.
- Render serves the same `index-Dc4X5YZr.js` and `index-BLGnwQPS.css` produced by
  application commit `1d0e0f79fe2f8a57d0f5a21e9ae4102bcbb36a38`.
- User approved the final judgment and rejected-advice statements in
  `docs/SUBMISSION.md`.

The user supplied a Chrome Incognito screenshot confirming the product URL,
public warning, source plan and carried next plan. A second Chrome Incognito
screenshot confirmed that the public full-commit source URL opens without
authentication and shows commit `1d0e0f7` with the repository file list. Product,
database health and source URLs returned HTTP 200 in the final check. No submission
verification remains.

학원 PC에서 이어갈 때는 `docs/process/ACADEMY-HANDOFF.md`를 먼저 읽는다.
최신 main 받기, 새 PC 설치/실행, 완료 작업, 남은 제출 검증과 이어가기 프롬프트를
정리했다. 집 PC의 `tmp/` 검증 스크립트·로컬 DB·환경 설정은 Git에 포함되지 않는다.

## Phase

**COMPLETE — Cards 1–5 implemented, publicly verified and ready to submit**

## Completed

### 2026-09-02 — See metric cards: signed variance and evidence counts

- The variance card renders its sign (`+220분` / `-40분`, ASCII hyphen) and is the only
  metric with a semantic colour: `--crit` when actual exceeded the estimate, `--good`
  when under, neutral at zero. The other six stay neutral, so the light default keeps
  its white-and-blue base and the screen carries one point of colour. Dark palette
  resolves to `#ef8279` / `#4fc3a1`. Decision D-025.
- The tone rules sit after `.metric-card[aria-pressed="true"] strong` at equal
  specificity, so selecting the variance card does not repaint the sign in the accent.
- `근거 기록 보기` replaced by the real counts, named per kind. A single total
  misread against the metric: 막힘 shows `2개` but is backed by 2 tasks and 3 logs, so the
  label reads `근거 할 일 5 · 기록 3` and matches what the drill-down lists.
- Verified against a seeded local database holding the matrix fixture
  (`[5, 3, 1, 2, 300, 260, -40]`) plus a second plan built to produce `+220`:
  both signs and both colours in light and dark, the variance drill-down listing
  exactly 8 records for `할 일 5 · 기록 3` with task/execution IDs visible (T06-C83),
  the value's leading character confirmed as ASCII 45 (T06-C32), and at 375px no
  document or card overflow with every evidence label on one line and card heights equal.
- 53 backend tests passed; `npm run build` (tsc + vite) passed. Presentation only —
  no API, contract, migration or test expectation changed.
- Not committed. Browser-pane screenshots of scrolled content were unreliable in this
  session, so the evidence above is computed-style and layout measurement, not images.

### 2026-09-02 — Plan/Do/See usability follow-up

- Saved plans appear before the optional new-plan form. Empty accounts show the
  first-plan form immediately after loading; saving selects the new plan and
  moves focus to Do. The existing-plan form opens through “새 계획 만들기”.
- One App-owned plan selection drives Do and See. Sticky anchor navigation moves
  between mounted sections, preserving drafts during step navigation. Plan-card
  actions, newly created follow-up plans and existing reflection links select the
  same plan. Changing plans resets task-local state rather than carrying it over.
- Execution forms span the full task card; form/grid children and native inputs
  can shrink. At 320px, datetime fields remain inside their card. Priority badges
  stay on one line, and mobile navigation labels use two consistent lines.
- Build and 53 existing tests pass. Synthetic browser checks cover two plans,
  matching tasks/See metrics, preserved draft during navigation, first-plan save
  and reload, 25-minute execution save/See update, and reflection-to-next-plan
  selection with exact carried improvement. No backend/schema/security change.
- Deployed from main at `92a115672a5a07068f6a97f99c625c9fe2f29eee`.
  Public HTML references `/assets/index-DnSTSqUZ.js` and
  `/assets/index-Dr1DAnWc.css`; new navigation code/styles, sampled fonts, license
  and PostgreSQL health are verified. Real-use records and final submission checks
  remain separate.

- Preliminary five-card material analyzed.
- Conflicts with the broader course overview identified.
- Draft acceptance matrix prepared.
- Conditional Flask architecture drafted.
- Shared Claude–Codex working agreement created.
- Codex skill `t06-diary-workflow` scaffolded.
- Local Git repository initialized on `main`.
- Preparation baseline committed as `303012b429234866e2f79e35568475537a094f2b`.
- Official assignment source saved as `docs/source/T06-OFFICIAL-ASSIGNMENT.md`.
- Official requirements reconciled on 2026-09-01.
- All 44 official acceptance IDs fixed with observable inputs and expectations.
- React + Flask + PostgreSQL architecture activated.
- Initial real-use subject fixed as `T06 프로젝트 완주`, measured in minutes.
- Canonical `contracts/pds-schema-v2.json` created and JSON syntax verified.
- React + Vite and Flask + SQLAlchemy application skeletons created.
- Card 1 plan creation and immutable revision history implemented.
- T06-C04–T06-C08 passed in automated tests and local browser verification.
- Backend: 3 tests passed with 89% coverage; frontend production build passed.
- Card 2 task model, normalized tags, soft deletion, API, and React workflow implemented.
- T06-C09–T06-C20 passed in automated tests.
- Browser verification passed for task creation, content edit, complete, reopen, and search.
- Backend: 7 tests passed with 87% coverage; updated frontend production build passed.
- Card 3 execution logs and database-protected completion events implemented.
- T06-C21–T06-C27 passed locally: UTC persistence, Seoul display, actual minutes,
  exact blocker text, preserved estimates, one event and one completed-count increase.
- Four concurrent requests using independent database connections return one event.
- Replays after reopen do not complete the task again; a new key starts a new cycle.
- React supports execution entry/history and the See completed count with source IDs.
- Browser verification: 13:00–14:30 Seoul, actual 75 minutes, blocker text, estimate
  90 retained; double-click leaves one completion event and completed count 1;
  refresh restores the same execution ID and values, with no console errors/warnings.
- Backend: 31 tests passed, 90% coverage. Frontend production build passed.
- Card 2 → Card 3 migration preserves existing values and repeated upgrade is safe.
- Local `db upgrade` and `db check` passed; PostgreSQL execution remains unverified.
- Card 4: seven See metrics, exact source task/log drill-down, due-date period
  selection, reflection persistence, and next-plan carry-over implemented.
- T06-C28–T06-C33 and T06-C83 passed locally; all earlier regression checks passed.
- Synthetic fixture: 5 tasks, 3 completed, 1 overdue, 2 blocked, estimated 300,
  actual 260, variance -40. Empty aggregates and Seoul midnight boundary passed.
- Browser verified all seven source views, period filtering, reflection creation,
  exact improvement carry-over, empty next-plan aggregates, and refresh persistence.
- Card 4 migration preserves earlier logs/events and repeated upgrade is safe.
- Four concurrent next-plan requests create one linked plan.
- Current backend result: 47 tests passed, 92% coverage; frontend build passed.

## Card 5 local results

- Full JSON export, consistent database snapshot and all-column canonical contract implemented.
- Docker builds React and serves it with non-root Waitress; PostgreSQL is mandatory.
- Local PostgreSQL migrations, repeated upgrade and schema check passed.
- Four concurrent completion requests create one event; four next-plan requests create one plan.
- Web restart preserves all exported IDs, dates, values, units and links.
- Backend: 51 tests passed, 91% coverage. Frontend and Docker production builds passed.
- Browser at port 5173: exact warning visible, script-shaped input rendered literally
  with no corresponding script element, JSON download success status, no console warnings/errors.
- Browser tool blocked port 8000 with ERR_BLOCKED_BY_CLIENT; production HTTP and
  database tests passed, but production browser verification is still unrun.
- Common-secret pattern scan covered working files, frontend bundle and 142 Git
  objects with zero findings after recognizing the existing replace_me placeholder.
- Deployment instructions and submission draft are ready. Local data is synthetic.

## Not started

- Public hosting and private-browser product/full-commit source verification
- Real non-sensitive user entries and live safety checks
- User judgment/rejected-advice statements and final submission

## Render + Neon preparation

- User selected Render Free + Neon Free for approximately three months.
- render.yaml defines one free Docker service; no paid database is provisioned.
- /api/live avoids DB queries during hosting probes; /api/health verifies DB readiness.
- SQLAlchemy pre-ping checks connections reused after database sleep.
- 52 tests passed with 91% coverage; frontend production build passed.
- Render browser shows Sign In; account connection and Neon database creation are pending.
- See docs/RENDER-NEON.md. docs/archive/GCP-SETUP.md is a superseded alternative.

## Next action

Public deployment update: the user created Neon and Render Free. Public URL is
https://t06-plando-see-diary.onrender.com. API liveness/PostgreSQL readiness return
200, but the initial root page returned 404 because the installed package resolved
the frontend path incorrectly. STATIC_DIST is now explicit in Docker; missing
production index.html fails startup. 53 tests and installed-image root/assets
checks pass. Fix 7bb42551308c5d90ab717227982d563e5b9f7a99 was pushed and automatically
deployed. Public /, JS, CSS, /api/live and /api/health now all return 200. Browser
tool access was blocked; ask the user to reload for visual confirmation, then finish
deployed save/refresh/source/export acceptance.

Account setup is complete. Verify public access, cold-start recovery, stored data and JSON.
Obtain real safe records and user judgment text for SUBMISSION.md.
Public app/database connectivity is verified; UI and full acceptance remain pending.

## Design token layer

Accepted follow-up (2026-09-02): user approved adopting the design after the review
fixes. Gothic A1 5.3.0 is bundled through Fontsource at weights 400/500/700/800;
external Google links are removed, Vite emits even small fonts as files to preserve
the existing same-origin CSP, and the OFL license ships under /assets/fonts/.
Evidence labels use stronger light/dark colors; sort rule and source IDs are 13px.
Build and 53 tests pass. Flask serves the built CSS and requested Korean/Latin
fonts with HTTP 200. Dark and forced-light local views retain metrics and IDs;
375px dark/mobile and 1280px views have no document overflow. Both review findings
are resolved. Merged and pushed to main as application commit
`d9b23a077b640a6cf4e02be92c356781f52dc958`. Render now serves the new
`/assets/index-CmX_ZMf7.css`; public Korean/Latin WOFF2 samples and OFL license
return 200, and /api/health confirms PostgreSQL. The CSP remains same-origin.
Earlier design review findings below describe the pre-fix state.

Codex review (2026-09-02, HEAD `2ebb7bb`): adopt after fixing external font/CSP
compatibility and low-contrast evidence labels. Build and 53 tests pass; seeded
dark-theme browser checks preserve the public warning, priority literals, success
criterion, sort rule, execution records and See sources. Main is unchanged; no
merge/deployment performed. Full review handoff: `docs/process/REVIEW-CSS-TOKEN-LAYER.md`.

Scope: presentation only. No markup, API, contract, or test expectation changed.

- Direction chosen from four sketched candidates: "flow" — Gothic A1, single accent
  `#1B64DA`, Plan/Do/See read as an ordered process. Rejected candidates kept as
  evidence of the comparison.
- `frontend/src/styles.css` rewritten on a token layer: one accent plus three
  semantic colors (`--good` `--warn` `--crit`), three radii, 4px spacing scale,
  four font weights, 150ms transitions, `prefers-reduced-motion` respected.
- Dark palette added under `prefers-color-scheme: dark`; `color-scheme: light dark`
  set so native date inputs follow the theme.
- Gothic A1 is now bundled locally with a fallback stack (supersedes Google Fonts).
- Removed `text-transform: uppercase` from `.priority`. The DOM value was already
  `high`, but the screen rendered `HIGH`; T06-C05 and T06-C15 expect the plan and
  task screens to show `high`, so the literal is now what the viewer reads.
- Removed the `min-height: 48px` hack on `.plan-card > p`, which reserved blank
  space under every success criterion.
- Locked screen elements left intact in position and wording: the public-data
  warning (T06-C82), the sort rule (T06-C20), success criterion text (T06-C06),
  and the source task/execution IDs (T06-C83).

Evidence: `npm run build` passed; `python -m pytest backend/tests -q` passed 53
tests; dev server checked in light and dark at 1280px with computed styles verified
(`.priority` text-transform `none`, tokens resolving, no horizontal overflow).

Remaining design work needs markup changes. Step navigation and the plan-list
empty state landed in `92a1156`; still open are the plan-card estimate-vs-actual
gauge and signed variance plus evidence counts on the See metric cards. Run the
acceptance suite before and after each of those.

Direction rationale, the four sketched candidates, sketch links, the token summary
and the list of screen elements design must not touch are in `docs/DESIGN.md`.
Editable sketch and prototype sources are committed under `design/` with their own
README; they are not built or served, and the 2.5 MB seeded canvases stay ignored.

## Working tree

Branch: `main`

Baseline commit: `303012b429234866e2f79e35568475537a094f2b`

Official requirements commit: `f25841f`

Card 1 implementation commit: `1bb2c42`

Card 1 handoff commit: `1a4ea62`

Card 2 implementation commit: `f2b9c8c`

Card 2 handoff commit: `22a6655`

Remote: https://github.com/myeongjundev/t06-plando-see-diary

Card 3 start commit: `f8e04fd1d9c413ccf6999a9d666f78f6f3e349b2`

Cards 3–5 and Render/Neon preparation were committed and pushed to origin/main as
`150a9052610705dad52274d94d28f674ab07d324`. Account connection and public deployment
remain pending; see `docs/process/HANDOFF.md`.

Design token layer and review fixes were merged from `design/css-token-layer` into
`main`, pushed, and verified on Render at application commit `d9b23a0`.

## 할 일 목록을 카드에서 줄로 (D-034)

할 일 18개를 로컬에 넣고 실제 화면을 떠서 판단했습니다. 개수보다 행의 생김새가 문제였습니다.

| | 이전 | 지금 |
|---|---|---|
| 행 높이 (1280px) | 114px | 56px |
| Do 구획 (18개) | 2,656px | 1,496px |
| 문서 전체 | 4,890px | 3,730px |
| 행 높이 (375px) | 138–155px | 110px |
| Do 구획 (375px) | 3,230px | 2,829px |

`내용 수정`·`삭제`·`실행 기록 열기` 세 버튼을 아이콘 셋으로 바꿨습니다. hover 뒤에 감추지
않았습니다 — 터치 기기에는 hover가 없고, 수정·삭제는 T06-C10·C13의 근거입니다. 이름은
`title`과 `aria-label`이 지킵니다. 아이콘 색은 `--ink-2`(#4e5968)로 흰 바탕 대비 약 7.6:1입니다.

375px에서 4열 그리드를 그대로 두면 제목이 세 줄로 접혔습니다. 측정값은 넘침 0이었고
화면을 떠 보고서야 발견했습니다. 좁은 화면은 flex 두 줄로 다시 짰습니다.

확인: 53개 검사 통과, 프런트 빌드 통과. 1280px·375px 모두 문서·행 넘침 0. 공개 안내문
첫 화면(top 167), 정렬 기준 문구, `high`/`medium`/`low` 리터럴과 `text-transform: none`,
할 일 앵커 18개 유지. 실행 기록 열기 → 줄 전체 너비로 4개 입력칸 마운트, 라벨과
`aria-expanded` 전환, 닫기 → 언마운트. 수정 폼·삭제 확인도 줄 전체 너비.

## 계획을 바꿀 때 카드가 튀던 것 (D-035, D-036)

«자세히»가 어떤 규칙에도 걸리지 않아 브라우저 기본 버튼(검은 2px outset)으로
나왔습니다. 페이지의 버튼 91개 중 유일했습니다. 보조 버튼 규칙에 넣고, 그 규칙에
«새 보조 버튼은 반드시 여기에 더하라»는 주석을 달았습니다 — D-033의 «내용 수정»·
«삭제»에 이어 두 번째로 같은 이유로 새어 나갔기 때문입니다. 대비는 라이트 4.63:1,
다크 6.46:1입니다.

계획 줄을 누르면 카드가 깜빡이던 문제는 재현해서 원인을 확인했습니다. 클릭 한 번에
카드 높이가 **310 → 231 → 264 → 231 → 264**로 네 번 움직였습니다.

1. `setPlanSummary(null)`을 받아오기 전에 호출해 게이지를 먼저 지웠습니다.
2. `dataRevision`이 의존성인데, 계획을 바꾸면 `TaskPanel`(계획 ID로 keyed)이 다시
   마운트되며 곧바로 목록을 읽고 `dataRevision`을 올립니다. 그래서 효과가 두 번
   돌았고 지우기도 두 번 일어났습니다.

집계에 계획 ID를 붙여 두고 지금 계획의 것일 때만 그리도록 바꿨습니다. 이전 계획의
숫자를 그대로 두는 선택지는 없었습니다. 게이지 자리는 5rem으로 미리 잡아 기다리는
동안에도 카드가 움직이지 않습니다. **전환 네 번 모두 323px 고정**입니다.

확인: 53개 검사·빌드 통과. 기본 버튼으로 남은 것 0개. 공개 안내문 첫 화면(top 167),
정렬 기준 문구, 우선순위 리터럴, 넘침 0.

## 아이콘이 버튼 밖으로 밀려 있던 것 (D-037)

행의 아이콘 세 개가 가운데가 아니라 오른쪽 끝에 붙어 있었습니다. 왼쪽 여백 15px,
오른쪽 1px이었습니다.

D-035에서 «자세히»를 보조 버튼 규칙에 넣을 때 그 규칙에 `.task-actions button`이
함께 있었는데, 이 선택자가 `.icon-button`보다 명시도가 높습니다 — (0,1,1) 대 (0,1,0).
그래서 `padding: 8px 14px`가 `padding: 0`을 덮어썼고, 32px 버튼의 내용 상자가 2px로
줄어 16px 아이콘이 밖으로 밀렸습니다. 시계·연필에만 테두리가 보이고 휴지통에는 없던
것도 같은 충돌입니다(`.icon-button.danger`는 (0,2,0)이라 이겼습니다).

`.task-actions`에는 이제 아이콘 버튼밖에 없으므로 그 선택자를 규칙에서 걷어냈습니다.
inline SVG가 baseline에 놓여 아래로 내려앉는 것도 `display: block`으로 막았습니다.

확인: 1280px·375px 모두 네 방향 여백 **8px 동일**, 상자 32×32. 수정 폼·삭제 확인의
글자 버튼은 스타일 그대로(주버튼 파랑 테두리, 삭제 확인 빨강 채움). 기본 버튼으로
남은 것 0개(전체 94개). 53개 검사·빌드 통과, 넘침 0.

## 목록이 무엇을 하라고 말하게 (D-038, D-039, D-040)

길이보다 **열여덟 줄이 전부 똑같이 생긴 것**이 문제였습니다. 훑어도 다음에 뭘 할지
알 수 없었습니다. 높이를 줄이는 대신 읽히도록 고쳤습니다.

**마감 표시** — `2026-09-0x`가 열여덟 줄이면 어느 게 늦었는지 머릿속에서 빼야 합니다.
지났거나 오늘·내일일 때만 앞에 표시를 붙입니다. 모든 줄에 붙이면 아무것도 눈에 띄지
않으므로 드물게 둡니다. 저장한 날짜는 T06-C14의 근거라 그대로 옆에 남습니다.
급한 차례대로 빨강 → 노랑 → 회색이고, 파랑은 동작에만 남겨 뒀습니다(D-025).
판정은 See와 같은 서울 시간대입니다(D-008).

**완료 분리** — 끝난 일이 목록 맨 위를 차지하고 있었습니다. 아래 `완료 N개 보기`로
접습니다. 다만 완료하거나 되돌리면 그 묶음을 자동으로 폅니다 — 어디로 갔는지 보이고
T06-C11·C12의 되돌리기가 닿아야 합니다. 상태 필터를 쓰는 중이면 나누지 않습니다.
나누면 `완료`로 거른 결과가 빈 목록처럼 보여 T06-C19가 깨집니다.

**대비** — `--crit`을 `--crit-soft` 위에 글자로 올리면 3.82:1, `--warn`은 3.86:1이었습니다.
11px는 WCAG의 «큰 글씨»가 아니라 4.5:1이 필요합니다. 우선순위 배지에 원래 있던
미달인데 마감 표시가 같은 짝을 두 배로 늘리게 되어, `--crit-ink`·`--warn-ink`를
따로 두고 soft 배경 위 글자에만 씁니다. 채움·테두리·게이지는 원래 색 그대로입니다.

| | 이전 | 지금 |
|---|---|---|
| 배지 대비 (라이트, 최악) | 3.82:1 | **5.32:1** |
| 배지 대비 (다크, 최악) | 5.95:1 | 5.95:1 |
| 행 높이 | 56px | **56px** (표시가 높이를 안 늘림) |

확인: 53개 검사·빌드 통과. 검색 «마이그레이션» → 1건, 없는 낱말 → «조건에 맞는 할 일이
없습니다», 지우면 19건 복귀. 상태 필터 `완료` → 1건 전부 완료, 완료 묶음 없음.
완료 묶음 펴기 → 취소선·되돌리기 버튼 닿음. 1280px·375px 넘침 0. 공개 안내문
첫 화면(top 167), 정렬 기준 문구, 우선순위 리터럴과 `text-transform: none` 유지.

## 계획 목록에 테두리와 검색 (D-041, D-042, D-043)

**테두리** — 줄마다 테두리를 둘러 네 장이 떠 있는 것처럼 보였습니다. 할 일 목록과 같이
목록 전체가 하나의 상자고 항목은 그 안의 줄입니다. 19rem 상한과 안쪽 스크롤은 D-032
그대로입니다.

**검색** — `GET /api/plans`에는 limit이 없고 화면도 전부 그립니다. 여섯 줄을 넘으면
상자 안에서 스크롤해 찾는 수밖에 없었습니다. 다른 계획이 다섯을 넘을 때만 검색이
나옵니다 — 네 개일 때는 잡음입니다. 줄에 보이는 것이 이름이라 **이름만** 찾습니다.
안 보이는 값까지 걸리면 왜 걸렸는지 알 수 없습니다. 찾아서 고르면 검색어를 비웁니다.
남겨 두면 나머지 계획이 가려집니다. 거르는 동안에는 머리글이 «다른 계획 2개 · 전체 8개».

**정렬** — 배지가 `low` 35px · `high` 40px · `medium` 60px이라 훑어 읽는 제목 열이
줄마다 **25px씩 흔들렸습니다.** 두 목록 모두 배지를 3.75rem으로 맞췄습니다. 계획
카드의 배지는 혼자라 맞출 대상이 없어 그대로 뒀습니다.

| | 이전 | 지금 |
|---|---|---|
| 제목 시작점 흔들림 | 25px | **0px** |
| 계획 줄 (375px) | 94px | **73px** |
| 계획 줄 (1280px) | 41.6px | 48px (여백을 줄에 맞춰 늘림) |

확인: 53개 검사·빌드 통과. 검색 «회고» → 2건, 없는 이름 → «이름이 맞는 계획이
없습니다», 거른 상태에서 눌러도 선택 전환됨, 지우면 8건 복귀. 상자 304px에서 스크롤,
7번째 줄이 살짝 걸쳐 더 있음을 알립니다. 1280px·375px 넘침 0. 공개 안내문 첫 화면
(top 167), 정렬 기준 문구, 우선순위 리터럴과 `text-transform: none` 유지.

## 계획 목록에 우선순위 필터 (D-044)

이름 검색 옆에 우선순위 선택을 뒀습니다. 나오는 조건은 검색과 같습니다 — 다른 계획이
다섯을 넘을 때. 둘은 AND로 걸립니다.

**둘을 다르게 비웁니다.** 계획을 고르면 검색어는 비우고 우선순위는 남깁니다. 이름을
치는 건 «이걸 찾는다»라서 골랐으면 끝이지만, 우선순위는 «이 부류를 본다»라서 골랐다고
풀어 버리면 훑던 흐름이 끊깁니다.

배치에서 한 번 틀렸습니다. `.plan-filters`에 기준 너비를 주지 않아 컨테이너가 내용보다
좁게(312px) 잡혔고, 검색(192px)과 선택(125px)이 세로로 쌓였습니다. 26rem을 기준으로
주니 한 줄에 들어갑니다. `input`과 `select`는 같은 패딩에서도 기본 줄높이가 달라 37px
대 31px로 어긋나 있어서 `align-items: stretch`로 맞췄습니다.

확인: 53개 검사·빌드 통과. `보통` → 3건, `보통`+«T0» → 2건, 안 맞는 조합 → «조건에 맞는
계획이 없습니다», 지우면 8건 복귀. 거른 상태에서 눌러도 선택 전환되고 검색어만 비워짐
(우선순위 `medium` 유지). 1280px에서 검색 283px·선택 125px 한 줄 같은 높이,
375px에서도 한 줄. 넘침 0. 공개 안내문 첫 화면(top 167), 정렬 기준 문구, 우선순위
리터럴과 `text-transform: none` 유지.

## 다음에 이어갈 곳 (2026-09-02 저녁 기준)

오늘 UX 작업은 여기서 끊었습니다. 이어받는 쪽이 알아야 할 것만 적습니다.

### 상태

`main` = 태그 `t06-submission` = 배포본. 셋이 같은 커밋을 가리킵니다.

### 로컬 실행

포트 5000은 이 PC에서 다른 앱(«Flask RESTful 게시판»)이 쓰고 있습니다. 백엔드를 옮기고
프록시를 그쪽으로 돌려야 합니다.

```powershell
# backend/
.\.venv\Scripts\flask.exe --app app:create_app db upgrade
.\.venv\Scripts\flask.exe --app app:create_app run --host 127.0.0.1 --port 5055

# frontend/, 다른 터미널
$env:T06_API_TARGET = "http://127.0.0.1:5055"
npm run dev -- --host 127.0.0.1 --port 5182
```

`backend/instance/t06.db`에는 화면을 확인하려고 넣은 합성 계획 8개와 할 일 21개가
들어 있습니다. Git에 올라가지 않으므로 다른 PC에는 없습니다. 목록이 길어질 때의
화면을 다시 보려면 새로 넣어야 합니다.

### 남은 후보

| | 내용 | 판단 |
|---|---|---|
| 우선순위 그룹 | 목록에 `높음 7` / `보통 7` 구분선을 넣고 배지 반복을 없앤다 | **권하지 않음.** 리터럴이 머리글로 올라가고 목록이 셋으로 갈라져 보여 T06-C15·C20에 위험이 있다 |
| See 구획 | 버튼 11개. 그중 «집계 새로고침»이 왜 필요한지 화면에 설명이 없어, 오히려 숫자를 못 믿게 만든다 | 없애거나 자동 갱신으로 바꾸는 쪽 |
| 중복 요청 | 계획을 바꿀 때마다 `/see`를 두 번 부른다. 화면에는 안 보이지만 무료 티어에서는 낭비다. `TaskPanel.refresh()`가 목록이 그대로여도 `onDataChange()`를 부르는 것이 원인 | See 갱신 경로를 함께 봐야 해서 미룸 |

### 제출물

제출은 취소된 상태입니다. 폼은 40자 전체 commit 해시를 요구하므로 `/tree/<태그이름>`은
받지 않습니다. 제출 PDF와 `docs/SUBMISSION.md`의 에셋 이름은 아직 `ae9510c` 시점이라,
실제로 낼 때 `python tools/generate_verification.py`부터 다시 돌려야 합니다.

### 미룬 정리 (기능과 무관)

481줄짜리 `STATUS.md`를 상태와 변경 기록으로 나누기 · 루트 `design/`을 `docs/design/`으로
옮기기 · 프런트엔드에 `components/`·`hooks/`·`lib/` 만들기 · `App.tsx`에서 Plan 패널
떼어내기.
