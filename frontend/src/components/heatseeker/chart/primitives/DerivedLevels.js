// B09 frontend mirror: distinct source shapes, same gates.
export function deriveRatio(source, target) {
  if (!source || !target) return { status: 'unavailable' };
  if (typeof source.price !== 'number' || typeof target.price !== 'number' || target.price === 0) {
    return { status: 'unavailable' };
  }
  return { status: 'available', ratio: source.price / target.price };
}
