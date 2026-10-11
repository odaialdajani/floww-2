// G11 recorder polling: bounded scopes sightings after a record trigger.
// fetchScopes returns the price-history payload (or throws on outage — counts
// as a miss, never throws out). Non-empty scopes array means landed.
const sleep = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
export async function awaitRecording(fetchScopes, { tries = 4, gapMs = 5000 } = {}) {
  const total = Math.max(1, tries);
  for (let attempt = 1; attempt <= total; attempt += 1) {
    let scopes = [];
    try {
      const data = await fetchScopes(attempt);
      if (Array.isArray(data?.scopes)) scopes = data.scopes;
    } catch { /* outage counts as a miss */ }
    if (scopes.length > 0) return { recorded: true, tries: attempt };
    if (attempt < total) await sleep(Math.max(0, gapMs));
  }
  return { recorded: false, tries: total };
}
