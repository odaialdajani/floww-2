// Retry reporting reads/uploads only; this policy never replays product actions.
export const permanentRefusal = response => response?.status >= 400 && response.status < 500
  && ![408,429].includes(response.status);

export function retryDelay(response, failures, base) {
  const value = response?.headers?.get?.("Retry-After");
  let supplied = 0;
  if (typeof value === "string" && value.trim()) {
    const seconds = Number(value);
    const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(value) - Date.now();
    if (Number.isFinite(delay)) supplied = Math.max(0,delay);
  }
  return Math.max(supplied,Math.min(300000,base * 2 ** Math.min(Math.max(0,failures-1),10)));
}
