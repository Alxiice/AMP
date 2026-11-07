/** Global player shortcuts. */

const TEXT_INPUT_TYPES = new Set(["text", "search", "email", "url", "password", "number", "tel"]);

/** True when the user is typing: space must reach the field, not the player. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as { tagName?: string; type?: string; isContentEditable?: boolean } | null;
  if (!el || typeof el.tagName !== "string") return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName.toUpperCase();
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") return TEXT_INPUT_TYPES.has(el.type || "text");
  return false;
}

/**
 * Space toggles play/pause anywhere except in text fields. On a focused button
 * it plays/pauses too instead of pressing that button (as in most music players).
 */
export function isPlayPauseKey(e: Pick<KeyboardEvent, "code" | "key" | "repeat" | "ctrlKey" | "altKey" | "metaKey" | "shiftKey" | "target">): boolean {
  if (e.code !== "Space" && e.key !== " ") return false;
  if (e.repeat || e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return false;
  return !isTypingTarget(e.target);
}
