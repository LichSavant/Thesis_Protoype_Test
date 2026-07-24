import { beforeEach, describe, expect, it, vi } from "vitest";
import { ensureScanButton, SCAN_BUTTON_ID } from "./gmailScanButton";

describe("Gmail Scan button injection", () => {
  beforeEach(() => { document.body.innerHTML = ""; });
  it("inserts once before Forward", () => {
    const area = document.createElement("div"), reply = document.createElement("button"), forward = document.createElement("button");
    area.append(reply, forward); document.body.append(area);
    const handler = vi.fn(); const first = ensureScanButton(area, forward, handler); const second = ensureScanButton(area, forward, handler);
    expect(first).toBe(second); expect(document.querySelectorAll(`#${SCAN_BUTTON_ID}`)).toHaveLength(1); expect(area.children[1]).toBe(first);
  });
  it("removes a stale button when Gmail replaces the action area", () => {
    const oldArea = document.createElement("div"), newArea = document.createElement("div"); document.body.append(oldArea, newArea);
    ensureScanButton(oldArea, null, vi.fn()); const current = ensureScanButton(newArea, null, vi.fn());
    expect(oldArea.querySelector(`#${SCAN_BUTTON_ID}`)).toBeNull(); expect(newArea.querySelector(`#${SCAN_BUTTON_ID}`)).toBe(current);
  });
  it("can insert into Gmail's nested Reply and Forward group", () => {
    const wrapper = document.createElement("div"), group = document.createElement("div"), reply = document.createElement("button"), forward = document.createElement("button");
    group.append(reply, forward); wrapper.append(group); document.body.append(wrapper);
    const button = ensureScanButton(forward.parentElement!, forward, vi.fn());
    expect(group.children[1]).toBe(button); expect(wrapper.children).toHaveLength(1);
  });
});
