"use client";

import {
  Building2,
  ChevronDown,
  ClipboardList,
  FileText,
  FileUp,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  ScanLine,
  Truck,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "./auth-provider";
import { Button } from "./ui";

const navigation: Array<{
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  feature?: string;
}> = [
  { href: "/", label: "總覽", icon: LayoutDashboard },
  { href: "/customers", label: "客戶", icon: Users },
  { href: "/fleet", label: "車隊", icon: Truck },
  {
    href: "/logistics",
    label: "倉務物流",
    icon: ScanLine,
    feature: "mobile_logistics",
  },
  { href: "/imports", label: "匯入", icon: FileUp },
  { href: "/quotes", label: "報價", icon: FileText },
  { href: "/orders", label: "租約", icon: ClipboardList },
  { href: "/billing", label: "帳務", icon: ReceiptText },
];

const pageTitles: Record<string, string> = {
  "/": "營運總覽",
  "/customers": "客戶資料",
  "/fleet": "車隊與資產",
  "/logistics": "倉務物流",
  "/imports": "資料匯入",
  "/quotes": "報價管理",
  "/orders": "租約調度",
  "/billing": "營運帳務",
};

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    status,
    account,
    tenant,
    currentTenant,
    signOut,
    selectTenant,
  } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [router, status]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  if (status === "loading") {
    return (
      <main className="boot-screen">
        <div className="boot-mark">MR</div>
        <p>正在連接營運系統</p>
      </main>
    );
  }
  if (status === "anonymous") return null;

  const activePage =
    Object.entries(pageTitles).find(
      ([path]) => path !== "/" && pathname.startsWith(path),
    )?.[1] ?? pageTitles["/"];
  const visibleNavigation = navigation.filter(
    (item) =>
      !item.feature ||
      currentTenant?.plan.features.includes(item.feature) ||
      currentTenant === null,
  );

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__brand">
          <div className="brand-mark">
            <span>MR</span>
          </div>
          <div>
            <strong>機械租賃</strong>
            <small>Operations</small>
          </div>
          <Button
            aria-label="關閉選單"
            className="sidebar__close"
            onClick={() => setMobileOpen(false)}
            variant="ghost"
          >
            <X size={18} />
          </Button>
        </div>

        <nav className="sidebar__nav" aria-label="主要導覽">
          {visibleNavigation.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                className={`nav-item ${active ? "nav-item--active" : ""}`}
                href={item.href}
                key={item.href}
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar__tenant">
          <span className="eyebrow">目前租戶</span>
          <div className="tenant-select-wrap">
            <Building2 size={16} />
            <select
              aria-label="切換租戶"
              onChange={(event) => void selectTenant(event.target.value)}
              value={tenant?.slug ?? ""}
            >
              {account?.tenants.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          {currentTenant ? (
            <div className="tenant-meta">
              <span>{currentTenant.role}</span>
              <span>{currentTenant.plan.code}</span>
            </div>
          ) : null}
        </div>
      </aside>

      {mobileOpen ? (
        <button
          aria-label="關閉選單"
          className="sidebar-scrim"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <div className="workspace">
        <header className="topbar">
          <div className="topbar__heading">
            <Button
              aria-label="開啟選單"
              className="mobile-menu"
              onClick={() => setMobileOpen(true)}
              variant="ghost"
            >
              <Menu size={20} />
            </Button>
            <div>
              <span className="eyebrow">{tenant?.name}</span>
              <h1>{activePage}</h1>
            </div>
          </div>
          <div className="topbar__user">
            <div className="user-copy">
              <strong>{account?.username}</strong>
              <span>{tenant?.membership.role}</span>
            </div>
            <Button
              className="icon-button"
              onClick={() => void signOut()}
              title="登出"
              variant="ghost"
            >
              <LogOut size={18} />
            </Button>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
