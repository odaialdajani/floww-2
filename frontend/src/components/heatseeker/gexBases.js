// Compatibility import for PR 89 consumers; one display metadata registry.
// The backend still owns formulas and numeric observations.
import { ALL_BASES } from '../../lib/solsticeMetrics';
export const GEX_BASES = ALL_BASES.filter(b => b.id !== 'window');

export function gexBasisLabel(id) {
  return GEX_BASES.find(b => b.id === id)?.label || 'Unknown GEX basis';
}
