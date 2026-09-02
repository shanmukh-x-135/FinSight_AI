import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePersistentString } from "./use-persistent-state";

function Subject() {
  const [value, setValue] = usePersistentString<string>("test-filter", "change");
  return <button onClick={() => setValue("symbol")}>{value}</button>;
}

describe("usePersistentString", () => {
  beforeEach(() => localStorage.clear());

  it("persists UI preferences and observes cross-document storage updates", () => {
    render(<Subject />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("button")).toHaveTextContent("symbol");
    expect(localStorage.getItem("test-filter")).toBe("symbol");

    localStorage.setItem("test-filter", "rsi");
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: "test-filter", newValue: "rsi" })));
    expect(screen.getByRole("button")).toHaveTextContent("rsi");
  });
});
