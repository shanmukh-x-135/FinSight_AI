import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ContextualAIActions } from "./contextual-ai-actions";

describe("ContextualAIActions", () => {
  it("prefills the research question through an encoded chat link", () => {
    render(<ContextualAIActions actions={[{ label: "Explain move", prompt: "Explain AAA.NS using evidence & risks" }]} />);
    expect(screen.getByRole("link", { name: "Explain move" })).toHaveAttribute("href", "/chat?prompt=Explain%20AAA.NS%20using%20evidence%20%26%20risks");
  });
});
