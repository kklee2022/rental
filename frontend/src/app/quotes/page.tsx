"use client";

import { ArrowUpRight, FilePlus2, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  Modal,
  Select,
  StatusBadge,
} from "@/components/ui";
import { api, apiErrorMessage, responseError } from "@/lib/api";
import type { Customer, Quote, Site } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/format";

const filters = ["all", "draft", "pending_approval", "approved", "converted"] as const;

export default function QuotesPage() {
  const { tenant, status } = useAuth();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<number | null>(null);

  async function loadQuotes() {
    setLoading(true);
    const [quoteResponse, customerResponse, siteResponse] = await Promise.all([
      api.GET("/api/v1/quotes/"),
      api.GET("/api/v1/customers/"),
      api.GET("/api/v1/sites/"),
    ]);
    if (!quoteResponse.error) setQuotes(quoteResponse.data?.results ?? []);
    if (!customerResponse.error) {
      const nextCustomers = customerResponse.data?.results ?? [];
      setCustomers(nextCustomers);
      setCustomerId((current) => current ?? nextCustomers[0]?.id ?? null);
    }
    if (!siteResponse.error) setSites(siteResponse.data?.results ?? []);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadQuotes();
  }, [status, tenant]);

  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return quotes.filter((quote) => {
      const statusMatches = filter === "all" || quote.status === filter;
      const searchMatches =
        !term ||
        [quote.number, quote.customer_name, quote.site_name]
          .join(" ")
          .toLocaleLowerCase()
          .includes(term);
      return statusMatches && searchMatches;
    });
  }, [filter, quotes, search]);

  async function createQuote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/quotes/", {
      body: {
        customer: Number(form.get("customer")),
        site: form.get("site") ? Number(form.get("site")) : null,
        valid_until: String(form.get("valid_until")),
        notes: String(form.get("notes") ?? ""),
      },
    });
    setSubmitting(false);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "報價建立失敗"));
      return;
    }
    setOpen(false);
    await loadQuotes();
  }

  const visibleSites = sites.filter((site) => site.customer === customerId);

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Commercial workflow</span>
            <h2>報價與審批</h2>
            <p>建立明細、計算租金及追蹤審批狀態。</p>
          </div>
          <Button onClick={() => setOpen(true)} variant="primary">
            <FilePlus2 size={16} />
            新增報價
          </Button>
        </section>

        <div className="toolbar">
          <div className="toolbar__group">
            <div className="search-box">
              <Search size={16} />
              <Input
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜尋報價、客戶或工地"
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
                    : item === "pending_approval"
                      ? "待審"
                      : item === "draft"
                        ? "草稿"
                        : item === "approved"
                          ? "已批"
                          : "已轉租約"}
                </button>
              ))}
            </div>
          </div>
          <span className="inline-note">{filtered.length} 張報價</span>
        </div>

        {loading ? (
          <LoadingBlock rows={7} />
        ) : filtered.length ? (
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>報價</th>
                    <th>客戶</th>
                    <th>工地</th>
                    <th>有效期</th>
                    <th>小計</th>
                    <th>稅項</th>
                    <th>總額</th>
                    <th>狀態</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((quote) => (
                    <tr key={quote.id}>
                      <td>
                        <Link className="table-link" href={`/quotes/${quote.id}`}>
                          {quote.number}
                        </Link>
                      </td>
                      <td>{quote.customer_name}</td>
                      <td>{quote.site_name ?? "—"}</td>
                      <td>{formatDate(quote.valid_until)}</td>
                      <td>{formatMoney(quote.subtotal)}</td>
                      <td>{formatMoney(quote.tax_total)}</td>
                      <td>
                        <strong>{formatMoney(quote.total)}</strong>
                      </td>
                      <td>
                        <StatusBadge status={quote.status} />
                      </td>
                      <td>
                        <Link
                          aria-label="查看報價"
                          className="button button--ghost icon-button"
                          href={`/quotes/${quote.id}`}
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
              action={
                <Button onClick={() => setOpen(true)} variant="primary">
                  <Plus size={16} />
                  新增報價
                </Button>
              }
              detail="建立報價後加入設備及服務明細。"
              title="目前沒有符合的報價"
            />
          </section>
        )}
      </div>

      <Modal
        description="先建立報價抬頭，再於明細頁加入設備及收費項目。"
        onClose={() => setOpen(false)}
        open={open}
        title="新增報價"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={createQuote}>
          <div className="form-grid">
            <Field label="客戶">
              <Select
                name="customer"
                onChange={(event) => setCustomerId(Number(event.target.value))}
                required
                value={customerId ?? ""}
              >
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="工地">
              <Select name="site">
                <option value="">未指定</option>
                {visibleSites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="有效期至">
              <Input name="valid_until" required type="date" />
            </Field>
            <Field className="field--full" label="備註">
              <Input name="notes" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={submitting || !customers.length} type="submit" variant="primary">
              建立報價
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
