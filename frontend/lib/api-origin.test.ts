import { describe, expect, it } from "vitest";

import {
  resolveApiOrigin,
  resolveConfiguredApiOrigin,
  validateProductionApiOrigin,
} from "./api-origin";

describe("API origin configuration", () => {
  it("keeps the local backend default for development", () => {
    expect(resolveApiOrigin(undefined)).toBe("http://localhost:8000");
  });

  it("normalizes a configured trailing slash", () => {
    expect(resolveApiOrigin("https://api.finsight.example/")).toBe(
      "https://api.finsight.example",
    );
  });

  it("uses the legacy container argument when the primary origin is empty", () => {
    expect(
      resolveConfiguredApiOrigin("", "https://api.finsight.example"),
    ).toBe("https://api.finsight.example");
  });

  it("prefers the server-only backend origin when both are configured", () => {
    expect(
      resolveConfiguredApiOrigin(
        "https://private-api.finsight.example",
        "https://legacy-api.finsight.example",
      ),
    ).toBe("https://private-api.finsight.example");
  });

  it("accepts a production HTTPS origin", () => {
    expect(validateProductionApiOrigin("https://api.finsight.example")).toBe(
      "https://api.finsight.example",
    );
  });

  it.each([
    undefined,
    "not-a-url",
    "http://api.finsight.example",
    "https://localhost:8000",
    "https://127.0.0.1:8000",
    "https://user:secret@api.finsight.example",
    "https://api.finsight.example/v1",
    "https://api.finsight.example?debug=true",
  ])("rejects unsafe production value %s", (value) => {
    expect(() => validateProductionApiOrigin(value)).toThrow();
  });
});
