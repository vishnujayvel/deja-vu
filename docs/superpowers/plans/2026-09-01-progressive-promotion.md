# Progressive promotion and rollback implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Beads is the authoritative task tracker; numbered steps here are execution
> instructions, not a second task list.

**Goal:** Promote Deja Vu through one v2.0 baseline, three clean human-approved
incremental releases, and then protected automated promotion with canary,
rollback, and kill-switch controls.

**Architecture:** Promotion lives beside the protected external verifier in
`gc-router`, never in the candidate repository. An append-only state machine
consumes immutable release-evidence packets and writes decisions. The first
publisher adapter atomically changes a protected local active-release record;
GitHub or marketplace publication can later implement the same interface
without changing promotion semantics.

**Tech stack:** Python 3 standard library, JSON/JSONL protected state, `pytest`,
atomic file replacement, Beads evidence references.

**Spec:** `docs/superpowers/specs/2026-09-01-vishnu-city-release-control-design.md`

**Beads:** `deja-vu-p3.6.4`, blocked by `deja-vu-p3.6.3`

## Global constraints

- Promotion authority, verifier policy, thresholds, kill switch, and publisher
  credentials remain outside the candidate repository.
- Exactly three consecutive clean human-promoted incremental releases follow
  the v2.0 baseline before automated promotion can activate.
- A rollback, unresolved high-severity finding, held-out regression, or failed
  canary resets the clean calibration streak.
- The previously trusted verifier evaluates the next candidate. A candidate
  cannot certify or weaken its own verifier or policy.
- High-risk batches may automate only under the stricter policy ratified before
  the candidate existed.
- No external publisher is invoked by the initial implementation. The local
  protected publisher is complete, reversible behavior, not a fake network
  deployment.

---

### Task 1: Implement the protected promotion state machine

**Files:**

- Create: `$HOME/workplace/gc-router/gc_router/switchboard/promotion.py`
- Create: `$HOME/workplace/gc-router/tests/test_promotion.py`
- Create: `$HOME/workplace/gc-router/policy/deja-vu-promotion-policy.json`
- Modify: `$HOME/workplace/gc-router/bin/jobctl`

**Interfaces:**

```python
class PromotionState(str, Enum):
    BASELINE_PENDING = "baseline_pending"
    HUMAN_INCREMENT_1 = "human_increment_1"
    HUMAN_INCREMENT_2 = "human_increment_2"
    HUMAN_INCREMENT_3 = "human_increment_3"
    AUTO_ACTIVE = "auto_active"
    KILLED = "killed"


def evaluate_candidate(
    packet: VerifiedEvidencePacket,
    state: PromotionLedger,
    policy: PromotionPolicy,
) -> PromotionDecision: ...
```

`tests/test_promotion.py` defines test-only factories with these exact
signatures: `baseline_promoted(version: str) -> PromotionLedger`,
`clean_packet(version: str) -> VerifiedEvidencePacket`,
`policy() -> PromotionPolicy`, `one_clean_increment() -> PromotionLedger`,
`packet_with(defect: str) -> VerifiedEvidencePacket`,
`record_failure(packet, ledger) -> PromotionLedger`,
`auto_active_ledger() -> PromotionLedger`, and
`protected_policy() -> PromotionPolicy`. The helpers build public immutable
types; they do not bypass production validation.

1. Write table-driven failing tests for the full sequence:

   ```python
   def test_three_clean_human_promotions_activate_automation():
       ledger = baseline_promoted("2.0.0")
       for version in ("2.0.1", "2.0.2", "2.0.3"):
           decision = evaluate_candidate(clean_packet(version), ledger, policy())
           ledger = record_human_promotion(decision, ledger, actor="vishnu")
       assert ledger.state is PromotionState.AUTO_ACTIVE


   @pytest.mark.parametrize("defect", [
       "rollback", "high_finding", "heldout_regression", "canary_failure"
   ])
   def test_dirty_release_resets_calibration(defect):
       ledger = one_clean_increment()
       ledger = record_failure(packet_with(defect), ledger)
       assert ledger.clean_increment_count == 0
       assert ledger.state is PromotionState.HUMAN_INCREMENT_1
   ```

2. Add negative tests for skipping a calibration step, duplicate version,
   non-monotonic base, stale verifier, same-release verifier change,
   self-authored eligibility, and a candidate policy hash that differs from the
   previously ratified policy.

3. Run and verify RED:

   ```bash
   cd "$HOME/workplace/gc-router"
   python3 -m pytest tests/test_promotion.py -q
   ```

4. Implement immutable decision and ledger types. Store append-only decisions
   under the protected Switchboard state root and derive the current state by
   replay. Use a file lock for append and reject a stale expected revision.

5. Add `jobctl promotion inspect|evaluate|human-promote|activate-automation`.
   `human-promote` records the authenticated local operator and packet digest;
   it cannot accept a raw candidate path in place of protected verification.

6. Rerun the focused tests and verify GREEN.

### Task 2: Implement the local publisher and rollback adapter

**Files:**

