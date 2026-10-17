# Student learning flow

The server owns progression and saves every turn. New lessons use `flow_version: 2`. Existing lessons and attempts keep their previous flow; opening them does not reset student work.

## Professor configuration

A lesson supplies its topic, approved teaching material, introduction and concrete introductory example, objectives, intended difficulty, prerequisites, approved resource links with descriptions and study focus, five prepared MCQs, answer keys, explanations, distractor misconceptions, conceptual hints, reasoning rubrics, and fresh practice banks. The studio lists missing information and blocks publication until the professor reviews and approves it. Runtime code has no subject-specific branches and does not invent absent content.

Quick setup uses a configured AI provider to draft a lesson grounded in the supplied material and objectives. It saves a draft for review; it never publishes automatically. Without a provider, use Advanced setup or the bundled configured examples in `backend/lessons/requirements.json` and `fractions.json`.

Quick setup can begin with an uploaded document or a public article/PDF URL. URL preview reuses the validated downloader and parsing pipeline; the source is then indexed on the draft. The draft review's Edit action opens content, objective, concept, quiz, answer-key, resource, and practice editing. Saving returns to review and clears prior content approval. Renaming a diagnostic concept also updates linked practice names within its objective. Published lessons offer Create editable copy, duplicating source files and indexed chunks into a new draft while preserving the original assignment, access code, and student attempts.

## 1. Common introduction

Greet the student by name, name the topic, show the brief approved explanation, concrete example, and learning objectives. Ask: “What feels most unfamiliar about this topic, or are you completely new to it?” Self-report changes emphasis, never placement or ability.

Offer three familiarity buttons and optional free text. “I'm completely new” gives the introduction and a basic example, marking the first approved reading “Start here.” “I know some of this” asks which configured concept feels unclear and supplies approved support. “I'm comfortable with this topic” offers a quick recap or an immediate quiz. All choices lead to the same diagnostic. Unknown unfamiliar topics prompt clarification rather than invented teaching content.

## 2. Supported study

Show professor-approved credible resource links with descriptions and what to focus on. Students can request explanations, examples, analogies, or a smaller task. Available uploaded course notes provide cited support. Students study at their own pace. The **I am done** button and equivalent readiness replies begin the quiz; negative replies such as “not ready” keep study open. Readiness is not evidence of understanding.

The approved reading links remain accessible in the sidebar during quiz, practice, reflection, and pauses. A matching reading is suggested for the selected study focus when its description, focus, or title supplies matching terms. Comfortable students see the readings as optional revision. Opening every link is never required. The app displays the instructor's actual approved links; it does not invent additional resources to fill three slots.

## 3. Common diagnostic

Every student assigned the same lesson receives the same prepared five questions, one at a time, with four options each. Their increasing levels address recall, understanding, application, analysis of a misconception, and transfer within the taught material.

Ask for low/medium/high confidence on each answer and a one-sentence explanation on questions 4 and 5. Accept a letter, option text, or an unambiguous natural-language choice. Clarify ambiguous answers. “I don’t know” is allowed. Missing confidence or explanation triggers one request, then students can continue without it; missing information stays marked. Conceptual hints are recorded as assistance. Do not reveal correctness until all five answers have been recorded.

## 4. Evidence-based feedback

Each correct selection earns one point, for a score out of five. Confidence does not alter the score. Reasoning is assessed separately against the configured rubric as sound reasoning, partial understanding, identifiable misconception, or insufficient evidence.

Give the score, concepts supported by the selections, and the specific concept to focus on. Always offer the five learning formats before starting a follow-up. Each choice shows its purpose. Selecting a format removes the menu for the teaching and probing conversation; it returns only at a new learning decision after reflection or when configured cases are exhausted. Foundational gaps get simpler approved explanations and worked examples. Application gaps receive targeted practice. A high-confidence incorrect answer receives a counterexample and fresh check. A correct answer with unclear reasoning receives a probe. Correct but uncertain answers receive affirmation and a fresh confidence-building activity. Strong independent evidence receives an application challenge. Unknown answers offer clarification, hints, a smaller task, or a pause. Disagreement is considered through its reasoning, never penalized by itself.

## 5. Fresh practice, recheck, reflection

Diagnostic support precedes the selected format once per question: a confident incorrect answer gets the approved counterexample and a supported fresh case; unclear reasoning on a correct answer gets an independent reasoning probe; a correct low-confidence answer gets explicit affirmation and an independent fresh case. These required checks cannot be bypassed by selecting a challenge or recap. Subsequent format selections use the usual behavior below.

