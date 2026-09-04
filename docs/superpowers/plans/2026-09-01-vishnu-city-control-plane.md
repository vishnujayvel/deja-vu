# Vishnu City control-plane implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Beads is the authoritative task tracker; numbered steps here are execution
> instructions, not a second task list.

**Goal:** Give Deja Vu a dedicated Vishnu City rig whose protected router uses
Claude for implementation, Gemini for independent analysis, Claude Fable 5 for
terminal review, and rejects every Codex-family worker target.

**Architecture:** Complete the Switchboard cutover first, then add a generic
host-owned client-policy boundary rather than a Deja-specific conditional in the
planner. The Deja policy, capacity receipts, and standing review grants remain
outside the candidate repository. Vishnu City consumes those contracts through
explicit qualified formula targets.

**Tech stack:** Python 3 standard library, JSON policy, `pytest`, Gas City TOML
formulas, Beads, OpenUsage.

**Spec:** `docs/superpowers/specs/2026-09-01-vishnu-city-release-control-design.md`

**Beads:** `router-m2a` -> `router-bpi.12` and `router-bpi.11` ->
`router-bpi.13` -> `deja-vu-p3.6.2`

## Global constraints

- Do not implement against the retiring `gc-route` or `delegate-job` surface.
- Do not edit Vishnu City's global provider default or another rig's patches.
- The current Codex task may orchestrate; no Deja Vu city worker may use the
  Codex provider family.
- Capacity is an admission predicate, not a cost ceiling. Stale, absent, or
  unknown required capacity blocks dispatch.
- Candidate-owned manifests and Beads cannot mint provider policy or review
  authority.
- Every changed executable module receives a fresh Claude Fable 5 review bound
  to its current artifact and contract hashes.
- Preserve existing dirty worktrees. Perform implementation in isolated
  worktrees recorded on the owning Beads.

---

### Task 1: Finish and freeze the Switchboard worker-role contract

**Owner:** `router-m2a`, then `router-bpi.12`

**Files:**

- Modify in `gc-router`: `policy/routing-policy.json`
- Modify in `gc-router`: `tests/test_gc_route.py`
- Create during the clean cutover: `gc_router/switchboard/contracts.py`
- Create during the clean cutover: `gc_router/switchboard/capacity.py`
- Create during the clean cutover: `gc_router/switchboard/planner.py`
- Create during the clean cutover: `gc_router/switchboard/adapters/gas_city.py`
- Create during the clean cutover: `tests/test_switchboard_planner.py`
- Rename during the clean cutover: `bin/delegate-job` -> `bin/jobctl`

**Interfaces:**

- `TaskRequest.from_dict(raw: Mapping[str, object]) -> TaskRequest`
- `CapacitySnapshot.from_openusage(raw: Mapping[str, object], now: datetime) -> CapacitySnapshot`
- `plan_execution(request, capacity, routing_policy, playbook, client_policy) -> ExecutionPlan`
- `GasCityAdapter.validate(plan: ExecutionPlan, client_policy: ClientPolicy) -> None`

1. Add a production-policy matrix test proving `draft` and `impl` select native
   Claude, ordinary `review` selects Claude Opus, and `review_high` selects
   Claude Fable when their declared windows are fresh and above reserve. Run:

   ```bash
   cd "$HOME/workplace/gc-router"
   python3 -m pytest tests/test_gc_route.py -q -k role_matrix
   ```

   Expected before the final `router-m2a` correction: at least one role selects
   Codex or admits a provider with missing required capacity evidence.

2. Complete `router-m2a`'s fail-closed missing-window correction and rerun the
   complete routing matrix. Do not call a caller-specific explicit target proof
   of a correct generic allocator.

3. Implement `router-bpi.12`'s clean Switchboard cutover with the interfaces
   above. Preserve the immutable `ExecutionPlan` fields `decision_id`, `rig`,
   `task_kind`, `provider_family`, `provider`, `resolved_model`,
   `capacity_snapshot_id`, `policy_version`, and `permission_hash`.

