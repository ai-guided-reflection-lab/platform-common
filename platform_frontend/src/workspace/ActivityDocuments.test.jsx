import React, { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ActivityDocuments from "./ActivityDocuments";

const library = Array.from({ length: 8 }, (_, index) => ({
  id: `doc-${index}`,
  name: `Reading ${index + 1}.pdf`,
  size: 1024 * (index + 1),
}));
let motions, reduce, destinationOffscreen;
function Harness({
  upload = async () => [],
  onContinue = vi.fn(),
  onSelection = vi.fn(),
}) {
  const [selected, setSelected] = useState([]);
  return (
    <ActivityDocuments
      library={library}
      selected={selected}
      onChange={(next) => {
        setSelected(next);
        onSelection(next);
      }}
      onUpload={upload}
      onContinue={onContinue}
    />
  );
}
const select = async (user, index) =>
  user.click(
    screen.getByRole("checkbox", {
      name: new RegExp(`Reading ${index + 1}\\.pdf`),
    }),
  );
beforeEach(() => {
  motions = [];
  reduce = false;
  destinationOffscreen = false;
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: reduce,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
    function () {
      const selected = this.classList.contains("ad-selected-row");
      const index = selected
        ? [...this.parentElement.children].indexOf(this)
        : 0;
      const top = selected
        ? (destinationOffscreen ? 1500 : 350) + index * 70
        : 100;
      return {
        top,
        left: 12,
        width: 330,
        height: 50,
        right: 342,
        bottom: top + 50,
        x: 12,
        y: top,
        toJSON() {},
      };
    },
  );
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (frames, options) {
      let finish, reject;
      const animation = {
        finished: new Promise((resolve, fail) => {
          finish = resolve;
          reject = fail;
        }),
        cancel: vi.fn(() => reject(new Error("cancelled"))),
      };
      motions.push({ animation, finish, options, element: this, frames });
      return animation;
    }),
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Create Activity document selection", () => {
  it("flies selections 1–4 downward, then uses a short entrance and retains document references", async () => {
    const user = userEvent.setup(),
      selection = vi.fn();
    render(<Harness onSelection={selection} />);
    for (let index = 0; index < 5; index++) await select(user, index);
    expect(motions.filter((m) => m.options.duration === 330)).toHaveLength(4);
    expect(motions.filter((m) => m.options.duration === 150)).toHaveLength(1);
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(4);
    expect(selection.mock.lastCall[0].map((file) => file.id)).toEqual(
      library.slice(0, 5).map((file) => file.id),
    );
    expect(
      screen.getByRole("button", { name: "Add Documents (5)" }),
    ).toBeEnabled();
    await act(async () =>
      motions
        .filter((m) => m.options.duration === 330)
        .forEach((m) => m.finish()),
    );
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(0);
    expect(
      [...document.querySelectorAll(".ad-selected-row")].every(
        (row) => row.style.visibility === "",
      ),
    ).toBe(true);
  });
  it("uses current selected count, synchronizes removal, and does not delete library documents", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    for (let i = 0; i < 4; i++) await select(user, i);
    await act(async () => motions.forEach((motion) => motion.finish()));
    await user.click(
      screen.getByRole("button", { name: "Remove Reading 2.pdf" }),
    );
    expect(
      screen.getByRole("checkbox", { name: /Reading 2\.pdf/ }),
    ).not.toBeChecked();
    expect(screen.getAllByRole("checkbox")).toHaveLength(8);
    await select(user, 4);
    expect(motions.filter((m) => m.options.duration === 330)).toHaveLength(5);
    expect(
      [...document.querySelectorAll(".ad-selected-row strong")].map(
        (el) => el.textContent,
      ),
    ).toEqual([
      "Reading 1.pdf",
      "Reading 3.pdf",
      "Reading 4.pdf",
      "Reading 5.pdf",
    ]);
  });
  it("keeps rapid selections unique, reveals additions only inside the capped stack, and cleans up on unmount", () => {
    const { unmount } = render(<Harness />);
    act(() =>
      screen
        .getAllByRole("checkbox")
        .forEach((input) => fireEvent.click(input)),
    );
    expect(document.querySelectorAll(".ad-selected-row")).toHaveLength(8);
    expect(document.querySelector(".ad-selected-list")).toHaveAttribute(
      "data-scrollable",
      "true",
    );
    expect(motions.filter((m) => m.options.duration === 330)).toHaveLength(4);
    expect(motions.filter((m) => m.options.duration === 150)).toHaveLength(4);
    unmount();
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(0);
    expect(motions.every((m) => m.animation.cancel.mock.calls.length > 0)).toBe(
      true,
    );
  });
  it("combines uploads and library references across tabs and prevents duplicate uploads", async () => {
    const user = userEvent.setup(),
      selection = vi.fn(),
      proceed = vi.fn();
    const uploaded = {
      id: "upload-1",
      name: "Notes.txt",
      size: 20,
      storageKey: "course:Notes.txt:20",
      source: "upload",
    };
    render(
      <Harness
        onSelection={selection}
        onContinue={proceed}
        upload={async () => [uploaded, uploaded]}
      />,
    );
    await select(user, 0);
    await user.click(screen.getByRole("tab", { name: "Upload New" }));
    await user.upload(
      screen.getByLabelText("Upload activity documents"),
      new File(["notes"], "Notes.txt", { type: "text/plain" }),
    );
    expect(document.querySelectorAll(".ad-selected-row")).toHaveLength(2);
    expect(selection.mock.lastCall[0][1]).toEqual(uploaded);
    await user.click(screen.getByRole("tab", { name: "Existing Documents" }));
    expect(
      screen.getByRole("checkbox", { name: /Reading 1\.pdf/ }),
    ).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Add Documents (2)" }));
    expect(proceed).toHaveBeenCalledOnce();
  });
  it("falls back to a short entrance when the selected stack is offscreen", async () => {
    destinationOffscreen = true;
    const user = userEvent.setup();
    render(<Harness />);
    await select(user, 0);
    expect(motions.filter((m) => m.options.duration === 330)).toHaveLength(0);
    expect(motions.filter((m) => m.options.duration === 150)).toHaveLength(1);
  });
  it("cancels flying clones on page scrolling without losing selections", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await select(user, 0);
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(1);
    fireEvent.scroll(window);
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(0);
    expect(
      screen.getByRole("checkbox", { name: /Reading 1\.pdf/ }),
    ).toBeChecked();
    expect(document.querySelector(".ad-selected-row").style.visibility).toBe(
      "",
    );
  });
  it("makes reduced-motion selections immediate without any animations", async () => {
    reduce = true;
    const user = userEvent.setup();
    render(<Harness />);
    await select(user, 0);
    expect(motions).toHaveLength(0);
    expect(document.querySelectorAll(".ad-selected-row")).toHaveLength(1);
  });
  it("clears all selections and active flights without removing library documents", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await select(user, 0);
    await select(user, 1);
    await user.click(
      screen.getByRole("button", { name: "Clear all", exact: true }),
    );
    expect(document.querySelectorAll(".ad-selected-row")).toHaveLength(0);
    expect(document.querySelectorAll(".ad-flying-document")).toHaveLength(0);
    expect(screen.getAllByRole("checkbox")).toHaveLength(8);
    expect(
      screen.getAllByRole("checkbox").every((input) => !input.checked),
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "Add Documents (0)" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Clear all", exact: true }),
    ).not.toBeInTheDocument();
  });
  it("keeps keyboard tab navigation and upload errors accessible", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        upload={async () => {
          throw new Error(
            "The embedding provider rejected its configured API key.",
          );
        }}
      />,
    );
    const existing = screen.getByRole("tab", { name: "Existing Documents" });
    existing.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Upload New" })).toHaveFocus();
    await user.upload(
      screen.getByLabelText("Upload activity documents"),
      new File(["notes"], "Notes.txt", { type: "text/plain" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The embedding provider rejected its configured API key.",
    );
    expect(
      screen.getByRole("button", { name: "Upload new documents" }),
    ).toBeEnabled();
  });
});