Coverage is tracked per objective and diagnostic concept using distinct independent activity IDs. Each concept requires two successful independent cases. An objective is demonstrated only when every diagnostic concept mapped to it meets this requirement. Saved coverage is reconstructed from practice history, including older records whose authored cases identify their concepts; quiz scores and original diagnostic evidence are preserved. Instructor and student objective status use this coverage rather than a single successful response.

The five formats have distinct behavior:

- **A simpler explanation:** explain the selected concept briefly using its approved explanation and hint, then ask a guided question.
- **A worked example:** explain the relevant completed quiz example and why its answer works, then ask the student to reason through a different authored case.
- **Another practice question:** ask an independent fresh application question, give rubric feedback, then probe with a different case.
- **An application challenge:** ask a harder authored transfer case and require a justified decision, followed by a fresh check.
- **A recap:** summarize the selected idea and its essential reasoning, then ask the student to explain it through a fresh case.

Use professor-configured fresh activities and rubrics. After a sound independent response, probe the same concept with a second distinct case before reflection. Supported responses require an independent recheck; incomplete responses receive targeted revision feedback. Asking for help or saying “I don't know” keeps the conversation focused with a smaller step and does not redisplay the format menu. Pause/resume also keeps that menu hidden during active practice. Hints mark an activity as assisted; a sound assisted answer leads to a fresh independent check. Revised misconceptions get specific feedback and another attempt. Merely repeating a revealed quiz answer or an earlier successful response does not establish new understanding. Successful independent evidence updates the current path without rewriting the diagnostic answers or original paths.

After independent understanding is demonstrated, ask: “What can you explain or do now that you couldn’t before?” Save the reflection, then ask: “Would you like another example, a harder challenge, a recap, or to pause here?” Keep the session open. The newest specification replaces the earlier automatic thank-you-and-exit flow.

## Persistence and assessment limits

Instructor learning analytics summarize coverage by diagnostic concept across the class and each student's latest assessed practice. States are demonstrated, developing, needs support, and not yet assessed. A later assessed gap is shown as current support needs even when earlier successful checks remain in history. Original quiz misconceptions remain visible as historical evidence and do not remain current weaknesses after successful independent practice. Grader failures are displayed separately from student errors. Student details include original diagnostic reasoning, independent/assisted checks, next actions, and saved reflections. Analytics use stored evidence without extra AI calls; Refresh analytics fetches the latest student progress.

After three assessed revisions of one activity (`MAX_PRACTICE_REVISIONS`), show the approved explanation and worked example, record `substantial_support`, reset the independent-check count, and offer an unused independent case for the same concept. If no case remains, show the format choices. Recovery never awards mastery. Existing assistance policies remain unchanged.

Assessment results distinguish `student_insufficient_evidence`, `grader_unavailable`, and `grader_error` through their `status`. Provider failures and invalid responses have no score, do not count as failed revisions, and return to format choices with an explanation. The submitted response remains in practice history; it is not inserted as scored evidence. Correct MCQ selections remain correct when explanation grading is unavailable.

`ADAPTIVE_AI_MODE=demo` explicitly enables approximate local phrase checks. In provider mode, `ADAPTIVE_ALLOW_DEMO_FALLBACK=false` (the default) prevents local grading after a provider failure. Setting it to true is a development/demo opt-in: returned results identify `source=demo_rubric` and `fallback_reason`. Local matching cannot establish arbitrary semantic equivalence. Server diagnostics log error types and HTTP status codes, never provider error bodies or credentials. The health endpoint reports configured runtime mode, not verified provider authentication.

Persist the stage, current question, immutable lesson snapshot, original answers, confidence, explanations, assistance, gaps, selected follow-up, practice responses, revisions, current paths, and reflections. Pause/resume and page refresh retain progress. Turn identifiers make retries idempotent; concurrent answers are serialized. Students cannot access the snapshot, keys, future quiz questions, or private rubrics before the diagnostic is complete.

A configured AI provider can assess semantics and answer grounded questions. Offline assessment uses professor-authored phrase groups and is approximate; missing local evidence groups require instructor review. It does not substitute invented criteria. The bundled lessons exercise the same engine through configuration alone.

## Verification

Backend acceptance checks cover two substantially different topics; common quizzes; the adaptive cases above; missing metadata; hints; pauses; duplicate and stale requests; original-result preservation; authorization; authoring issues; and retrieved course notes. Build both web applications and check the local service separately. Visual browser verification may be unavailable under the host's browser security policy.
