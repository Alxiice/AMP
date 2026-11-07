import { describe, expect, it } from "vitest";
import { isPlayPauseKey, isTypingTarget } from "./keyboard";

const key = (target: unknown, extra: Partial<KeyboardEvent> = {}) => ({
  code: "Space", key: " ", repeat: false, ctrlKey: false, altKey: false, metaKey: false, shiftKey: false,
  target: target as EventTarget, ...extra,
});

describe("isTypingTarget", () => {
  it("text fields, textareas, selects and contenteditable are typing targets", () => {
    expect(isTypingTarget({ tagName: "INPUT", type: "text" } as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ tagName: "INPUT", type: "search" } as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ tagName: "TEXTAREA" } as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ tagName: "SELECT" } as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ tagName: "DIV", isContentEditable: true } as unknown as EventTarget)).toBe(true);
  });

  it("buttons, sliders, checkboxes and the page are not", () => {
    expect(isTypingTarget({ tagName: "BUTTON" } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget({ tagName: "INPUT", type: "range" } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget({ tagName: "INPUT", type: "checkbox" } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget({ tagName: "BODY" } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});

describe("isPlayPauseKey", () => {
  it("plain space outside text fields", () => {
    expect(isPlayPauseKey(key({ tagName: "BODY" }))).toBe(true);
    expect(isPlayPauseKey(key({ tagName: "BUTTON" }))).toBe(true);
  });

  it("ignores typing, repeats, modifiers and other keys", () => {
    expect(isPlayPauseKey(key({ tagName: "INPUT", type: "text" }))).toBe(false);
    expect(isPlayPauseKey(key({ tagName: "BODY" }, { repeat: true }))).toBe(false);
    expect(isPlayPauseKey(key({ tagName: "BODY" }, { ctrlKey: true }))).toBe(false);
    expect(isPlayPauseKey(key({ tagName: "BODY" }, { code: "KeyK", key: "k" }))).toBe(false);
  });
});
