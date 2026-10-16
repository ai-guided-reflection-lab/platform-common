import React from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import SignIn from "./SignIn";

afterEach(() => vi.unstubAllGlobals());

it("offers self-service entry only when the server enables demo mode", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: true }) }));
  render(<SignIn />);
  expect(await screen.findByRole("button", { name: "Enter demo" })).toBeEnabled();
  expect(screen.getByLabelText("Demo username")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it("keeps normal sign-in when demo mode is disabled", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false }) }));
  render(<SignIn />);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  expect(screen.getByLabelText("Email or username")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Enter demo" })).not.toBeInTheDocument();
});
