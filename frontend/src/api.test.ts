import { describe, expect, it } from "vitest";
import { exportUrl } from "./api";

describe("exportUrl", () => {
  it("builds an export link with the format and an URL-encoded token query param", () => {
    const u = exportUrl("sess-1", "zip");
    expect(u).toContain("/api/sessions/sess-1/export");
    expect(u).toContain("format=zip");
    expect(u).toMatch(/[?&]token=/); // token in query so a plain <a download> can authenticate
  });
});
