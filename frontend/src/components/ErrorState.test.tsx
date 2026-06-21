import type { ReactElement } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LangProvider } from "../i18n";
import ErrorState from "./ErrorState";

// ErrorState calls useI18n() for the "Retry" label, so it must render under the provider.
function renderInI18n(ui: ReactElement) {
  return render(<LangProvider>{ui}</LangProvider>);
}

describe("ErrorState", () => {
  it("renders the friendly title and the raw detail", () => {
    renderInI18n(<ErrorState title="Failed to load groups" detail="Error: boom" />);
    expect(screen.getByRole("heading", { name: "Failed to load groups" })).toBeInTheDocument();
    expect(screen.getByText("Error: boom")).toBeInTheDocument();
  });

  it("shows Retry only when onRetry is given, and calls it on click", async () => {
    const onRetry = vi.fn();
    renderInI18n(<ErrorState title="oops" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("omits Retry when onRetry is absent", () => {
    renderInI18n(<ErrorState title="oops" />);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("renders a secondary action and fires its onClick", async () => {
    const onClick = vi.fn();
    renderInI18n(<ErrorState title="oops" action={{ label: "← New session", onClick }} />);
    await userEvent.click(screen.getByRole("button", { name: "← New session" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
