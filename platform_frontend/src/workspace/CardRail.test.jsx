import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import CardRail from "./CardRail";

it("shows overflow navigation and scrolls one card without hiding items", () => {
  render(
    <CardRail label="New assignments">
      {[1, 2, 3, 4].map((n) => (
        <a key={n} href={`#${n}`}>
          Assignment {n}
        </a>
      ))}
    </CardRail>,
  );
  const track = screen.getByRole("list", { name: "New assignments" });
  Object.defineProperties(track, {
    clientWidth: { value: 1000 },
    scrollWidth: { value: 1300 },
    scrollLeft: { value: 0, writable: true },
  });
  track.firstElementChild.getBoundingClientRect = () => ({ width: 300 });
  track.scrollBy = vi.fn();
  act(() => window.dispatchEvent(new Event("resize")));
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
  expect(
    screen.queryByRole("button", { name: "Previous New assignments" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next New assignments" }));
  expect(track.scrollBy).toHaveBeenCalledWith({
    left: 316,
    behavior: "smooth",
  });
  track.scrollLeft = 300;
  fireEvent.scroll(track);
  expect(
    screen.getByRole("button", { name: "Previous New assignments" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Next New assignments" }),
  ).not.toBeInTheDocument();
});

it("keeps arrows hidden when all cards fit", () => {
  render(
    <CardRail label="Your courses">
      <a href="#course">One course</a>
    </CardRail>,
  );
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "One course" })).toBeVisible();
});
