import React from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { Shell } from "./Workspace";

vi.mock("./WorkspaceContext", () => ({
  useWorkspace: () => ({
    user: { username: "instructor", display_name: "Test Instructor" },
    professor: true,
    items: [],
    refresh: vi.fn(),
  }),
  WorkspaceProvider: ({ children }) => children,
}));

it("retains the approved header toggle and sidebar icon structure", () => {
  render(
    <MemoryRouter initialEntries={["/professor"]}>
      <Shell />
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("button", { name: "Student", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  expect(
    screen.getByRole("button", { name: "Professor", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
  const overview = within(nav).getByRole("link", { name: "Overview" });
  expect(overview.querySelector("svg")).not.toBeNull();
  expect(
    within(nav).getByRole("link", { name: "Course management" }),
  ).toHaveAttribute("href", "/professor/courses");
  expect(
    screen.getAllByRole("link", { name: "Course management", exact: true }),
  ).toHaveLength(3);
  expect(
    screen.getByRole("button", { name: "Sign out" }),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText("Professor account menu"),
  ).toBeInTheDocument();
  expect(screen.getByText("Fall 2026")).toBeInTheDocument();
});

it("uses the exact approved CSS files without style edits", () => {
  const root = resolve(process.cwd(), "..");
  for (const [approved, integrated] of [
    [
      "platform_frontend/src/workspace/__fixtures__/approved-workspace.css",
      "platform_frontend/src/workspace/workspace.css",
    ],
    [
      "platform_frontend/src/workspace/__fixtures__/approved-base.css",
      "platform_frontend/src/workspace/approved-base.css",
    ],
    [
      "platform_frontend/src/workspace/__fixtures__/approved-sdl.css",
      "platform_frontend/src/workspace/approved-sdl.css",
    ],
    [
      "platform_frontend/src/workspace/__fixtures__/approved-charlotte-theme.css",
      "platform_frontend/shared/charlotte-theme.css",
    ],
  ])
    expect(readFileSync(resolve(root, integrated))).toEqual(
      readFileSync(resolve(root, approved)),
    );
});
