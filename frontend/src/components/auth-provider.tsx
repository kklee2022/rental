"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  api,
  apiErrorMessage,
  apiMutation,
  responseError,
  setActiveTenantSlug,
  setAuthToken,
} from "@/lib/api";
import type { Account, AccountTenant, CurrentTenant } from "@/lib/types";

const TENANT_STORAGE_KEY = "rental-erp-active-tenant";
const TOKEN_STORAGE_KEY = "rental-erp-api-token";

type AuthState = {
  status: "loading" | "authenticated" | "anonymous";
  account: Account | null;
  tenant: AccountTenant | null;
  currentTenant: CurrentTenant | null;
  signIn: (username: string, password: string) => Promise<string | null>;
  signOut: () => Promise<void>;
  selectTenant: (slug: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [currentTenant, setCurrentTenant] = useState<CurrentTenant | null>(null);

  const loadAccount = useCallback(async () => {
    try {
      setActiveTenantSlug(null);
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem(TOKEN_STORAGE_KEY)
          : null;
      if (!token) {
        setStatus("anonymous");
        setAccount(null);
        setSelectedSlug(null);
        setCurrentTenant(null);
        setAuthToken(null);
        return;
      }
      setAuthToken(token);

      const response = await api.GET("/api/v1/me/");
      if (response.error || !response.data) {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        setAuthToken(null);
        setStatus("anonymous");
        setAccount(null);
        return;
      }

      const nextAccount = response.data;
      const stored =
        typeof window !== "undefined"
          ? window.localStorage.getItem(TENANT_STORAGE_KEY)
          : null;
      const validStored = nextAccount.tenants.some((item) => item.slug === stored);
      const nextSlug = validStored
        ? stored
        : nextAccount.tenants[0]?.slug ?? null;
      setAccount(nextAccount);
      setSelectedSlug(nextSlug);
      setActiveTenantSlug(nextSlug);
      setStatus("authenticated");
    } catch {
      setStatus("anonymous");
      setAccount(null);
      setSelectedSlug(null);
      setCurrentTenant(null);
      setActiveTenantSlug(null);
    }
  }, []);

  useEffect(() => {
    void loadAccount();
  }, [loadAccount]);

  useEffect(() => {
    if (!selectedSlug) {
      setCurrentTenant(null);
      setActiveTenantSlug(null);
      return;
    }
    setActiveTenantSlug(selectedSlug);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TENANT_STORAGE_KEY, selectedSlug);
    }
    let cancelled = false;
    void api.GET("/api/v1/tenant/").then((response) => {
      if (!cancelled && !response.error) setCurrentTenant(response.data ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedSlug]);

  const signIn = useCallback(async (username: string, password: string) => {
    try {
      setActiveTenantSlug(null);
      const response = await apiMutation<{
        detail: string;
        username: string;
        token: string;
      }>(
        "/api/v1/auth/login/",
        {
          body: { username, password },
        },
      );
      const loginError = responseError(response);
      if (loginError) {
        return apiErrorMessage(loginError, "登入失敗");
      }
      if (!response.data?.token) return "登入回應缺少 API token";
      window.localStorage.setItem(TOKEN_STORAGE_KEY, response.data.token);
      setAuthToken(response.data.token);
      await loadAccount();
      return null;
    } catch (error) {
      console.error("Login request failed", error);
      return "無法連接營運 API";
    }
  }, [loadAccount]);

  const signOut = useCallback(async () => {
    await apiMutation("/api/v1/auth/logout/");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
    setAuthToken(null);
    setStatus("anonymous");
    setAccount(null);
    setSelectedSlug(null);
    setCurrentTenant(null);
    setActiveTenantSlug(null);
  }, []);

  const selectTenant = useCallback(async (slug: string) => {
    setSelectedSlug(slug);
  }, []);

  const tenant = useMemo(
    () => account?.tenants.find((item) => item.slug === selectedSlug) ?? null,
    [account, selectedSlug],
  );

  const value = useMemo<AuthState>(
    () => ({
      status,
      account,
      tenant,
      currentTenant,
      signIn,
      signOut,
      selectTenant,
      refresh: loadAccount,
    }),
    [
      status,
      account,
      tenant,
      currentTenant,
      signIn,
      signOut,
      selectTenant,
      loadAccount,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
