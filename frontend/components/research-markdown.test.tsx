import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResearchMarkdown } from "./research-markdown";

describe("ResearchMarkdown", () => {
  it("renders finance responses as semantic headings and lists", () => {
    render(<ResearchMarkdown content={"### Evidence\n- **Breadth** is constructive\n- Risk remains `moderate`"} />);
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeVisible();
    expect(screen.getByRole("list")).toHaveTextContent("Breadth is constructive");
    expect(screen.getByText("moderate")).toHaveRole("code");
  });
});
