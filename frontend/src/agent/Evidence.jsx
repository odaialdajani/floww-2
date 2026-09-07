/** Evidence chips with hover-to-source (plan v3 L2 cite-don't-type). */
export default function Evidence({ turn }) {
  const ledger = (turn && turn.ledger) || {};
  const ids = Object.keys(ledger).slice(0, 12);
  if (!ids.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {ids.map((id) => (
        <span key={id} title={`${ledger[id].tool} · ${ledger[id].source} · ${ledger[id].status}`} style={{ fontSize: 11, background: "#16181c", border: "1px solid #333942", borderRadius: 10, padding: "2px 8px" }}>
          {id}
        </span>
      ))}
    </div>
  );
}