4. Run the focused Switchboard planning suite, then the complete router suite:

   ```bash
   python3 -m pytest tests/test_switchboard_planner.py -q
   make test
   ```

5. Submit each changed executable module for exact-hash Fable review. Reconcile
   every `FIX-FIRST` finding before closing `router-bpi.12`.

### Task 2: Add host-owned Deja provider policy and Gemini capacity

**Owner:** `router-bpi.13`

**Files:**

- Create: `$HOME/workplace/gc-router/gc_router/switchboard/client_policy.py`
- Create: `$HOME/workplace/gc-router/gc_router/switchboard/review_grants.py`
- Create: `$HOME/workplace/gc-router/policy/clients/deja-vu.json`
- Create: `$HOME/workplace/gc-router/tests/test_deja_client_policy.py`
- Create: `$HOME/workplace/gc-router/tests/test_review_grants.py`
- Modify: `$HOME/workplace/gc-router/gc_router/switchboard/capacity.py`
- Modify: `$HOME/workplace/gc-router/gc_router/switchboard/planner.py`
- Modify: `$HOME/workplace/gc-router/gc_router/switchboard/adapters/gas_city.py`
- Modify: `$HOME/workplace/gc-router/bin/jobctl`

**Interfaces:**

```python
@dataclass(frozen=True)
class ClientPolicy:
    policy_id: str
    rig: str
    allowed_families_by_kind: Mapping[str, tuple[str, ...]]
    forbidden_families: frozenset[str]
    max_capacity_age_seconds: int


def load_client_policy(rig: str, policy_root: Path) -> ClientPolicy: ...
def enforce_client_policy(plan: ExecutionPlan, policy: ClientPolicy) -> None: ...
def observe_and_reserve(grant_id: str, semantic_key: str) -> CapacityReservation: ...
```

`tests/test_deja_client_policy.py` defines fixtures named `fresh_capacity`,
`routing_policy`, `playbook`, and `policy_root`, plus
`request(kind: str) -> TaskRequest`. Tests create a forced invalid result with
`dataclasses.replace`; they do not need a second routing implementation.

1. Write failing tests that load `deja-vu.json` and prove these exact rules:

   ```python
   def test_deja_rejects_codex_before_ranking(fresh_capacity):
       policy = load_client_policy("deja-vu", policy_root)
       plan = plan_execution(
           request("implementation"), fresh_capacity,
           routing_policy, playbook, policy,
       )
       assert plan.provider_family == "claude"
       with pytest.raises(ForbiddenProvider, match="codex"):
           GasCityAdapter.validate(
               dataclasses.replace(plan, provider_family="codex"), policy
           )


   def test_deja_analysis_can_select_fresh_gemini(fresh_capacity):
       policy = load_client_policy("deja-vu", policy_root)
       plan = plan_execution(
           request("analysis"), fresh_capacity,
           routing_policy, playbook, policy,
       )
       assert plan.provider_family == "gemini"


   def test_missing_required_window_blocks(capacity_without):
       policy = load_client_policy("deja-vu", policy_root)
       with pytest.raises(CapacityUnknown):
           plan_execution(
               request("implementation"), capacity_without("claude:weekly"),
               routing_policy, playbook, policy,
           )
   ```

2. Run the tests and verify RED:

   ```bash
   python3 -m pytest tests/test_deja_client_policy.py -q
   ```

3. Implement a strict client-policy loader. The Deja policy contains:

   ```json
   {
     "schema_version": 1,
     "policy_id": "deja-vu-model-policy/v1",
     "rig": "deja-vu",
     "allowed_families_by_kind": {
       "implementation": ["claude"],
       "analysis": ["gemini", "claude", "grok"],
       "evaluation": ["gemini", "claude", "grok"],
       "module-review": ["claude-fable"]
     },
     "forbidden_families": ["codex"],
     "max_capacity_age_seconds": 900
   }
   ```

   Reject unknown fields, duplicate families, empty allowlists, a family present
   in both lists, and any policy whose `rig` does not match the request.

