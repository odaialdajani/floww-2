import React, { useEffect, useState } from "react";
import TidehunterSettings from "./flowseeker/TidehunterSettings";

const STORAGE_KEY = "floww_settings";

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

export function saveSettings(patch) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...loadSettings(), ...patch }));
    window.dispatchEvent(new Event("floww-settings-changed"));
    return true;
  } catch {
    return false; // private mode — settings just don't persist
  }
}

export function getSettings() {
  return { refreshMs: 25000, defaultTicker: "SPY", theme: "dark", colorBlindMode: false, ...loadSettings() };
}

export function SettingsPanel({ refreshMs, onRefreshMsChange, defaultTicker, onDefaultTickerChange }) {
  const [open, setOpen] = useState(false);
  const [s, setSettings] = useState(getSettings);
  const [saveError, setSaveError] = useState(false);
  useEffect(() => {
    const refresh = () => setSettings(getSettings());
    const storage = (event) => { if (event.key === STORAGE_KEY || event.key === null) refresh(); };
    window.addEventListener("storage", storage);
    window.addEventListener("floww-settings-changed", refresh);
    return () => {
      window.removeEventListener("storage", storage);
      window.removeEventListener("floww-settings-changed", refresh);
    };
  }, []);

  const save = (patch) => {
    const saved = saveSettings(patch);
    setSaveError(!saved);
    return saved;
  };

  const setRefreshMs = (ms) => {
    if (save({ refreshMs: ms })) onRefreshMsChange?.(ms);
  };

  const setDefaultTicker = (t) => {
    if (save({ defaultTicker: t })) onDefaultTickerChange?.(t);
  };

  return (
    <div className="panel-2 p-2">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
      >
        <div className="label mb-0">Settings</div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {saveError && <p role="alert">Your setting could not be saved. Try again after checking browser storage.</p>}
          <div>
            <div className="label mb-0.5">Refresh Rate</div>
            <div className="flex gap-1">
              {[10000, 25000, 60000].map((ms) => (
                <button
                  key={ms}
                  onClick={() => setRefreshMs(ms)}
                  className={`btn flex-1 text-[9px] ${refreshMs === ms ? "active" : ""}`}
                >
                  {ms / 1000}s
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="label mb-0.5">Default Ticker</div>
            <input
              value={defaultTicker}
              onChange={(e) => setDefaultTicker(e.target.value.toUpperCase())}
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              placeholder="SPY"
            />
          </div>
          <div>
            <div className="label mb-0.5">Theme</div>
            <div className="flex gap-1">
              {["dark"].map((t) => (
                <button key={t} className="btn flex-1 text-[9px] active">{t}</button>
              ))}
            </div>
          </div>
          <div>
            <div className="label mb-0.5">Accessibility</div>
            <div className="flex gap-1">
              <button
                onClick={() => save({ colorBlindMode: !getSettings().colorBlindMode })}
                className={`btn flex-1 text-[9px] ${s.colorBlindMode ? "active" : ""}`}
                aria-label={s.colorBlindMode ? "Disable color-blind mode" : "Enable color-blind mode"}
                title="Use patterns instead of colors for regime indicators"
              >
                {s.colorBlindMode ? "👁️ Color-Blind ON" : "👁️ Color-Blind OFF"}
              </button>
            </div>
            <div className="text-[8px] text-slate-600 mt-0.5">Patterns instead of colors</div>
          </div>
          <div>
            <div className="label mb-0.5">Tidehunter Pro</div>
            <TidehunterSettings />
          </div>
        </div>
      )}
    </div>
  );
}
