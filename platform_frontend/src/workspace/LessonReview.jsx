import React from "react";

export default function LessonReview({ plan }) {
  return (
    <div className="workspace-lesson-review">
      <h3>{plan.title}</h3>
      <p>{plan.topic_introduction}</p>
      <p>{plan.introductory_example}</p>
      <h4>Learning objectives</h4>
      {plan.objectives.map((o) => (
        <section key={o.id}>
          <strong>{o.title}</strong>
          <p>{o.description}</p>
          <ul>
            {o.success_criteria.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </section>
      ))}
      <details>
        <summary>Review diagnostic questions and answers</summary>
        {plan.diagnostic_quiz.map((q) => (
          <section key={q.id}>
            <h4>{q.question}</h4>
            <ol>
              {q.options.map((option, i) => (
                <li key={i}>
                  {option}
                  {i === q.correct_index ? " (Correct)" : ""}
                </li>
              ))}
            </ol>
            <p>{q.explanation}</p>
          </section>
        ))}
      </details>
      <details>
        <summary>Review teaching content and practice</summary>
        {plan.learning_assets.map((a) => (
          <section key={a.objective_id}>
            <h4>
              {plan.objectives.find((o) => o.id === a.objective_id)?.title}
            </h4>
            <p>{a.explanation}</p>
            <p>{a.worked_example}</p>
            <p>{a.analogy}</p>
            <p>{a.counterexample}</p>
            {["foundational", "standard", "accelerated"].map((level) => (
              <div key={level}>
                <h4>{level}</h4>
                {a[level].map((q, i) => (
                  <div key={i}>
                    <p>{q.prompt}</p>
                    <small>{q.hint}</small>
                  </div>
                ))}
              </div>
            ))}
          </section>
        ))}
      </details>
      <details>
        <summary>Review final task and readings</summary>
        <h4>{plan.required_task.title}</h4>
        <p>{plan.required_task.description}</p>
        <p>{plan.required_task.submission_prompt}</p>
        {plan.study_resources.map((r) => (
          <p key={r.url}>
            <a href={r.url} target="_blank" rel="noreferrer">
              {r.title}
            </a>{" "}
            · {r.description}
          </p>
        ))}
      </details>
    </div>
  );
}
