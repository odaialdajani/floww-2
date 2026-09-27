import React, { useEffect, useState } from "react";

export const PAPER_SETUP_KEY = "floww_paper_setup_v1";
const emptyDraft = () => ({
  name: "", startingCash: "", maxTradeLoss: "", maxOpenRisk: "", maxDayLoss: "",
  feePerContract: "", slippageEnabled: "", slippageMethod: "", priceDifference: "",
});
const accountIdentity = value => typeof value === "string" && /^\S{1,100}$/.test(value);
const cleanDraft = value => {
  const draft = emptyDraft();
  if (!value || typeof value !== "object" || Array.isArray(value)) return draft;
  for (const key of Object.keys(draft)) {
    if (typeof value[key] === "string" && value[key].length <= (key === "name" ? 80 : 32)) draft[key] = value[key];
  }
  if (!["", "on", "off"].includes(draft.slippageEnabled)) draft.slippageEnabled = "";
  if (!["", "price", "cash"].includes(draft.slippageMethod)) draft.slippageMethod = "";
  return draft;
};

function readSetup() {
  try {
    const raw = JSON.parse(localStorage.getItem(PAPER_SETUP_KEY));
    if (raw?.version !== 1 || !raw.drafts || typeof raw.drafts !== "object" || Array.isArray(raw.drafts)) throw new Error("Invalid setup");
    const drafts = Object.fromEntries(Object.entries(raw.drafts).filter(([key]) =>
      key === "new" || key.startsWith("account:") && accountIdentity(key.slice(8)))
      .map(([key, value]) => [key, cleanDraft(value)]));
    return { version: 1, accountChoice: ["new", "existing"].includes(raw.accountChoice) ? raw.accountChoice : "",
      selectedAccount: accountIdentity(raw.selectedAccount) ? raw.selectedAccount : "", drafts };
  } catch {
    return { version: 1, accountChoice: "", selectedAccount: "", drafts: {} };
  }
}

const moneyFields = [
  ["startingCash", "Starting cash ($)"], ["maxTradeLoss", "Most to risk per trade ($)"],
  ["maxOpenRisk", "Most to risk across open trades ($)"], ["maxDayLoss", "Daily loss limit ($)"],
  ["feePerContract", "Fee per option contract ($)"],
];
const controlClass = "w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200";

export default function PaperSettings({ accounts = [] }) {
  const [setup, setSetup] = useState(readSetup);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // Caller must provide owned accounts. A live account cannot enter this picker.
  const eligible = accounts.filter(account => account?.paper === true && account.venue === "internal" &&
    accountIdentity(account.id) && typeof account.name === "string");
  const accountKey = setup.accountChoice === "new" ? "new" :
    eligible.some(account => account.id === setup.selectedAccount) ? `account:${setup.selectedAccount}` : null;
  const draft = { ...emptyDraft(), ...(accountKey ? setup.drafts[accountKey] : {}) };
  const update = patch => {
    if (!accountKey) return;
    setMessage(""); setError("");
    setSetup(old => ({ ...old, drafts: { ...old.drafts, [accountKey]: { ...emptyDraft(), ...old.drafts[accountKey], ...patch } } }));
  };
  useEffect(() => {
    const refresh = event => { if (event.key === PAPER_SETUP_KEY || event.key === null) { setSetup(readSetup()); setMessage(""); } };
    window.addEventListener("storage", refresh);
    return () => window.removeEventListener("storage", refresh);
  }, []);
  const save = () => {
    setError(""); setMessage("");
    if (!accountKey) { setError("Choose a paper account setup first."); return; }
    if (Object.values(setup.drafts).some(value => JSON.stringify(cleanDraft(value)) !== JSON.stringify(value))) {
      setError("Choose valid paper settings before saving."); return;
    }
    if ([...moneyFields.map(([key]) => key), "priceDifference"].some(key =>
      draft[key] !== "" && (typeof draft[key] !== "string" || !/^(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(draft[key])))) {
      setError("Use a positive dollar amount or zero, without commas."); return;
    }
    try {
      localStorage.setItem(PAPER_SETUP_KEY, JSON.stringify(setup));
      setMessage("Setup saved on this device. This does not open an account or place a trade.");
    } catch {
      setError("Setup could not be saved. Your earlier saved setup is unchanged.");
    }
  };
  return <section aria-label="Paper trading setup" className="space-y-2" style={{ fontSize: 12 }}>
    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Paper trading</h3>
    <p style={{ margin: 0 }}>Choose your setup. Paper trading stays off until its checks are complete.</p>
    <label className="block">Paper account
      <select aria-label="Paper account" className={controlClass} value={setup.accountChoice} onChange={event => {
        setSetup(old => ({ ...old, accountChoice: event.target.value })); setMessage(""); setError("");
      }}>
        <option value="">Choose a setup</option>
        <option value="existing">Use a saved paper account</option>
        <option value="new">Set up a new paper account</option>
      </select>
    </label>
    {setup.accountChoice === "existing" && <>
      <label className="block">Saved paper account
        <select aria-label="Saved paper account" className={controlClass} value={eligible.some(account => account.id === setup.selectedAccount) ? setup.selectedAccount : ""}
          disabled={!eligible.length} onChange={event => { setSetup(old => ({ ...old, selectedAccount: event.target.value })); setMessage(""); }}>
          <option value="">Choose an account</option>
          {eligible.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
        </select>
      </label>
      {!eligible.length && <p>No saved paper accounts are available here yet.</p>}
    </>}
    <fieldset disabled={!accountKey} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
      {setup.accountChoice === "new" && <>
        <label>Account name<input className={controlClass} maxLength={80} value={draft.name} onChange={event => update({ name: event.target.value })} /></label>
        {moneyFields.map(([key, label]) => <label key={key}>{label}
          <input className={controlClass} inputMode="decimal" maxLength={32} value={draft[key]} onChange={event => update({ [key]: event.target.value })} />
        </label>)}
        <p style={{ margin: 0 }}>Leave a value blank until you choose it. No cash or risk limit is assumed.</p>
      </>}
      <label>Slippage
        <select aria-label="Slippage" className={controlClass} value={draft.slippageEnabled} onChange={event => update({ slippageEnabled: event.target.value })}>
          <option value="">Choose on or off</option><option value="on">On</option><option value="off">Off</option>
        </select>
      </label>
      <label>How slippage is charged
        <select aria-label="How slippage is charged" className={controlClass} value={draft.slippageMethod} onChange={event => update({ slippageMethod: event.target.value })}>
          <option value="">Choose a method</option><option value="price">Worse fill price</option><option value="cash">Separate cash charge</option>
        </select>
      </label>
      <label>Price difference ($)
        <input className={controlClass} inputMode="decimal" maxLength={32} value={draft.priceDifference} onChange={event => update({ priceDifference: event.target.value })} />
      </label>
      <p style={{ margin: 0 }}>Slippage counts once. Fees still apply when slippage is off. Changes affect future paper trades only.</p>
    </fieldset>
    <button type="button" className="btn" onClick={save}>Save paper setup</button>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
