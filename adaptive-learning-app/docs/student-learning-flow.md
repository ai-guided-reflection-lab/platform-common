# Student learning flow

The backend owns progression. The browser displays the returned attempt and sends the next student action; it does not decide difficulty, mastery, or the next phase.

## 1. Diagnostic selection

Every student receives the same deterministic five-question diagnostic for a given assignment:

- 2 foundational questions
- 2 application questions
- 1 challenge question

If the authored bank has more questions, the backend selects the first required number at each level and fills any missing slots from the remaining authored questions. This keeps the diagnostic reproducible and makes two students' placement results comparable.

## 2. Placement

Answers are evaluated per learning objective. Difficulty controls the evidence weight:

| Difficulty | Weight |
| --- | ---: |
| Foundational | 1 |
| Application | 2 |
| Challenge | 3 |

For each objective, the backend divides earned weight by available weight:

- below 50%: `foundational`
- 50% through 84%: `standard`
- 85% or above: `accelerated`

An assignment-level path is also stored for display. It is the most supportive path required by any objective. The per-objective paths, stored in `learning_state.objective_paths`, control the actual questions.

## 3. Per-objective flow

### Foundational

1. Show a short explanation and worked example.
2. Ask the authored foundational practice questions in order.
3. Ask the objective's independent demonstration question.

### Standard

1. Ask an authored standard practice question.
2. Ask the objective's independent demonstration question.

### Accelerated

1. Ask an authored challenge question as the independent demonstration.

Practice responses never establish mastery. They only prepare the student for the independent demonstration.

## 4. Response decisions

The assessor returns a score, a `demonstrated` decision, and a rationale against the objective's success criteria.

- Demonstrated: advance to the next objective using that objective's diagnostic path.
- First unsuccessful demonstration: provide formative feedback and retry.
- Second unsuccessful demonstration: return to foundational explanation, example, and practice.
- Successful remediation practice: return to an independent demonstration; do not mark mastery from supported practice.

After every required objective is independently demonstrated, the attempt enters `required_task`. Submitting that task completes the assignment.

## 5. Persisted state

The database stores the current phase, objective index, quiz result, assignment-level path, and a JSON learning state containing:

- `objective_paths`: diagnostic placement for every objective
- `current_path`: placement for the current objective
- `mode`: `practice`, `demonstration`, or `complete`
- `practice_level`: the active practice bank, when applicable
- `practice_index`: position in that bank
- `failures`: unsuccessful independent demonstrations for the current objective

Because this state is persisted after every response, refreshing or reopening the assignment resumes the same learning decision.
