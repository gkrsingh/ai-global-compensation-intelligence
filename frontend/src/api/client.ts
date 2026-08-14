const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export interface HealthCheckResponse {
  status: string;
  checks: Record<string, string>;
}

export async function fetchHealth(): Promise<HealthCheckResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return (await response.json()) as HealthCheckResponse;
}
