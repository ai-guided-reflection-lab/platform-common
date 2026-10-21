import Markdown from "react-markdown";
export default function SocraticLearningSummary({ summary }) {
  if (!summary) return null;
  return (
    <section
      className="socratic-learning-summary"
      aria-label="Learning summary"
    >
      <h2>Your learning summary</h2>
      <h3>Original question</h3>
      <p>{summary.original_question}</p>
      <h3>Your own summary</h3>
      <p className="student-reflection-text">{summary.student_reflection}</p>
      {summary.demonstrated?.length > 0 && (
        <>
          <h3>What you demonstrated in your answers</h3>
          <ul>
            {summary.demonstrated.map((answer, i) => (
              <li key={i}>{answer}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Tutor feedback</h3>
      <Markdown>{summary.final_comment}</Markdown>
      {summary.misconception_correction && (
        <>
          <h3>Misconception to correct</h3>
          <Markdown>{summary.misconception_correction}</Markdown>
        </>
      )}
      <h3>How the original scenario works out</h3>
      <Markdown>{summary.scenario_wrap_up}</Markdown>
      <h3>Answer to your original question</h3>
      <Markdown>{summary.opening_answer}</Markdown>
    </section>
  );
}
