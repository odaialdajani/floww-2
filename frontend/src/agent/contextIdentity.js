function ordered(value) {
  if (Array.isArray(value)) return value.map(ordered);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])]));
  }
  return value;
}

// Local equality guard only; never an approval token or a server evidence hash.
export function contextIdentity(context) {
  return JSON.stringify(ordered(context));
}
