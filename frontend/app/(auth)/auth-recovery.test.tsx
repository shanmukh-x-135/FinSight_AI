import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import ForgotPasswordPage from "./forgot-password/page";
import ResetPasswordPage from "./reset-password/page";

describe("authentication recovery screens", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, "", "/forgot-password");
  });

  it("shows the same successful recovery state without revealing account existence", async () => {
    vi.spyOn(api, "forgotPassword").mockResolvedValue(null);
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText("Email address"), "Investor@Example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(api.forgotPassword).toHaveBeenCalledWith("investor@example.com");
    expect(await screen.findByRole("heading", { name: "Check your inbox" })).toBeVisible();
    expect(screen.getByText(/If an eligible account exists/)).toBeVisible();
  });

  it("requires matching passwords and completes a single-use reset", async () => {
    window.history.replaceState({}, "", "/reset-password?token=secure-reset-token-value-1234567890");
    vi.spyOn(api, "resetPassword").mockResolvedValue(null);
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText("New password"), "New-S3curePass!");
    await user.type(screen.getByLabelText("Confirm new password"), "different");
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(api.resetPassword).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Confirm new password"));
    await user.type(screen.getByLabelText("Confirm new password"), "New-S3curePass!");
    await user.click(screen.getByRole("button", { name: "Reset password" }));

    expect(api.resetPassword).toHaveBeenCalledWith(
      "secure-reset-token-value-1234567890",
      "New-S3curePass!",
    );
    expect(await screen.findByRole("heading", { name: /password has been reset/i })).toBeVisible();
  });
});
