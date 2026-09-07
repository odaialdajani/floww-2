const ORDER = ["Structure", "Flow", "Levels", "Vol", "Company", "What changed", "Confluence", "Verdict", "Invalidation", "Trade"];

/** Fixed-section JSX (plan v3 L3). Server emits <<S:Name>> markers; the panel
 *  renders them in order, no markdown dependency.
 */
export default function Sections({ text }) {
  const parts = [];
  const re = /<<S:([^>]+)>>/g;
  let last = 0;
  let m;
  const found = [];
  while ((m = re.exec(text || ""))) {
    found.push({ name: m[1].trim(), index: m.index, end: m.index + m[0].length });
  }
  if (!found.length) return <div style={{ fontSize: 13 }}>{text}</div>;
  found.forEach((f, i) => {
    const next = found[i + 1];
    const body = (text || "").slice(f.end, next ? next.index : undefined).trim();
    parts.push({ name: f.name, body });
    last = i;
  });
  void last;
  const rank = (n) => {
    const i = ORDER.indexOf(n);
    return i === -1 ? 99 : i;
  };
  parts.sort((a, b) => rank(a.name) - rank(b.name));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {parts.map((p) => (
        <div key={p.name}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>{p.name}</div>
          <div style={{ fontSize: 13 }}>{p.body}</div>
        </div>
      ))}
    </div>
  );
}
