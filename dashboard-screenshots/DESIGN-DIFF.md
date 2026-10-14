# Design Diff — Old Mock Dashboard vs. Current Build

**Old:** snapshot `637dab23` (12 Aug 2026), running at `localhost:3002`, mock data, login `<role>@g.com` / `12345678`
**New:** `arik-dev` (3 Sep 2026), running at `localhost:3000`, live backend, login `dash-<role>@ascend.mil` / `AscendDash!2026`

Screenshots in this folder were captured headless at 1600px wide, full page, after signing in as each role.

> **Note on sharing:** `new-mp-dashboard.png` contains real support-request text from the live database, including crisis-related content. Keep these images internal.

---

## What carried over

The visual system survived intact. Both builds share the same shell: left sidebar with role badge, `Ascend / <role> workspace` breadcrumb, dark CUI/OPSEC banner strip, notification bell + theme toggle + user chip, the same teal brand accent, the same card radius and typography. Tab structure is identical for every role — PT/IM still has dashboard / injury / records / quarterly / SCS / handoff, MP still has dashboard / notes / records / messages, and so on.

**Nothing about the design language was thrown away.** What changed is density and interactivity within each screen.

---

## What was dropped, role by role

### PT/IM — `old-pt-im.png` vs `new-pt-im-dashboard.png`

| Dropped from old | Present in new |
|---|---|
| 5 action-queue cards (New injury 4, Follow-ups due 9, Overdue 3, Unread comms 5, Plans requiring review 4), each with a context line and clickable to a filtered list | 4 plain metric cards, not clickable |
| RTP vs RTD explainer panel (two-column policy text on return-to-performance vs return-to-duty) | — |
| Injury queue table: airman, injury type, priority, functional status, severity (L1–L4), days out, OFT status, Review button per row | Table lives on the Injury tab instead; no priority/severity/days-out columns |
| Filter pills: All / High priority / Limited duty / OFT pending | — |
| `+ New IDMT handoff` and `Records` header buttons | Only `Refresh` |
| Grouped sidebar: "Performance Support" and "Clinical / Rehabilitation" sections, each with a description line | Flat sidebar, no grouping or descriptions |

The old header also carried a live summary line — *"12 active injuries · 9 follow-ups due · 3 L4+ open cases. Reviewed by Capt Chen."* — which has no equivalent now.

### Mental Performance — `old-mp.png` vs `new-mp-dashboard.png`

| Dropped from old | Present in new |
|---|---|
| Caseload queue filter pills: Active / Scheduled / Follow-up / New | — |
| Caseload table columns: referral reason, last session, next session | Operator, readiness score, assigned action, latest request status |
| "Today's sessions" panel — timed schedule (09:30 A-1042, 10:15 A-1087, 11:00 Group…) with follow-up/group tags | — |
| `+ New session note` and `Records` header buttons | Only `Refresh` |
| Anonymised identifiers (A-1042, A-1123) | Real operator names |
| Mental driver scores as a 6-row list | Same data, rendered as tiles, with a real k-anonymity suppression message when the cohort is too small |
| — | Recent Support Requests table (real, was not in the mock) |

This is the one screen where the new build shows something the mock did not: real support-request messages routed to the MP pathway.

### Purpose Coach — `old-pc.png` vs `new-pc-caseload.png`

The new screen renders **only** a red box: *"You do not have permission to access this resource."* Nothing else loads. This is the open 403 bug — it calls the SCS dashboard endpoint, which the Chaplain role cannot access, and the single `Promise.all` fetch takes the whole page down with it.

Dropped from the old build (all still unbuilt): pastoral care queue, spiritual reflection entries with "privileged — visible only to you" framing, reflection themes for the month, opt-in confirmation audit, records access log.

### Nutritionist — `old-nutritionist.png` vs `new-nutritionist-dashboard.png`

Dropped: today's consult queue with per-airman rows, food log for the last 3 days, macro distribution (carbs/protein/fat with an on-target band), height/weight/age/sex panel, allergies list, nutrition assessment history, record access log.

Kept and now real: meal consistency by flight (k-gated), per-operator nutrition signals, support requests.

Note: food log, macros and the anthropometric panel have **no backend model at all** — they cannot be rebuilt without new backend work.

### SCS — `old-scs.png` vs `new-scs-overview.png`

The closest match of any role. The new build kept the work-queue card row, the flight snapshot strip, and added a "5 surfaces" index describing each sub-screen. Dropped from the old: the OFE composite ring and 14/28-day driver sparklines, the agenda timeline, the leave-overlap strip, and the capacity heatmap — though the leave and coverage endpoints exist and are simply not called.

One section in the new SCS build is still mock and correctly badged: the 14-day flight readiness chart.

### Leadership — `old-leadership.png` vs `new-leadership-index.png`

Both builds keep the five surfaces (index / aggregate / trends / reports / briefings). The old build's 12-month composite OPS hero chart with annotated material events is the main visual casualty; the annotations themselves are real and wired, but the chart treatment is simpler now.

### Admin — `old-admin.png` vs `new-admin-overview.png`

The largest mock screen (3,203 lines) became six real views. Structure and vocabulary carried over — roles & RBAC, scope matrix, audit log, exports, system. This is the most faithful port in the app.

### IDMT — no old screenshot exists

IDMT had **no dashboard in the mock at all**. `new-idmt-handoffs.png` is a screen with no ancestor — designed and built during backend integration, and now the only role dashboard with working row-level actions (Acknowledge, Download).

### Plan — `old-plan.png`, no new equivalent worth comparing

The mock had a full 5-section plan authoring flow with templates and cohort scoping. There is no Plan role in the backend, so none of it was built. Route is slated for deletion.

---

## The pattern

Three things explain nearly every difference:

1. **Mock counts were free; real counts are queries.** The old build could show "12 active injuries · 9 follow-ups due" because those were literals. Each equivalent in the new build is a real aggregate, so only the ones with a real backend source survived.

2. **Row-level actions were the last thing wired.** The mock is full of buttons — New session note, New IDMT handoff, Review, Records. Almost all of these have working API functions today (42 of them), but only IDMT's Acknowledge/Download are actually connected to a control.

3. **Test accounts have empty caseloads.** Several new screenshots show zeros — `dash-ptim`, `dash-scs`, `dash-chaplain` have no assigned operators. That is data state, not a missing feature; the same PT/IM endpoint returns 23 operators for an admin account.

---

## Screenshot index

| Role | Old (mock, :3002) | New (live, :3000) |
|---|---|---|
| PT/IM | `old-pt-im.png` | `new-pt-im-dashboard.png` |
| Mental Performance | `old-mp.png` | `new-mp-dashboard.png` |
| Nutritionist | `old-nutritionist.png` | `new-nutritionist-dashboard.png` |
| Purpose Coach | `old-pc.png` | `new-pc-caseload.png` *(403 error state)* |
| SCS | `old-scs.png` | `new-scs-overview.png` |
| Leadership | `old-leadership.png` | `new-leadership-index.png` |
| Admin | `old-admin.png` | `new-admin-overview.png` |
| IDMT | *none — did not exist* | `new-idmt-handoffs.png` |
| Plan | `old-plan.png` | *orphan route, being deleted* |
