import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import StudentDashboardView from "./StudentDashboardView";

it("counts actual assignments and filters the card rows by assignment or course", () => {
  const assignments = [1, 2, 3, 4].map((id) => ({
    id: String(id),
    title: `Assignment ${id}`,
    chat: "Socratic",
    course: id === 4 ? "Networks" : "Software Engineering",
    course_code: "SE 101",
    progress: "not_started",
  }));
  render(
    <MemoryRouter>
      <StudentDashboardView
        firstName="Alex"
        assignments={assignments}
        courses={[]}
        assignmentPath={(a) => `/student/assignments/${a.id}`}
        joinCourse={<p>Join a course</p>}
      />
    </MemoryRouter>,
  );
  const group = screen.getByRole("region", { name: "New assignments" });
  expect(
    within(group).getByRole("heading", { name: "New 4" }),
  ).toBeInTheDocument();
  expect(within(group).getAllByRole("link")).toHaveLength(4);
  fireEvent.change(
    screen.getByRole("textbox", { name: "Search assignments" }),
    { target: { value: "Networks" } },
  );
  expect(
    within(group).getByRole("heading", { name: "New 1" }),
  ).toBeInTheDocument();
  expect(within(group).getAllByRole("link")).toHaveLength(1);
  expect(within(group).getByText("Assignment 4")).toBeInTheDocument();
  expect(screen.queryByText("View all")).not.toBeInTheDocument();
});

it("keeps the course-code join flow available through the compact course action", () => {
  render(
    <MemoryRouter>
      <StudentDashboardView
        firstName="Alex"
        assignments={[]}
        courses={[
          {
            id: "course-1",
            code: "SE 101",
            title: "Software Engineering",
            activities: [],
          },
        ]}
        assignmentPath={(a) => `/student/assignments/${a.id}`}
        compactJoin={
          <label>
            Course code
            <input />
          </label>
        }
      />
    </MemoryRouter>,
  );
  const button = screen.getByRole("button", { name: /Join another course/ });
  expect(screen.queryByLabelText("Course code")).not.toBeInTheDocument();
  fireEvent.click(button);
  expect(screen.queryByRole("button", { name: /Join another course/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Course code").closest(".p-section-title")).not.toBeNull();
  expect(screen.getByLabelText("Course code")).toHaveFocus();
});
