---
status: resolved
trigger: "Completed Reflections transcript reports Missing Topics: none and Misconceptions: none despite repeated incomplete or incorrect student answers before correction."
created: 2026-10-23
updated: 2026-10-23T12:00:00-04:00
---

## Symptoms

- expected_behavior: The completed-session evaluation should identify required topics the student did not independently demonstrate and misconceptions or misunderstandings evidenced anywhere in the learning trajectory, even if the tutor later supplied a correction and the student repeated it.
- actual_behavior: The evaluator reports every required topic as covered and both missing_topics and misconceptions as empty after multiple inadequate answers and tutor corrections.
- error_messages: None; this is a silent analytics-quality failure.
- timeline: Observed in the pasted completed activity; whether older versions behaved differently is unknown.
- reproduction: Complete a topic-based session by first answering inadequately, receive the tutor's correction, then repeat the correction. End the session and inspect Missing Topics and Misconceptions.

## Current Focus

- hypothesis: The final evaluator loses deterministic per-turn failure evidence because evaluate_session omits state.wrong_subtopics, and evaluation validation trusts empty model arrays.
- test: Pass wrong_subtopics through the final prompt and reconcile them into missing_topics/misconceptions after model parsing.
- expecting: The supplied trajectory regression will pass and existing reflection tests will remain green.
- next_action: deploy the changed Reflections backend, then repeat the reported workflow to establish live-environment proof
- bug_class: Bohrbug
- reasoning_checkpoint:
    hypothesis: evaluate_session discards state.wrong_subtopics, so the final LLM sees only a transcript in which tutor corrections and student repetitions look like independent mastery; _validate then accepts contradictory empty arrays.
    confirming_evidence:
      - evaluate_reply appends inadequate topics to wrong_subtopics, but evaluate_session passes only transcript and config.
      - format_transcript serializes only speaker text and omits adequate=false and topic metadata.
      - The regression fails because build_evaluation_prompt and _validate accept no wrong_subtopics evidence.
    falsification_test: If passing a known wrong_subtopic to prompt/validation still permits empty missing_topics and misconceptions, this hypothesis is wrong.
    fix_rationale: Preserve the already-recorded per-turn evidence through the evaluation boundary, instruct the model how to interpret corrected repetitions, and deterministically prevent empty analytics from erasing known struggle.
    blind_spots: A topic can be genuinely mastered later without copying; current state records that it was previously missed but not the semantic independence of the recovery.
    candidate_causes:
      - code: evaluation drops wrong_subtopics and validation trusts empty arrays.
      - data: transcript lacks adequacy/topic annotations and cannot expose the learning trajectory by itself.
    and_gate: yes; the failure requires both loss of structured trajectory evidence and a final model response that classifies the corrected transcript as fully covered.
- tdd_checkpoint:

## Evidence

- timestamp: 2026-10-23T12:00:00-04:00
  checked: .planning/debug/knowledge-base.md
  found: No project debug knowledge base exists.
  implication: No known-pattern resolution is available; investigate directly.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: reflections-app/backend/app/agents/nodes/evaluator.py and state.py
  found: Per-turn inadequate answers are recorded in state.wrong_subtopics, but evaluate_session passes only transcript and module config to evaluate_transcript.
  implication: The strongest deterministic evidence of struggle is discarded before final analytics.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: reflections-app/backend/app/agents/nodes/session.py
  found: The final transcript contains only USER and ASSISTANT text; it omits question/topic identity and the parsed adequate boolean.
  implication: The final evaluator cannot reliably distinguish an independently demonstrated answer from a student repeating tutor-provided correction.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: reflections-app/backend/app/services/prompts.py and evaluation.py
  found: The prompt defines missing topics only as required topics not discussed, and _validate defaults/accepts empty arrays without reconciling known wrong_subtopics.
  implication: A final correct repetition can be treated as coverage and empty analytics are accepted despite recorded earlier failures.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: focused regression tests in tests/test_evaluation.py
  found: Both tests fail before the fix because _validate and build_evaluation_prompt reject wrong_subtopics as an argument.
  implication: The regression directly reproduces the missing trajectory-evidence contract.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: mutation and revert/reconfirm guardrail
  found: Replacing trajectory reconciliation with an empty iteration made the focused regression fail; restoring the fix made it pass.
  implication: The regression detects removal of the root-cause fix and this change causes the corrected behavior.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: complete reflections backend test suite
  found: 6 tests passed and 2 database-backed tests skipped because TEST_DATABASE_URL is not configured; compileall completed successfully.
  implication: Unit and provider-adjacent behavior remains green, while database integration remains not run in this environment.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: service-level completed-session reproduction with an evaluator model returning empty gap arrays
  found: evaluate_transcript now returns and persists String immutability in missing_topics plus an earlier-incomplete-answer entry in misconceptions; the generated prompt includes the recorded inadequate topic and independent-demonstration rules.
  implication: The original silent analytics failure is reproduced and corrected across prompt generation, model parsing, validation, and persistence without relying on hosted UI access.
- timestamp: 2026-10-23T12:00:00-04:00
  checked: final reflections backend suite after service-level reproduction was added
  found: 7 tests passed and 2 database-backed tests skipped; compileall passed.
  implication: The fix is locally verified; database-backed and deployed behavior remain explicit validation boundaries.

## Eliminated

## Resolution

- root_cause: Final evaluation discarded state.wrong_subtopics and provided only an unannotated transcript to the evaluator; the vague prompt treated discussed/corrected content as covered, and validation accepted empty missing_topics/misconceptions without reconciling known inadequate turns.
- fix: Pass wrong_subtopics into final evaluation, add explicit learning-trajectory semantics to the evaluator prompt, and deterministically reconcile known inadequate topics into missing_topics and misconceptions.
- oracle_type: specified
- verification:
    target_test: {result: pass}
    mutation_check: {result: pass, mutant_killed: true, reason_if_skipped: "Stryker is not applicable to this Python project; a scoped manual mutant at the reconciliation loop was killed."}
    no_op_deletion: {result: pass, deletion_justified_by_rca: false}
    adjacent_tests: {result: pass, suites_run: ["reflections-app/backend/tests (7 passed, 2 database-backed skipped)", "python compileall"]}
    revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
    guardrail_verdict: accepted
- validation_boundary: Local service behavior is verified. Database-backed integration was not run because TEST_DATABASE_URL is unavailable, and no deployment or hosted UI was changed or tested.
- files_changed:
    - reflections-app/backend/app/agents/nodes/evaluator.py
    - reflections-app/backend/app/services/evaluation.py
    - reflections-app/backend/app/services/prompts.py
    - reflections-app/backend/tests/test_evaluation.py
