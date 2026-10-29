"use client";

import { ArrowUpRight, ClipboardList, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  EmptyState,
  Input,
  LoadingBlock,
  StatusBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { RentalOrder } from "@/lib/types";
import { formatDateTime, formatMoney } from "@/lib/format";

const filters = ["all", "reserved", "active", "completed", "cancelled"] as const;

export default function OrdersPage() {
  const { tenant, status } = useAuth();
  const [orders, setOrders] = useState<RentalOrder[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    setLoading(true);
    void api.GET("/api/v1/rental-orders/").then((response) => {
      if (!response.error) setOrders(response.data?.results ?? []);
      setLoading(false);
    });
  }, [status, tenant]);

  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return orders.filter((order) => {
      const statusMatches = filter === "all" || order.status === filter;
      const searchMatches =
        !term ||
        [order.number, order.customer_name, order.site_name]
          .join(" ")
          .toLocaleLowerCase()
          .includes(term);
      return statusMatches && searchMatches;
    });
  }, [filter, orders, search]);

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Rental book</span>
            <h2>租約與調度</h2>
            <p>由已批報價建立租約，管理預留、出倉及回倉。</p>
          </div>
          <Link className="button button--primary" href="/quotes">
            <ClipboardList size={16} />
            由報價建立
          </Link>
        </section>

        <div className="toolbar">
          <div className="toolbar__group">
            <div className="search-box">
              <Search size={16} />
              <Input
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜尋租約、客戶或工地"
                value={search}
              />
            </div>
            <div className="segmented">
              {filters.map((item) => (
                <button
                  data-active={filter === item}
                  key={item}
                  onClick={() => setFilter(item)}
                  type="button"
                >
                  {item === "all"
                    ? "全部"
                    : item === "reserved"
                      ? "已預留"
                      : item === "active"
                        ? "進行中"
                        : item === "completed"
                          ? "已完成"
                          : "已取消"}
                </button>
              ))}
            </div>
          </div>
          <span className="inline-note">{filtered.length} 張租約</span>
        </div>

        {loading ? (
          <LoadingBlock rows={8} />
        ) : filtered.length ? (
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>租約</th>
                    <th>客戶 / 工地</th>
                    <th>租期</th>
                    <th>資產</th>
                    <th>總額</th>
                    <th>按金</th>
                    <th>狀態</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((order) => (
                    <tr key={order.id}>
                      <td>
                        <Link className="table-link" href={`/orders/${order.id}`}>
                          {order.number}
                        </Link>
                      </td>
                      <td>
                        <strong>{order.customer_name}</strong>
                        <small style={{ display: "block", color: "#75817c" }}>
                          {order.site_name ?? "未指定工地"}
                        </small>
                      </td>
                      <td>
                        {formatDateTime(order.start_at)}
                        <small style={{ display: "block", color: "#75817c" }}>
                          至 {formatDateTime(order.end_at)}
                        </small>
                      </td>
                      <td>
                        {order.lines
                          ?.map((line) => line.asset_number)
                          .filter(Boolean)
                          .join(", ") || "待分配"}
                      </td>
                      <td>{formatMoney(order.total)}</td>
                      <td>{formatMoney(order.deposit_total)}</td>
                      <td>
                        <StatusBadge status={order.status} />
                      </td>
                      <td>
                        <Link
                          aria-label="查看租約"
                          className="button button--ghost icon-button"
                          href={`/orders/${order.id}`}
                        >
                          <ArrowUpRight size={16} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="panel">
            <EmptyState
              detail="已批報價可轉為租約並分配具體資產。"
              title="目前沒有符合的租約"
            />
          </section>
        )}
      </div>
    </AppShell>
  );
}
