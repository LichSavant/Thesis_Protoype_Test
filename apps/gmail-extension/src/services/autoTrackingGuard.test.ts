import { describe, expect, it } from "vitest";
import { AutoTrackingGuard } from "./autoTrackingGuard";

it("prevents duplicate automatic events while allowing a later different selection", () => {
  const guard = new AutoTrackingGuard();
  expect(guard.shouldTrack("message-1")).toBe(true);
  expect(guard.shouldTrack("message-1")).toBe(false);
  expect(guard.shouldTrack("message-2")).toBe(true);
  expect(guard.shouldTrack("message-1")).toBe(true);
});
