import Sections from "./Sections";
import Evidence from "./Evidence";

/** Structured fixed-section read (plan v3 L3). No markdown renderer. */
export default function AgentPanelAnswer({ turn }) {
  if (!turn) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Sections text={turn.text || ""} />
      {(turn.flagged || []).length > 0 && (
        <div style={{ color: "#e0a63c", fontSize: 12 }}>Flagged sentences: {turn.flagged.length} — numbers need evidence.</div>
      )}
      <Evidence turn={turn} />
    </div>
  );
}
