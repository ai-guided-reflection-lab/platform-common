import React from "react";
import { expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReflectionAssignment from "./ReflectionAssignment";
import { SESSION_KEY } from "./api";

const assignment = { tool: "reflections", title: "Weekly reflection", instructions: "Reflect on your week.", student_config: { module_type: "topic_based" } };
const attempt = { id: "attempt-1", status: "in_progress", messages: [{ role: "assistant", content: "What did you learn?" }], engine_state: { total_questions: 1, question_index: 0 } };
function setup(responses = {}) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ access_token: "test-session" }));
  const fetch = vi.fn(async (url, opts = {}) => {
    const path = url.replace("/api/platform/assignments/a", "");
    const value = { "": assignment, "/start": attempt, ...responses }[path];
    if (value === undefined) throw new Error(`Unexpected endpoint ${url}`);
    const data = typeof value === "function" ? value(opts) : value;
    return { ok: !data.error, status: data.error ? 502 : 200, json: async () => data.error ? { detail: data.error } : data };
  });
  vi.stubGlobal("fetch", fetch);
  render(<ReflectionAssignment assignmentId="a" />);
  return fetch;
}

test("assigned chat resumes, retries messages with the same key, and saves evaluation", async () => {
  let calls = 0;
  const replied = { ...attempt, engine_state: { total_questions: 1, question_index: 1, is_bonus_phase: true }, messages: [...attempt.messages, { role: "user", content: "Testing" }, { role: "assistant", content: "Let's explore further." }] };
  const fetch = setup({
    "/messages": () => ++calls === 1 ? { error: "Please retry." } : replied,
    "/complete": { ...replied, status: "completed", result: { evaluation: { reflection_depth_score: 4, confidence_level: 3, engagement_score: 5 } } },
  });
  const user = userEvent.setup();
  expect(await screen.findByText("What did you learn?")).toBeInTheDocument();
  expect(screen.queryByText("Student ID")).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "End Session" })).toBeDisabled();
  await user.type(screen.getByLabelText("Your message"), "Testing");
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Please retry");
  expect(screen.getByLabelText("Your message")).toHaveValue("Testing");
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Bonus Questions")).toBeInTheDocument();
  const requests = fetch.mock.calls.filter(([url]) => url.endsWith("/messages"));
  expect(JSON.parse(requests[0][1].body).request_id).toBe(JSON.parse(requests[1][1].body).request_id);
  expect(requests[0][1].headers.Authorization).toBe("Bearer test-session");
  await user.click(screen.getByRole("button", { name: "End Session" }));
  expect(await screen.findByRole("heading", { name: "Session Complete" })).toBeInTheDocument();
  expect(screen.getByLabelText("Saved transcript")).toHaveTextContent("Testing");
  expect(screen.queryByRole("button", { name: "New Session" })).not.toBeInTheDocument();
});

test("milestone assignment uses its prompt and displays persisted similar experiences", async () => {
  const fetch = setup({
    "": { ...assignment, student_config: { module_type: "milestone_based", milestone_prompt: "Describe a challenge." } },
    "/messages": { ...attempt, status: "completed", result: { similar: [{ name: "Peer", cos_score: 0.82, challenge: "Time management", solution: "Plan the week" }] } },
  });
  const user = userEvent.setup();
  expect(await screen.findByText("Describe a challenge.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Your Reflection"), "I struggled with time management.");
  await user.click(screen.getByRole("button", { name: "Submit Reflection" }));
  expect(await screen.findByText("Plan the week")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New Reflection" })).not.toBeInTheDocument();
  expect(fetch.mock.calls.every(([url]) => url.startsWith("/api/platform/assignments/a"))).toBe(true);
});

test("start failure offers retry and completed attempts open read-only", async () => {
  let calls = 0;
  setup({ "/start": () => ++calls === 1 ? { error: "Reflection engine unavailable." } : { ...attempt, status: "completed", result: { evaluation: { reflection_depth_score: 4 } } } });
  const user = userEvent.setup();
  expect(await screen.findByRole("alert")).toHaveTextContent("Reflection engine unavailable");
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("heading", { name: "Session Complete" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Your message")).not.toBeInTheDocument();
});

test("failed completion preserves the chat and allows a manual retry", async () => {
  setup({ "/start": { ...attempt, engine_state: { is_bonus_phase: true } }, "/complete": { error: "Evaluation unavailable. Retry." } });
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "End Session" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Evaluation unavailable");
  expect(screen.getByRole("button", { name: "End Session" })).toBeEnabled();
  expect(screen.getByText("What did you learn?")).toBeInTheDocument();
});

test("a non-Reflections assignment never starts through the Reflections entry", async () => {
  const fetch = setup({ "": { ...assignment, tool: "socratic" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("does not use Reflections");
  expect(fetch).toHaveBeenCalledTimes(1);
});
