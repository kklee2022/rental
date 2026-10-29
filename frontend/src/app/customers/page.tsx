"use client";

import { MapPin, Plus, Search, UserRound } from "lucide-react";
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
  Textarea,
} from "@/components/ui";
import { api, apiErrorMessage, responseError } from "@/lib/api";
import type { Contact, Customer, Site } from "@/lib/types";
import { formatMoney } from "@/lib/format";

export default function CustomersPage() {
  const { tenant, status } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCustomers() {
    setLoading(true);
    const [customerResponse, contactResponse, siteResponse] = await Promise.all([
      api.GET("/api/v1/customers/"),
      api.GET("/api/v1/contacts/"),
      api.GET("/api/v1/sites/"),
    ]);
    if (!customerResponse.error) {
      setCustomers(customerResponse.data?.results ?? []);
    }
    if (!contactResponse.error) setContacts(contactResponse.data?.results ?? []);
    if (!siteResponse.error) setSites(siteResponse.data?.results ?? []);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadCustomers();
  }, [status, tenant]);

  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return customers;
    return customers.filter((customer) =>
      [customer.code, customer.name, customer.email, customer.phone]
        .join(" ")
        .toLocaleLowerCase()
        .includes(term),
    );
  }, [customers, search]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/customers/", {
      body: {
        code: String(form.get("code")),
        name: String(form.get("name")),
        legal_name: String(form.get("legal_name") ?? ""),
        status: String(form.get("status")) as Customer["status"],
        email: String(form.get("email") ?? ""),
        phone: String(form.get("phone") ?? ""),
        billing_address: String(form.get("billing_address") ?? ""),
        credit_limit: String(form.get("credit_limit") || "0"),
        notes: String(form.get("notes") ?? ""),
      },
    });
    setSubmitting(false);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "客戶建立失敗"));
      return;
    }
    setOpen(false);
    await loadCustomers();
  }

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Customer ledger</span>
            <h2>客戶、聯絡人與工地</h2>
            <p>查看租賃關係、信用狀態及服務地點。</p>
          </div>
          <Button onClick={() => setOpen(true)} variant="primary">
            <Plus size={16} />
            新增客戶
          </Button>
        </section>

        <div className="toolbar">
          <div className="toolbar__group">
            <div className="search-box">
              <Search size={16} />
              <Input
                aria-label="搜尋客戶"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜尋名稱、編號、電話或電郵"
                value={search}
              />
            </div>
          </div>
          <span className="inline-note">
            {customers.length} 個客戶 · {sites.length} 個工地
          </span>
        </div>

        {loading ? (
          <LoadingBlock rows={7} />
        ) : filtered.length ? (
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>客戶</th>
                    <th>狀態</th>
                    <th>聯絡方式</th>
                    <th>聯絡人</th>
                    <th>工地</th>
                    <th>信用額度</th>
                    <th>賬單地址</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((customer) => {
                    const customerContacts = contacts.filter(
                      (contact) => contact.customer === customer.id,
                    );
                    const customerSites = sites.filter(
                      (site) => site.customer === customer.id,
                    );
                    return (
                      <tr key={customer.id}>
                        <td>
                          <strong>{customer.name}</strong>
                          <small style={{ display: "block", color: "#75817c" }}>
                            {customer.code}
                          </small>
                        </td>
                        <td>
                          <StatusBadge status={customer.status} />
                        </td>
                        <td>
                          <span>{customer.phone || "—"}</span>
                          <small style={{ display: "block", color: "#75817c" }}>
                            {customer.email || "未設定電郵"}
                          </small>
                        </td>
                        <td>
                          <span style={{ display: "inline-flex", gap: 5 }}>
                            <UserRound size={14} />
                            {customerContacts.length}
                          </span>
                        </td>
                        <td>
                          <span style={{ display: "inline-flex", gap: 5 }}>
                            <MapPin size={14} />
                            {customerSites.length}
                          </span>
                        </td>
                        <td>{formatMoney(customer.credit_limit)}</td>
                        <td>{customer.billing_address || "—"}</td>
                      </tr>
                    );
                  })}
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
                  新增第一位客戶
                </Button>
              }
              detail="建立客戶後即可加入聯絡人、工地及租賃報價。"
              title={search ? "找不到符合的客戶" : "尚未建立客戶"}
            />
          </section>
        )}
      </div>

      <Modal
        description="建立租賃關係及基礎信用資料。"
        onClose={() => setOpen(false)}
        open={open}
        title="新增客戶"
        width="680px"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={handleCreate}>
          <div className="form-grid">
            <Field hint="留空則按公司設定 prefix 自動編號" label="客戶編號">
              <Input name="code" />
            </Field>
            <Field label="客戶名稱">
              <Input name="name" required />
            </Field>
            <Field label="法定名稱">
              <Input name="legal_name" />
            </Field>
            <Field label="狀態">
              <Select defaultValue="active" name="status">
                <option value="active">Active</option>
                <option value="on_hold">On hold</option>
                <option value="blocked">Blocked</option>
              </Select>
            </Field>
            <Field label="電話">
              <Input name="phone" />
            </Field>
            <Field label="電郵">
              <Input name="email" type="email" />
            </Field>
            <Field label="信用額度">
              <Input defaultValue="0" min="0" name="credit_limit" step="0.01" type="number" />
            </Field>
            <Field className="field--full" label="賬單地址">
              <Textarea name="billing_address" />
            </Field>
            <Field className="field--full" label="備註">
              <Textarea name="notes" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={submitting} type="submit" variant="primary">
              {submitting ? "建立中" : "建立客戶"}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
