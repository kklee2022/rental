"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  CalendarClock,
  ClipboardCheck,
  Gauge,
  ReceiptText,
  Truck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { AppShell } from "@/components/app-shell";
import { LoadingBlock, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type {
  BillingReport,
  FleetReport,
  Quote,
  RentalOrder,
  RentalReport,
} from "@/lib/types";
import { formatDate, formatMoney, formatNumber, titleCase } from "@/lib/format";

export default function DashboardPage() {
  const { tenant, status: authStatus } = useAuth();
  const [fleet, setFleet] = useState<FleetReport | null>(null);
  const [rentals, setRentals] = useState<RentalReport | null>(null);
  const [billing, setBilling] = useState<BillingReport | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [orders, setOrders] = useState<RentalOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authStatus !== "authenticated" || !tenant) return;
    let cancelled = false;
    setLoading(true);
    void Promise.all([
      api.GET("/api/v1/reports/fleet/"),
      api.GET("/api/v1/reports/rentals/"),
      api.GET("/api/v1/reports/billing/"),
      api.GET("/api/v1/quotes/"),
      api.GET("/api/v1/rental-orders/"),
    ]).then(([fleetResponse, rentalResponse, billingResponse, quoteResponse, orderResponse]) => {
      if (cancelled) return;
      if (!fleetResponse.error) setFleet(fleetResponse.data ?? null);
      if (!rentalResponse.error) setRentals(rentalResponse.data ?? null);
      if (!billingResponse.error) setBilling(billingResponse.data ?? null);
      if (!quoteResponse.error) setQuotes(quoteResponse.data?.results ?? []);
      if (!orderResponse.error) setOrders(orderResponse.data?.results ?? []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [authStatus, tenant]);

  const pendingQuotes = quotes.filter(
    (quote) => quote.status === "pending_approval",
  );
  const activeOrders = orders.filter((order) =>
    ["reserved", "active"].includes(order.status),
  );
  const attentionCount =
    (rentals?.overdue_orders ?? 0) + pendingQuotes.length;
  const fleetAvailable =
    fleet?.status_counts?.available ?? 0;

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">{formatDate(new Date().toISOString())}</span>
            <h2>今日需要處理的營運事項</h2>
            <p>集中查看審批、調度、可用資產與未結帳款。</p>
          </div>
          <div className={`attention ${attentionCount ? "attention--active" : ""}`}>
            <AlertTriangle size={17} />
            <span>{attentionCount} 項需要跟進</span>
          </div>
        </section>

        {loading ? (
          <LoadingBlock rows={6} />
        ) : (
          <>
            <section className="metric-grid">
              <div className="metric">
                <Truck size={19} />
                <span>可租資產</span>
                <strong>{formatNumber(fleetAvailable)}</strong>
                <small>共 {formatNumber(fleet?.total_assets)} 台</small>
              </div>
              <div className="metric">
                <Gauge size={19} />
                <span>即時使用率</span>
                <strong>{formatNumber(fleet?.utilization_percent)}%</strong>
                <small>{formatNumber(fleet?.allocated_now)} 台已分配</small>
              </div>
              <div className="metric">
                <ClipboardCheck size={19} />
                <span>待審報價</span>
                <strong>{formatNumber(pendingQuotes.length)}</strong>
                <small>{formatNumber(rentals?.upcoming_orders)} 張租約即將開始</small>
              </div>
              <div className="metric">
                <ReceiptText size={19} />
                <span>應收餘額</span>
                <strong>{formatMoney(billing?.outstanding)}</strong>
                <small>{formatMoney(billing?.held_deposits)} 按金持有中</small>
              </div>
            </section>

            <div className="dashboard-grid">
              <section className="panel panel--wide">
                <header className="panel__header">
                  <div>
                    <span className="eyebrow">Action queue</span>
                    <h3>待批報價</h3>
                  </div>
                  <Link className="text-link" href="/quotes">
                    查看全部 <ArrowUpRight size={15} />
                  </Link>
                </header>
                <div className="compact-table">
                  <div className="compact-table__head">
                    <span>報價</span>
                    <span>客戶</span>
                    <span>總額</span>
                    <span>狀態</span>
                  </div>
                  {pendingQuotes.slice(0, 5).map((quote) => (
                    <Link
                      className="compact-table__row"
                      href={`/quotes/${quote.id}`}
                      key={quote.id}
                    >
                      <strong>{quote.number}</strong>
                      <span>{quote.customer_name}</span>
                      <span>{formatMoney(quote.total)}</span>
                      <StatusBadge status={quote.status} />
                    </Link>
                  ))}
                  {!pendingQuotes.length ? (
                    <div className="inline-empty">目前沒有待批報價。</div>
                  ) : null}
                </div>
              </section>

              <section className="panel">
                <header className="panel__header">
                  <div>
                    <span className="eyebrow">Fleet state</span>
                    <h3>車隊狀態</h3>
                  </div>
                </header>
                <div className="status-list">
                  {Object.entries(fleet?.status_counts ?? {})
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 7)
                    .map(([status, count]) => (
                      <div className="status-row" key={status}>
                        <span>{titleCase(status)}</span>
                        <div className="status-row__bar">
                          <i
                            style={{
                              width: `${Math.min(
                                100,
                                (count / Math.max(fleet?.total_assets ?? 1, 1)) *
                                  100,
                              )}%`,
                            }}
                          />
                        </div>
                        <strong>{count}</strong>
                      </div>
                    ))}
                </div>
              </section>
            </div>

            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Live rental book</span>
                  <h3>進行中的租約</h3>
                </div>
                <Link className="text-link" href="/orders">
                  租約調度 <ArrowUpRight size={15} />
                </Link>
              </header>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>租約</th>
                      <th>客戶</th>
                      <th>工地</th>
                      <th>開始</th>
                      <th>結束</th>
                      <th>總額</th>
                      <th>狀態</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeOrders.slice(0, 8).map((order) => (
                      <tr key={order.id}>
                        <td>
                          <Link className="table-link" href={`/orders/${order.id}`}>
                            {order.number}
                          </Link>
                        </td>
                        <td>{order.customer_name}</td>
                        <td>{order.site_name ?? "—"}</td>
                        <td>{formatDate(order.start_at)}</td>
                        <td>{formatDate(order.end_at)}</td>
                        <td>{formatMoney(order.total)}</td>
                        <td>
                          <StatusBadge status={order.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!activeOrders.length ? (
                  <div className="table-empty">
                    <CalendarClock size={20} />
                    尚未有進行中的租約
                  </div>
                ) : null}
              </div>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
