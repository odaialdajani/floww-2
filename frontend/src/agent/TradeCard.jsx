/** Trade card (plan v3 L5/L6). W1/W2: proposal read only. Stage buttons
 *  arrive in W3 (paper) / W6 (live). Pricing tag quote_mid vs bs_theoretical.
 */
export default function TradeCard({ turn }) {
  const proposal = turn && turn.proposal;
  if (!proposal) return null;
  return (
    <div style={{ border: "1px solid #333942", borderRadius: 8, padding: 10, marginTop: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{proposal.structure_label || "Trade proposal"} · {proposal.pricing || "bs_theoretical"}</div>
      <div style={{ fontSize: 12 }}>{proposal.thesis || ""}</div>
      <div style={{ fontSize: 11, opacity: 0.8 }}>Invalidation: {proposal.invalidation || "n/a"} · Max loss: {proposal.max_loss || "n/a"}</div>
    </div>
  );
}
