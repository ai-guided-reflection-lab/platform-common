import React from "react";
import { test, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import StudentAssignmentBrowser from "./StudentAssignmentBrowser";
const items = [
  { title: "Fresh activity", progress: "not_started" },
  { title: "Started activity", progress: "in_progress" },
  { title: "Finished activity", progress: "completed" },
];
const renderItems = (rows, view) => (
  <div data-testid="results" data-view={view}>
    {rows.map((item) => <p key={item.title}>{item.title}</p>)}
  </div>
);

test("dashboard separates finished work from work left to do", () => {
  const { unmount } = render(<StudentAssignmentBrowser items={items} renderItems={renderItems} />);
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  const left = screen.getByRole("region", { name: /^Left to do/ });
  const finished = screen.getByRole("region", { name: /^Finished/ });
  expect(within(left).getByText("Started activity")).toBeInTheDocument();
  expect(within(left).getByText("Fresh activity")).toBeInTheDocument();
  expect(within(left).queryByText("Finished activity")).not.toBeInTheDocument();
  expect(within(finished).getByText("Finished activity")).toBeInTheDocument();
  expect(within(finished).queryByText("Fresh activity")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Assignment completion" })).toHaveAttribute(
    "aria-valuetext", "1 of 3 assignments finished",
  );
  expect(screen.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "List view" }));
  expect(screen.getAllByTestId("results").every((el) => el.dataset.view === "list")).toBe(true);
  unmount();
  render(<StudentAssignmentBrowser items={items} renderItems={renderItems} />);
  expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
});

test("empty dashboard shows what is left and finished", () => {
  render(<StudentAssignmentBrowser items={[]} renderItems={renderItems} />);
  expect(screen.getAllByRole("region")).toHaveLength(3);
  expect(screen.getByText("You’re all caught up. No assignments left to do.")).toBeInTheDocument();
  expect(screen.getByText("Finished assignments will appear here.")).toBeInTheDocument();
});
