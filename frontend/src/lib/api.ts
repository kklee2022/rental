import createClient from "openapi-fetch";

import type { ApiPaths } from "./types";

let activeTenantSlug: string | null = null;
let csrfToken: string | null = null;
let authToken: string | null = null;

export const api = createClient<ApiPaths>({
  baseUrl:
    typeof window === "undefined"
      ? process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"
      : window.location.origin,
  credentials: "include",
});

export function setActiveTenantSlug(slug: string | null) {
  activeTenantSlug = slug;
}

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function setAuthToken(token: string | null) {
  authToken = token;
}

api.use({
  onRequest({ request }) {
    const method = request.method.toUpperCase();
    if (process.env.NODE_ENV !== "production") {
      console.debug("API request", method, request.url);
    }
    if (activeTenantSlug) {
      request.headers.set("X-Tenant", activeTenantSlug);
    }
    if (authToken) {
      request.headers.set("Authorization", `Token ${authToken}`);
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      if (csrfToken) request.headers.set("X-CSRFToken", csrfToken);
    }
    return request;
  },
});

export function apiErrorMessage(error: unknown, fallback = "操作未完成") {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  if (typeof error === "object") {
    const value = error as Record<string, unknown>;
    if (typeof value.detail === "string") return value.detail;
    const first = Object.values(value)[0];
    if (typeof first === "string") return first;
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
    if (first && typeof first === "object") {
      const nested = Object.values(first as Record<string, unknown>)[0];
      if (typeof nested === "string") return nested;
      if (Array.isArray(nested) && typeof nested[0] === "string") return nested[0];
    }
  }
  return fallback;
}

export function responseError(response: unknown): unknown {
  return (response as { error?: unknown } | null)?.error ?? null;
}

function authHeaders(tenantSlug?: string | null) {
  const headers: Record<string, string> = {};
  const slug = tenantSlug ?? activeTenantSlug;
  if (slug) headers["X-Tenant"] = slug;
  if (authToken) headers.Authorization = `Token ${authToken}`;
  return headers;
}

export async function apiUpload<T>(
  path: string,
  formData: FormData,
  tenantSlug?: string | null,
): Promise<{ data: T | null; error: unknown }> {
  try {
    const response = await fetch(
      new URL(path, window.location.origin).toString(),
      {
        method: "POST",
        credentials: "include",
        headers: authHeaders(tenantSlug),
        body: formData,
      },
    );
    const payload = await response.json();
    if (!response.ok) return { data: null, error: payload };
    return { data: payload as T, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function downloadApiFile(path: string, filename: string) {
  const response = await fetch(new URL(path, window.location.origin), {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function apiMutation<T>(
  path: string,
  options: {
    method?: "POST" | "PATCH" | "DELETE";
    body?: unknown;
    tenantSlug?: string | null;
  } = {},
): Promise<{ data: T | null; error: unknown }> {
  const method = options.method ?? "POST";
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...authHeaders(options.tenantSlug),
  };
  if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  try {
    const response = await fetch(
      new URL(path, window.location.origin).toString(),
      {
        method,
        credentials: "include",
        headers,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
      },
    );
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      if (!contentType.includes("application/json")) {
        return {
          data: null,
          error: new Error(`Request failed (${response.status})`),
        };
      }
      return { data: null, error: payload };
    }
    return { data: payload as T, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
