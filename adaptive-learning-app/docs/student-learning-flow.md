# Student learning flow

The server owns progression and saves every turn. New lessons use `flow_version: 2`. Existing lessons and attempts keep their previous flow; opening them does not reset student work.

## Professor configuration

A lesson supplies its topic, approved teaching material, introduction and concrete introductory example, objectives, intended difficulty, prerequisites, approved resource links with descriptions and study focus, five prepared MCQs, answer keys, explanations, distractor misconceptions, conceptual hints, reasoning rubrics, and fresh practice banks. The studio lists missing information and blocks publication until the professor reviews and approves it. Runtime code has no subject-specific branches and does not invent absent content.

Quick setup uses a configured AI provider to draft a lesson grounded in the supplied material and objectives. It saves a draft for review; it never publishes automatically. Without a provider, use Advanced setup or the bundled configured examples in `backend/lessons/requirements.json` and `fractions.json`.

## 1. Common introduction

Greet the student by name, name the topic, show the brief approved explanation, concrete example, and learning objectives. Ask: “What feels most unfamiliar about this topic, or are you completely new to it?” Self-report changes emphasis, never placement or ability.

## 2. Supported study

Show professor-approved credible resource links with descriptions and what to focus on. Students can request explanations, examples, analogies, or a smaller task. Available uploaded course notes provide cited support. Students study at their own pace. The **I am done** button and equivalent readiness replies begin the quiz; negative replies such as “not ready” keep study open. Readiness is not evidence of understanding.

## 3. Common diagnostic

Every student assigned the same lesson receives the same prepared five questions, one at a time, with four options each. Their increasing levels address recall, understanding, application, analysis of a misconception, and transfer within the taught material.

Ask for low/medium/high confidence on each answer and a one-sentence explanation on questions 4 and 5. Accept a letter, option text, or an unambiguous natural-language choice. Clarify ambiguous answers. “I don’t know” is allowed. Missing confidence or explanation triggers one request, then students can continue without it; missing information stays marked. Conceptual hints are recorded as assistance. Do not reveal correctness until all five answers have been recorded.

## 4. Evidence-based feedback

Each correct selection earns one point, for a score out of five. Confidence does not alter the score. Reasoning is assessed separately against the configured rubric as sound reasoning, partial understanding, identifiable misconception, or insufficient evidence.

Give the score, concepts supported by the selections, and the specific concept to focus on. Always offer the five learning formats before starting a follow-up. Each choice shows its purpose. Selecting a format removes the menu for the teaching and probing conversation; it returns only at a new learning decision after reflection or when configured cases are exhausted. Foundational gaps get simpler approved explanations and worked examples. Application gaps receive targeted practice. A high-confidence incorrect answer receives a counterexample and fresh check. A correct answer with unclear reasoning receives a probe. Correct but uncertain answers receive affirmation and a fresh confidence-building activity. Strong independent evidence receives an application challenge. Unknown answers offer clarification, hints, a smaller task, or a pause. Disagreement is considered through its reasoning, never penalized by itself.

## 5. Fresh practice, recheck, reflection

The five formats have distinct behavior:

- **A simpler explanation:** explain the selected concept briefly using its approved explanation and hint, then ask a guided question.
- **A worked example:** explain the relevant completed quiz example and why its answer works, then ask the student to reason through a different authored case.
- **Another practice question:** ask an independent fresh application question, give rubric feedback, then probe with a different case.
- **An application challenge:** ask a harder authored transfer case and require a justified decision, followed by a fresh check.
- **A recap:** summarize the selected idea and its essential reasoning, then ask the student to explain it through a fresh case.

Use professor-configured fresh activities and rubrics. After a sound independent response, probe the same concept with a second distinct case before reflection. Supported responses require an independent recheck; incomplete responses receive targeted revision feedback. Asking for help or saying “I don't know” keeps the conversation focused with a smaller step and does not redisplay the format menu. Pause/resume also keeps that menu hidden during active practice. Hints mark an activity as assisted; a sound assisted answer leads to a fresh independent check. Revised misconceptions get specific feedback and another attempt. Merely repeating a revealed quiz answer or an earlier successful response does not establish new understanding. Successful independent evidence updates the current path without rewriting the diagnostic answers or original paths.

After independent understanding is demonstrated, ask: “What can you explain or do now that you couldn’t before?” Save the reflection, then ask: “Would you like another example, a harder challenge, a recap, or to pause here?” Keep the session open. The newest specification replaces the earlier automatic thank-you-and-exit flow.

## Persistence and assessment limits

Persist the stage, current question, immutable lesson snapshot, original answers, confidence, explanations, assistance, gaps, selected follow-up, practice responses, revisions, current paths, and reflections. Pause/resume and page refresh retain progress. Turn identifiers make retries idempotent; concurrent answers are serialized. Students cannot access the snapshot, keys, future quiz questions, or private rubrics before the diagnostic is complete.

A configured AI provider can assess semantics and answer grounded questions. Offline assessment uses professor-authored phrase groups and is approximate; missing local evidence groups require instructor review. It does not substitute invented criteria. The bundled lessons exercise the same engine through configuration alone.

## Verification

Backend acceptance checks cover two substantially different topics; common quizzes; the adaptive cases above; missing metadata; hints; pauses; duplicate and stale requests; original-result preservation; authorization; authoring issues; and retrieved course notes. Build both web applications and check the local service separately. Visual browser verification may be unavailable under the host's browser security policy.
