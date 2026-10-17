import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LessonWorkspace from "../../adaptive-learning-app/student-app/src/LessonWorkspace.jsx";
import { api } from "../../adaptive-learning-app/student-app/src/api.js";

vi.mock("../../adaptive-learning-app/student-app/src/api.js", () => ({ api: vi.fn() }));

const question = {
  id: "Q1", difficulty: "foundational", question: "Choose a requirement.",
  options: ["An action", "A constraint", "An example", "A goal"],
};
const lesson = { learning_plan: { topic: "Requirements", study_resources: [] } };
const endpoint = "/student/assignments/lesson/learning-turn";

function attempt(stage, extra = {}) {
  return {
    messages: [], objective_progress: [],
    learning_state: { stage, quiz_index: 0, choices: [], current_question: question, ...extra },
  };
}

beforeEach(() => api.mockReset());

test("familiarity buttons submit the selected preparation preference", async () => {
  const user = await openLesson(attempt("welcome"));
  expect(screen.getByRole("button", { name: "I'm completely new", exact: true })).toBeVisible();
  expect(screen.getByRole("button", { name: "I know some of this", exact: true })).toBeVisible();
  api.mockResolvedValueOnce(attempt("study_resources", { familiarity: "comfortable" }));
  await user.click(screen.getByRole("button", { name: "I'm comfortable with this topic", exact: true }));
  expect(submittedTurn().content).toBe("I'm comfortable with this topic");
  await screen.findByRole("button", { name: "Quick recap" });
  expect(screen.getByRole("button", { name: /I'm ready/ })).toBeVisible();
});

test("approved readings remain accessible during practice and checks show concept progress", async () => {
  api.mockResolvedValueOnce({ learning_plan: { topic: "Requirements", study_resources: [
    { url: "https://example.edu/read", title: "Approved reading", description: "Learn to classify requirements", focus: "Classification" },
  ] } }).mockResolvedValueOnce(attempt("adaptive_learning", {
    diagnostic_complete: true, target_concept: "Classification", target_objective: "REQ", concept_checks: { REQ: { Classification: 1 } },
  }));
  render(<LessonWorkspace assignmentId="lesson" onBack={vi.fn()} />);
  await screen.findByRole("heading", { name: "Requirements" });
  await userEvent.setup().click(screen.getByText("Approved readings", { selector: "summary" }));
  expect(screen.getByRole("link", { name: /Approved reading/ })).toHaveAttribute("href", "https://example.edu/read");
  expect(screen.getByText("Independent checks: 1 of 2")).toBeVisible();
});


async function openLesson(initial) {
  api.mockResolvedValueOnce(lesson).mockResolvedValueOnce(initial);
  render(<LessonWorkspace assignmentId="lesson" onBack={vi.fn()} />);
  await screen.findByRole("heading", { name: "Requirements" });
  expect(api.mock.calls.slice(0, 2)).toEqual([
    ["/student/assignments/lesson"],
    ["/student/assignments/lesson/start", { method: "POST" }],
  ]);
  return userEvent.setup();
}

function submittedTurn(callIndex = 2) {
  const [path, options] = api.mock.calls[callIndex];
  expect(path).toBe(endpoint);
  expect(options.method).toBe("POST");
  return JSON.parse(options.body);
}

test("Record answer and Continue preserve the recorded choice and payload", async () => {
  const user = await openLesson(attempt("diagnostic_quiz"));
  api.mockResolvedValueOnce(attempt("diagnostic_quiz", { metadata_requested: true, recorded_option: 1 }));
  await user.click(screen.getByRole("radio", { name: "B. A constraint" }));
  await user.click(screen.getByRole("button", { name: "Record answer" }));
  await screen.findByRole("button", { name: "Continue", exact: true });
  expect(submittedTurn()).toMatchObject({ action: "answer", question_id: "Q1", option_index: 1 });
  expect(screen.getByRole("radio", { name: "B. A constraint" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "B. A constraint" })).toBeDisabled();
  api.mockResolvedValueOnce(attempt("learning_choice"));
  await user.selectOptions(screen.getByRole("combobox"), "high");
  await user.click(screen.getByRole("button", { name: "Continue", exact: true }));
  await waitFor(() => expect(api).toHaveBeenCalledTimes(4));
  expect(submittedTurn(3)).toMatchObject({ action: "continue", question_id: "Q1", confidence: "high" });
  expect(submittedTurn(3)).not.toHaveProperty("option_index");
  expect(submittedTurn(3).turn_id).not.toBe(submittedTurn().turn_id);
});

test("practice Send submits trimmed content and displays the returned result", async () => {
  const initial = attempt("adaptive_learning");
  delete initial.learning_state.current_question;
  const user = await openLesson(initial);
  const result = attempt("reflection");
  result.messages = [{ id: "feedback", role: "assistant", content: "Your reasoning addresses the rubric." }];
  api.mockResolvedValueOnce(result);
  await user.type(screen.getByRole("textbox", { name: "Your reply" }), "  This is my practice reasoning.  ");
  await user.click(screen.getByRole("button", { name: "Send", exact: true }));
  await screen.findByText("Your reasoning addresses the rubric.");
  expect(submittedTurn()).toEqual({ content: "This is my practice reasoning.", turn_id: expect.any(String) });
  expect(screen.getByRole("textbox", { name: "Your reply" })).toHaveValue("");
});

test("Pause and Resume keep the saved activity and restore the composer", async () => {
  const user = await openLesson(attempt("adaptive_learning"));
  api.mockResolvedValueOnce(attempt("paused"));
  await user.click(screen.getByRole("button", { name: "Pause & save" }));
  await screen.findByText("Paused · progress saved");
  expect(submittedTurn()).toMatchObject({ action: "pause" });
  expect(screen.queryByRole("textbox", { name: "Your reply" })).not.toBeInTheDocument();
  api.mockResolvedValueOnce(attempt("adaptive_learning"));
  await user.click(screen.getAllByRole("button", { name: "Resume learning" })[0]);
  await screen.findByRole("textbox", { name: "Your reply" });
  expect(submittedTurn(3)).toMatchObject({ action: "resume" });
});

test("Try again resends the identical pending turn and preserves its retry ID", async () => {
  const user = await openLesson(attempt("adaptive_learning"));
  api.mockRejectedValueOnce(new Error("Connection interrupted"));
  await user.type(screen.getByRole("textbox", { name: "Your reply" }), "My answer");
  await user.click(screen.getByRole("button", { name: "Send", exact: true }));
  await screen.findByText("Connection interrupted");
  expect(screen.getAllByText("My answer")).toHaveLength(1);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  const original = api.mock.calls[2];
  const result = attempt("adaptive_learning");
  result.messages = [{ id: "saved-answer", role: "student", content: "My answer" }];
  api.mockResolvedValueOnce(result);
  await user.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(api.mock.calls[3]).toEqual(original);
  expect(submittedTurn(3).turn_id).toBe(submittedTurn().turn_id);
  expect(screen.getAllByText("My answer")).toHaveLength(1);
});

test("Enter sends immediately with a thinking indicator, then replaces it with saved history", async () => {
  const user = await openLesson(attempt("adaptive_learning"));
  let resolveTurn;
  api.mockImplementationOnce(() => new Promise(resolve => { resolveTurn = resolve; }));
  await user.type(screen.getByRole("textbox", { name: "Your reply" }), "My independent reasoning");
  await user.keyboard("{Enter}");
  const answer = screen.getByText("My independent reasoning");
  const thinking = screen.getByRole("status");
  expect(thinking).toHaveTextContent("Thinking…");
  expect(answer.closest("article").nextElementSibling).toBe(thinking);
  expect(screen.getByRole("textbox", { name: "Your reply" })).toHaveValue("");
  expect(screen.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  const result = attempt("reflection");
  result.messages = [
    { id: "saved-answer", role: "student", content: "My independent reasoning" },
    { id: "reply", role: "assistant", content: "That explains your decision." },
  ];
  resolveTurn(result);
  await screen.findByText("That explains your decision.");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getAllByText("My independent reasoning")).toHaveLength(1);
});

test("Shift+Enter inserts a new line and empty Enter does not send", async () => {
  const user = await openLesson(attempt("adaptive_learning"));
  const reply = screen.getByRole("textbox", { name: "Your reply" });
  await user.click(reply);
  await user.keyboard("{Enter}");
  expect(reply).toHaveValue("");
  await user.type(reply, "First line");
  await user.keyboard("{Shift>}{Enter}{/Shift}");
  await user.type(reply, "Second line");
  expect(reply).toHaveValue("First line\nSecond line");
  expect(api).toHaveBeenCalledTimes(2);
});

test("assistant paragraphs become separate bubbles while code, lists, student text and citations stay intact", async () => {
  const initial = attempt("adaptive_learning");
  const code = "```python\nfirst()\n\nsecond()\n```";
  initial.messages = [
    { id: "reply", role: "assistant", content: `First idea.\n\nSecond idea.\n\n- Step one\n- Step two\n\n${code}`, sources: [{ document_id: "doc", filename: "notes.pdf" }] },
    { id: "student", role: "student", content: "My first paragraph.\n\nMy second paragraph." },
  ];
  await openLesson(initial);
  const bubbles = screen.getByText("First idea.").closest("article").querySelectorAll("p");
  expect(Array.from(bubbles, bubble => bubble.textContent)).toEqual([
    "First idea.", "Second idea.", "- Step one\n- Step two", code,
  ]);
  expect(screen.getAllByText(/notes\.pdf/)).toHaveLength(1);
  expect(screen.getByText(/My first paragraph/).closest("article").querySelectorAll("p")).toHaveLength(1);
});

test("Try again without a pending turn reloads the lesson and its saved attempt", async () => {
  api.mockRejectedValueOnce(new Error("Cannot open lesson"));
  render(<LessonWorkspace assignmentId="lesson" onBack={vi.fn()} />);
  await screen.findByText("Cannot open lesson");
  api.mockResolvedValueOnce(lesson).mockResolvedValueOnce(attempt("adaptive_learning"));
  await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("heading", { name: "Requirements" });
  expect(api.mock.calls[1]).toEqual(["/student/assignments/lesson"]);
  expect(api.mock.calls[2]).toEqual(["/student/assignments/lesson/start", { method: "POST" }]);
});
