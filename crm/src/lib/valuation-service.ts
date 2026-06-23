import "server-only";

export function valuationServiceSettings() {
  return {
    baseUrl: (process.env.VALUATION_API_URL ?? "http://127.0.0.1:8010").replace(/\/$/, "")
  };
}

export async function valuationServiceFetch(pathname: string, init?: RequestInit) {
  const settings = valuationServiceSettings();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  return fetch(`${settings.baseUrl}${pathname}`, {
    ...init,
    cache: "no-store",
    headers,
    signal: AbortSignal.timeout(15_000)
  });
}
