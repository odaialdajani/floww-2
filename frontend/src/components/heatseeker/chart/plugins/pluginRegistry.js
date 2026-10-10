// B26 allowlisted plugins: declarative types only, no remote code.
// Nexus/traders/Quiet Calf deferred; XABCD/Elliott need independent rules.
export const ALLOWLIST = ['overlay', 'study', 'export'];
export function registerPlugin(type, spec) {
  if (!ALLOWLIST.includes(type)) return { status: 'deferred', reason: 'not-allowlisted' };
  if (spec?.remoteCode || spec?.url) return { status: 'refused', reason: 'no-remote-code' };
  if (['nexus', 'traders', 'quiet-calf', 'xabcd', 'elliott'].includes(spec?.name)) {
    return { status: 'deferred', reason: 'separately-commissioned' };
  }
  return { status: 'registered', type };
}
