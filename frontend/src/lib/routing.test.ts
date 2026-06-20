import { describe, expect, it } from "vitest";
import { parseSessionId } from "./routing";

describe("parseSessionId", () => {
  it("extracts a uuid from /session/<id>", () => {
    expect(parseSessionId("/session/3c518675-1e34-4c53-9f5e-631621444c3d")).toBe(
      "3c518675-1e34-4c53-9f5e-631621444c3d",
    );
  });

  it("ignores trailing path segments", () => {
    expect(parseSessionId("/session/abc123/extra")).toBe("abc123");
  });

  it("returns null for the home path and unknown routes", () => {
    expect(parseSessionId("/")).toBeNull();
    expect(parseSessionId("/sessions")).toBeNull();
    expect(parseSessionId("/session/")).toBeNull();
  });
});
