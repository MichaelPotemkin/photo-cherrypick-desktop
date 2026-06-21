import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ConfirmModal from "./ConfirmModal";

describe("ConfirmModal", () => {
  it("renders the message and fires confirm / cancel (rendered via a body portal)", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        message="Favorite 5 picks?"
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByText("Favorite 5 picks?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("cancels on Escape", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        message="m"
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("danger variant opens with focus on Cancel (a reflexive Enter dismisses, not destroys)", () => {
    render(
      <ConfirmModal
        message="Delete this session?"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => {}}
        onCancel={() => {}}
        danger
      />,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });
});
