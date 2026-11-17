import { useEffect, useState } from "react";
import { api, type WidgetSettings } from "../api";
import { toast } from "../ui";

const DEFAULTS: WidgetSettings = { width: 320, height: 72, border: "#f4c0d1", background: "#fff1f4", progress: "#d4537e" };
const SIZES: Array<["width" | "height", string, number, number]> = [["width", "Width", 50, 4000], ["height", "Height", 20, 1000]];
const COLOURS: Array<[keyof WidgetSettings, string, string]> = [
  ["border", "Border", "Card outline and the line for the rest of the song."],
  ["background", "Background", "Shown 90 % opaque."],
  ["progress", "Progress bar", "The wave and the dot."],
];

/** OBS widget settings, saved by the backend so the widget page can read them. */
export function Widget() {
  const [ws, setWs] = useState<WidgetSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({}); // size fields while out of range

  useEffect(() => {
    api.getWidgetSettings().then(setWs, () => toast("Couldn't load the widget settings", true));
  }, []);

  if (!ws) return <div className="settings"><h1 className="page-title">Widget</h1></div>;

  const save = (next: WidgetSettings) => {
    setWs(next);
    api.saveWidgetSettings(next).catch(() => toast("Couldn't save the widget settings", true));
  };
  // Typing goes through out-of-range values ("5" on the way to "500"): show them, save only valid ones
  const setSize = (key: "width" | "height", value: string, min: number, max: number) => {
    const n = parseInt(value, 10);
    setDraft({ ...draft, [key]: value });
    if (n >= min && n <= max) save({ ...ws, [key]: n });
  };

  return (
    <div className="settings">
      <div className="page-header">
        <h1 className="page-title">Widget</h1>
        <button className="btn btn-secondary btn-small" onClick={() => { setDraft({}); save(DEFAULTS); }}>Reset to defaults</button>
      </div>

      <section className="settings-section">
        <h2>Size</h2>
        {SIZES.map(([key, label, min, max]) => (
          <div className="settings-row" key={key}>
            <div>
              <div className="settings-label">{label}</div>
              <div className="settings-hint">In pixels, {min} to {max}. <code>?w=</code> / <code>?h=</code> in the OBS source URL override it.</div>
            </div>
            <input className="search-input widget-size" type="number" min={min} max={max} value={draft[key] ?? ws[key]}
              onBlur={() => setDraft({})} onChange={(e) => setSize(key, e.target.value, min, max)} aria-label={`Widget ${label.toLowerCase()}`} />
          </div>
        ))}
      </section>

      <section className="settings-section">
        <h2>Colours</h2>
        {COLOURS.map(([key, label, hint]) => (
          <div className="settings-row" key={key}>
            <div>
              <div className="settings-label">{label}</div>
              <div className="settings-hint">{hint}</div>
            </div>
            <label className="swatch custom on" style={{ background: ws[key] as string }} title={`${label} colour`}>
              <input type="color" value={ws[key] as string} onChange={(e) => save({ ...ws, [key]: e.target.value })}
                aria-label={`Widget ${label.toLowerCase()} colour`} />
            </label>
          </div>
        ))}
      </section>
    </div>
  );
}