4. Extend capacity normalization for `antigravity:geminiSession` and
   `antigravity:geminiWeekly`. Preserve source window names and timestamps; do
   not convert heterogeneous quota units into tokens.

5. Enforce the policy twice: remove forbidden candidates before ranking and
   revalidate the final plan in `GasCityAdapter.validate`. A manual
   `deja-vu/codex` target must raise `ForbiddenProvider` before `gc sling`.

6. Implement `router-bpi.11`'s protected grant store and `jobctl review-grant
   issue|show|revoke`. Bind a grant to repository identity, Fable target/model,
   system-prompt hash, permission hash, generation, and capacity source. Keep
   grant state outside candidate-controlled roots.

7. Run focused tests and the full suite:

   ```bash
   python3 -m pytest tests/test_deja_client_policy.py tests/test_review_grants.py -q
   make test
   ```

### Task 3: Register the dedicated Deja rig and formula

**Owner:** `deja-vu-p3.6.2`

**Files:**

- Modify: `$HOME/vishnu-city/city.toml`
- Create: `$HOME/vishnu-city/formulas/deja-vu-release.toml`
- Create: `$HOME/vishnu-city/tests/deja-vu-routing-smoke.sh`

1. Remove `hold:external` only after `router-bpi.13` is closed and its exact
   test and Fable evidence has been independently read.

2. Snapshot the resolved city configuration, then add one `[[rigs]]` block for
   `name = "deja-vu"`, the Deja repository path, default branch, and Gastown
   pack. Add only rig-scoped patches required to pin Claude implementation and
   Fable review roles. Do not touch `[workspace].provider`.

3. Create `deja-vu-release.toml` with required qualified variables
   `implementation_target`, `analysis_target`, and `fable_target`. Each model
   step records `gc.run_target`, `provider_family`, and `resolved_model`.

4. Add a disposable smoke that proves:

   ```bash
   gc --city "$HOME/vishnu-city" config show >/dev/null
   gc --city "$HOME/vishnu-city" config explain --rig deja-vu --agent claude
   gc --city "$HOME/vishnu-city" config explain --rig deja-vu --agent agy-gemini
   gc --city "$HOME/vishnu-city" config explain --rig deja-vu --agent claude-fable-review
   ```

   The smoke must also submit a dry/manual Codex target to the protected
   validator and assert `FORBIDDEN` without launching a provider.

5. Compare the post-change resolved configuration for every pre-existing rig
   with the snapshot. Any unrelated delta fails the task.

6. When fresh capacity exists, run one bounded disposable Claude
   implementation, Gemini analysis, and Fable review smoke. Record effective
   provider/model receipts and close only after the worktrees and temporary
   Beads are cleaned up.

## Completion gate

Phase 1 is complete only when `router-bpi.13` and `deja-vu-p3.6.2` are closed,
the negative Codex smoke is green, exact model provenance exists for all three
allowed lanes, and unrelated Vishnu City rigs remain unchanged.

## Approved-spec coverage

| Capability | Implementation location |
|---|---|
| `review-grant` | This plan, Task 2; `router-bpi.11` |
| `token-capacity` | This plan, Tasks 1-2; Switchboard capacity snapshot and reservation |
| `model-routing-policy` | This plan, Tasks 2-3; host client policy plus adapter revalidation |
| `review-intent` | `2026-09-01-release-evidence.md`, Task 3 |
| `release-evidence` | `2026-09-01-release-evidence.md`, Tasks 1-5 |
| `promotion-control` | `2026-09-01-progressive-promotion.md`, Tasks 1 and 3 |
| `publisher-rollback` | `2026-09-01-progressive-promotion.md`, Tasks 2 and 4 |

The plans leave no approved capability without an owning task. External network
publication remains an additional publisher adapter; the protected local
publisher fully exercises promotion and rollback semantics first.
