import { useEffect, useState } from "react";
import { api, type WidgetSettings } from "../api";
import { toast } from "../ui";

const DEFAULTS: WidgetSettings = { width: 320, height: 72, border: "#f4c0d1", background: "#fff1f4", progress: "#d4537e", text: "#4b1528", opacity: 90 };
const SIZES: Array<["width" | "height", string, number, number]> = [["width", "Width", 50, 4000], ["height", "Height", 20, 1000]];
const COLOURS: Array<[keyof WidgetSettings, string, string]> = [
  ["border", "Border", "Card outline and the line for the rest of the song."],
  ["background", "Background", "Its opacity is set below."],
  ["progress", "Progress bar", "The wave and the dot."],
  ["text", "Text", "Title; the artist uses it at 75 %."],
];

/** OBS widget settings, saved by the backend so the widget page can read them. */
export function Widget() {
  const [ws, setWs] = useState<WidgetSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({}); // size fields while out of range
  const [port, setPort] = useState(0);

  useEffect(() => {
    api.getWidgetSettings().then(setWs, () => toast("Couldn't load the widget settings", true));
    api.health().then((h) => setPort(h.widget_port ?? 0), () => {});
  }, []);

  // No ?w=/?h=: the size set below applies
  const copyUrl = () => {
    navigator.clipboard.writeText(`http://127.0.0.1:${port}/`).then(
      () => toast("Widget URL copied"),
      () => toast("Couldn't copy the URL", true),
    );
  };

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
        <div className="btn-row" style={{ marginTop: 0 }}>
          <button className="btn btn-small" onClick={copyUrl} disabled={!port}
            title={port ? "Paste it as the URL of an OBS browser source" : "The widget is off or its port is taken"}>
            Copy widget URL
          </button>
          <button className="btn btn-secondary btn-small" onClick={() => { setDraft({}); save(DEFAULTS); }}>Reset to defaults</button>
        </div>
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

        <div className="settings-row">
          <div>
            <div className="settings-label">Opacity</div>
            <div className="settings-hint">Border and background. The text, cover and progress bar stay opaque.</div>
          </div>
          <div className="settings-slider">
            <input type="range" min={0} max={100} step={5} value={ws.opacity}
              onChange={(e) => save({ ...ws, opacity: parseInt(e.target.value, 10) })} aria-label="Widget opacity" />
            <span className="settings-value">{ws.opacity} %</span>
          </div>
        </div>
      </section>
    </div>
  );
}
