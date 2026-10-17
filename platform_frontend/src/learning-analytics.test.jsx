import React from "react";
import { expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClassLearningAnalytics, StudentConceptAnalytics } from "../../adaptive-learning-app/instructor-app/src/main.jsx";

const concept = { objective_id: "ARCH", objective_title: "Architecture", concept: "MVC", status: "needs_support", independent_checks: 0,
  assisted_responses: 1, next_action: "Explain component responsibilities, then check a fresh case.",
  diagnostic_correct: 0, diagnostic_total: 1, confident_errors: 1, earlier_misconceptions: ["Views own business logic"],
  latest_response: "My latest reasoning", latest_feedback: "The controller's responsibility is missing", assessment_source: "ai" };

test("class analytics filters students needing support and opens their evidence", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  render(<ClassLearningAnalytics progress={[
    { student_id: "a", display_name: "Alex", attempt_id: "attempt", concept_analytics: [concept] },
    { student_id: "b", display_name: "Jordan", attempt_id: null, concept_analytics: [{ ...concept, status: "not_assessed" }] },
  ]} onOpen={open} />);
  const table = screen.getByRole("table");
  expect(within(table).getByRole("rowheader", { name: /MVC/ })).toBeVisible();
  await user.selectOptions(screen.getByRole("combobox", { name: "Show students" }), "needs_support");
  expect(screen.queryByRole("button", { name: /Jordan/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Alex/ }));
  expect(open).toHaveBeenCalledWith("a");
});

test("student concept analytics shows evidence, recommended next action and reflections", async () => {
  render(<StudentConceptAnalytics concepts={[concept]} reflections={[{ content: "I can now explain the controller's role." }]} />);
  expect(screen.getByText("Needs support")).toBeVisible();
  expect(screen.getByText(/0\/2 independent checks/)).toBeVisible();
  expect(screen.getByText(/Explain component responsibilities/)).toBeVisible();
  await userEvent.setup().click(screen.getByText("View supporting evidence"));
  expect(screen.getByText("My latest reasoning")).toBeVisible();
  expect(screen.getByText(/Views own business logic/)).toBeVisible();
  expect(screen.getByText("I can now explain the controller's role.")).toBeVisible();
});

test("grader outage appears as unavailable assessment rather than a student error", () => {
  render(<StudentConceptAnalytics concepts={[{ ...concept, status: "not_assessed", grader_issue: "Provider unavailable" }]} />);
  expect(screen.getByText("Not yet assessed")).toBeVisible();
  expect(screen.getByText(/This is not a student error/)).toBeVisible();
});
