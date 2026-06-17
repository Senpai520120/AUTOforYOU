const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem('refresh');
  if (!refresh) return null;
  const res = await fetch(`${API}/api/v1/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  localStorage.setItem('access', data.access);
  return data.access;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const access = localStorage.getItem('access');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (access) headers['Authorization'] = `Bearer ${access}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401 && retry) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiFetch<T>(path, options, false);
    // Token refresh failed — clear storage
    localStorage.removeItem('access');
    localStorage.removeItem('refresh');
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(res.statusText), { status: res.status, data: err });
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export function apiGet<T>(path: string) {
  return apiFetch<T>(path);
}

export function apiPost<T>(path: string, body: unknown) {
  return apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function apiPut<T>(path: string, body: unknown) {
  return apiFetch<T>(path, { method: 'PUT', body: JSON.stringify(body) });
}

export function apiPatch<T>(path: string, body: unknown) {
  return apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
}

export function apiDelete(path: string) {
  return apiFetch<void>(path, { method: 'DELETE' });
}
