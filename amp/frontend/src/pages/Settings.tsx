import { ACCENT_PRESETS, MAX_FADE_SEC, resetSettings, updateSettings, useSettings, type Theme } from "../settings";

const THEMES: Array<[Theme, string]> = [["dark", "Dark"], ["light", "Light"], ["system", "System"]];

export function Settings() {
  const s = useSettings();

  return (
    <div className="settings">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <button className="btn btn-secondary btn-small" onClick={resetSettings}>Reset to defaults</button>
      </div>

      <section className="settings-section">
        <h2>Appearance</h2>

        <div className="settings-row">
          <div>
            <div className="settings-label">Theme</div>
            <div className="settings-hint">System follows your Windows light/dark setting.</div>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Theme">
            {THEMES.map(([value, label]) => (
              <button key={value} role="radio" aria-checked={s.theme === value}
                className={s.theme === value ? "on" : ""} onClick={() => updateSettings({ theme: value })}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">Accent colour</div>
            <div className="settings-hint">Buttons, highlights and the active song.</div>
          </div>
          <div className="swatches">
            {ACCENT_PRESETS.map((c) => (
              <button key={c} className={`swatch${s.accent === c ? " on" : ""}`} style={{ background: c }}
                onClick={() => updateSettings({ accent: c })} aria-label={`Accent ${c}`} aria-pressed={s.accent === c} />
            ))}
            <label className={`swatch custom${ACCENT_PRESETS.includes(s.accent) ? "" : " on"}`} title="Custom colour"
              style={ACCENT_PRESETS.includes(s.accent) ? undefined : { background: s.accent }}>
              <input type="color" value={s.accent} onChange={(e) => updateSettings({ accent: e.target.value })}
                aria-label="Custom accent colour" />
              +
            </label>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h2>Playback</h2>

        <div className="settings-row">
          <div>
            <div className="settings-label">Fade between songs</div>
            <div className="settings-hint">The end of each song fades out and the next one fades in.</div>
          </div>
          <div className="settings-slider">
            <input type="range" min={0} max={MAX_FADE_SEC} step={0.5} value={s.fadeSec}
              onChange={(e) => updateSettings({ fadeSec: parseFloat(e.target.value) })} aria-label="Fade duration" />
            <span className="settings-value">{s.fadeSec === 0 ? "Off" : `${s.fadeSec} s`}</span>
          </div>
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-label">Play / pause</div>
            <div className="settings-hint">Space bar, anywhere except in text fields.</div>
          </div>
        </div>
      </section>
    </div>
  );
}