- Create: `$HOME/workplace/gc-router/gc_router/switchboard/publisher.py`
- Create: `$HOME/workplace/gc-router/tests/test_publisher.py`
- Modify: `$HOME/workplace/gc-router/bin/jobctl`

**Interfaces:**

```python
class Publisher(Protocol):
    def canary(self, release: VerifiedRelease, policy: CanaryPolicy) -> CanaryReceipt: ...
    def promote(self, release: VerifiedRelease, expected_active: str) -> PublishReceipt: ...
    def rollback(self, receipt: PublishReceipt) -> RollbackReceipt: ...
```

The local adapter stores immutable release bundles under
`$XDG_STATE_HOME/deja-vu/releases/<digest>/` and atomically replaces
`$XDG_STATE_HOME/deja-vu/active-release.json`. It never follows candidate-
controlled symlinks.

1. Write failing tests proving compare-and-swap promotion, idempotent replay,
   concurrent-writer rejection, no-follow bundle validation, and exact rollback
   to the prior digest.

2. Add a crash test that interrupts after staging the new active record but
   before replacement; the previous active release must remain readable.

3. Run and verify RED:

   ```bash
   python3 -m pytest tests/test_publisher.py -q
   ```

4. Implement immutable bundles, `0600` protected records, directory-descriptor
   no-follow reads, temporary-file `fsync`, and atomic `os.replace`. A publish
   receipt records previous/new digest, policy, verifier, actor, and timestamp.

5. Add `jobctl promotion promote|rollback`. Neither command accepts a packet
   until `promotion evaluate` has produced a current eligible decision.

6. Rerun publisher and promotion tests together.

### Task 3: Add canary policy, high-risk batches, and kill switch

**Files:**

- Modify: `$HOME/workplace/gc-router/gc_router/switchboard/promotion.py`
- Modify: `$HOME/workplace/gc-router/gc_router/switchboard/publisher.py`
- Modify: `$HOME/workplace/gc-router/tests/test_promotion.py`
- Modify: `$HOME/workplace/gc-router/tests/test_publisher.py`
- Modify: `$HOME/workplace/gc-router/policy/deja-vu-promotion-policy.json`

1. Write failing tests for standard and high-risk canaries. The high-risk case
   requires every standard observation plus interaction-evaluation evidence,
   a longer declared observation window, and an exercised rollback receipt.

2. Write a failing test proving policy is selected by the candidate's base
   release, not by files included in the candidate:

   ```python
   def test_candidate_cannot_weaken_its_high_risk_canary():
       candidate = high_risk_packet(policy_override={"window_seconds": 0})
       with pytest.raises(PolicyMismatch):
           evaluate_candidate(candidate, auto_active_ledger(), protected_policy())
   ```

3. Write kill-switch tests proving an active kill switch blocks new canaries
   and promotions but does not block inspection or rollback.

4. Implement `jobctl promotion kill-switch set|clear|show`. Set and clear are
   authenticated local-operator actions with append-only receipts. No candidate
   input can clear the switch.

5. Run all promotion and publisher tests.

### Task 4: Connect Deja evidence and Vishnu City workflow

**Files:**

- Modify: `$HOME/vishnu-city/formulas/deja-vu-release.toml`
- Create: `tests/fixtures/releases/calibration-sequence.json`
- Create: `tests/test_release_sequence.py`
- Modify: `contracts/module-contracts.json`

1. Add a deterministic Deja fixture containing v2.0 plus three incremental
   releases and a fourth automation-eligible release. The fixture references
   protected verifier and publisher receipts by digest; it does not copy their
   authority claims into candidate data.

2. Write a release-sequence test that replays the fixture and asserts the exact
   state after every release.

3. Add Vishnu City formula steps in dependency order: build evidence -> external
   verify -> canary -> promotion decision -> human gate during calibration or
   automatic local promotion after activation -> monitor -> rollback on
   declared failure.

4. Ensure the formula's promotion steps are deterministic protected commands.
   Model workers may interpret evidence but cannot call publisher commands or
   resolve human gates.

5. Run the Deja sequence test and validate the resolved city formula.

### Task 5: Full verification and adversarial review

1. In `gc-router`, run:

   ```bash
   python3 -m pytest tests/test_promotion.py tests/test_publisher.py -q
   make test
   ```

2. In Deja Vu, run:

   ```bash
   python3 -m pytest -q
   python3 evals/run_evals.py
   python3 scripts/doctor.py
   bash scripts/sanitize_check.sh
   bd lint
   bd doctor --check=conventions
   ```

3. Run a disposable local sequence: promote v2.0, record three human
   incremental promotions, automatically promote release four, induce a canary
   failure on release five, and prove the active record returns to release four.

4. Obtain fresh Fable reviews for every changed executable module in both
   repositories. Any unresolved material finding blocks completion.

5. Record packet, verifier, canary, promotion, active-release, and rollback
   digests on `deja-vu-p3.6.4`, then close only after independent replay matches.

## Completion gate

Phase 3 is complete only when the entire calibration and automation sequence
replays deterministically, the high-risk and self-weakening negative tests pass,
rollback restores the exact prior release, the kill switch works, and all
current executable modules have terminal Fable evidence.
