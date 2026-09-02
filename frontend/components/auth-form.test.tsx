import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthForm } from "./auth-form";

const replace = vi.fn();
const login = vi.fn();
const register = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login, register }),
}));

describe("AuthForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, "", "/login");
  });

  it("supports password managers, recovery, Google, and password visibility", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);

    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
  });

  it("normalizes email and returns to the intended route after login", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/login?returnTo=%2Fportfolio");
    login.mockResolvedValue(undefined);
    render(<AuthForm mode="login" />);

    await user.type(screen.getByLabelText("Email address"), " Investor@Example.COM ");
    await user.type(screen.getByLabelText("Password"), "S3curePass!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("investor@example.com", "S3curePass!");
    expect(replace).toHaveBeenCalledWith("/portfolio");
  });

  it("validates registration inline before calling the API", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="register" />);

    await user.type(screen.getByLabelText("Email address"), "invalid");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByRole("alert")).toHaveTextContent("valid email");
    expect(register).not.toHaveBeenCalled();
  });
});
