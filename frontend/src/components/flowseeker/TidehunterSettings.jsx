// TidehunterSettings.jsx — self-contained persistence for Tidehunter Pro.
// First consumer of floww_settings.tidehunter.{screens, sectionOrder, columns, mode}.
// Rendered both inside the tab (settings section) and by SettingsPanel.jsx with
// no new props. Syncs across mounts via a `storage` event. Private-mode safe.

import React, { useState, useEffect } from "react";
import { PULSE_DEFAULT_COLS } from "./tideFeed";

export const SETTINGS_KEY = "floww_settings";
export const DEFAULT_MODE = "trade";
export const DEFAULT_SECTION_ORDER = ["board", "vector", "pulse", "lattice", "trust"];
export const SECTION_LABELS = {
  board: "Board",
  vector: "Vector · direction",
  pulse: "Pulse · live flow",
  lattice: "Lattice · positioning",
  trust: "Trust",
};
export const MODES = ["trade", "monitor", "research"];

export function defaultTide() {
  return {
    screens: [],
    sectionOrder: [...DEFAULT_SECTION_ORDER],
    columns: {
      trade: [...PULSE_DEFAULT_COLS],
      monitor: [...PULSE_DEFAULT_COLS].slice(0, 8),
      research: null, // null = all 17
    },
    mode: DEFAULT_MODE,
  };
}

export function loadTide() {
  try {
    const all = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    const t = all.tidehunter || {};
    return { ...defaultTide(), ...t };
  } catch {
    return defaultTide();
  }
}

// Guarded write (exported so tests can pin the try/catch contract).
export function saveSettings(patch) {
  try {
    const all = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    const next = { ...all, tidehunter: { ...((all || {}).tidehunter || {}), ...patch } };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event("floww-settings-changed"));
    return true;
  } catch {
    return false;
  }
}

export function readTideKey(key) {
  return loadTide()[key];
}

export default function TidehunterSettings() {
  const [tide, setTide] = useState(loadTide);

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === SETTINGS_KEY) setTide(loadTide());
    };
    const refresh = () => setTide(loadTide());
    window.addEventListener("storage", onStorage);
    window.addEventListener("floww-settings-changed", refresh);
    return () => { window.removeEventListener("storage", onStorage); window.removeEventListener("floww-settings-changed", refresh); };
  }, []);

  const setMode = (mode) => {
    if (!saveSettings({ mode })) { window.alert("Layout could not be saved."); return; }
    setTide((t) => ({ ...t, mode }));
  };

  const moveSection = (id, dir) => {
    const order=[...(tide.sectionOrder || DEFAULT_SECTION_ORDER)];
    const i=order.indexOf(id),j=i+dir;
    if(i<0 || j<0 || j>=order.length)return;
    [order[i],order[j]]=[order[j],order[i]];
    if(!saveSettings({sectionOrder:order})){window.alert("Section order could not be saved.");return;}
    setTide(t=>({...t,sectionOrder:order}));
  };

  const order = tide.sectionOrder || DEFAULT_SECTION_ORDER;
  const customCount = (tide.screens || []).length;

  return (
    <div data-testid="tide-settings">
      <div style={{ display: "grid", gap: 4, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Screens &amp; layout</h3>
        <p style={{ margin: 0, fontSize: 12 }}>
          What runs, what is shown, and in which order. {customCount} custom screen{customCount === 1 ? "" : "s"} saved in floww Settings.
        </p>
      </div>
      <label style={{display:"block",marginBottom:12}}><input type="checkbox" checked={!!tide.colorBlindMode} onChange={e=>{
        if(!saveSettings({colorBlindMode:e.target.checked}))window.alert("Display choice could not be saved.");
      }}/> Colour-blind patterns and labels</label>
      <div style={{ marginBottom: 6, fontSize: 11, letterSpacing: ".1em", textTransform: "uppercase" }}>
        Layout mode
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={tide.mode === m}
            onClick={() => setMode(m)}
            style={{
              padding: "6px 14px",
              borderRadius: 7,
              border: "1px solid",
              textTransform: "capitalize",
            }}
          >
            {m}
          </button>
        ))}
      </div>
      <div style={{ marginBottom: 6, fontSize: 11, letterSpacing: ".1em", textTransform: "uppercase" }}>
        Page order
      </div>
      <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 4, fontSize: 13 }}>
        {order.map((id, i) => (
          <li key={id}>
            {SECTION_LABELS[id] || id}{" "}
            <button type="button" aria-label={`Move ${id} up`} disabled={i === 0} onClick={() => moveSection(id, -1)}>↑</button>{" "}
            <button type="button" aria-label={`Move ${id} down`} disabled={i === order.length - 1} onClick={() => moveSection(id, 1)}>↓</button>
          </li>
        ))}
      </ol>
      <p style={{ fontSize: 12, marginBottom: 0 }}>
        Columns are saved per mode · Trade: {(tide.columns?.trade || []).length} of 17 · Monitor:{" "}
        {(tide.columns?.monitor || []).length} · Research: all 17. Colour-blind mode follows the app setting.
      </p>
    </div>
  );
}
