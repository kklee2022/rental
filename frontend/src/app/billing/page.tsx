"use client";

import {
  Banknote,
  CircleDollarSign,
  FilePlus2,
  Receipt,
  ShieldCheck,
} from "lucide-react";
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
import type {
  BillingReport,
  Deposit,
  Invoice,
  Payment,
  RentalOrder,
} from "@/lib/types";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";

export default function BillingPage() {
  const { tenant, status } = useAuth();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [deposits, setDeposits] = useState<Deposit[]>([]);
  const [orders, setOrders] = useState<RentalOrder[]>([]);
  const [report, setReport] = useState<BillingReport | null>(null);
  const [tab, setTab] = useState<"invoices" | "payments" | "deposits">(
    "invoices",
  );
  const [loading, setLoading] = useState(true);
  const [invoiceOpen, setInvoiceOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [depositOpen, setDepositOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paymentInvoice, setPaymentInvoice] = useState<number | null>(null);

  async function loadBilling() {
    setLoading(true);
    const [
      invoiceResponse,
      paymentResponse,
      depositResponse,
      orderResponse,
      reportResponse,
    ] = await Promise.all([
      api.GET("/api/v1/invoices/"),
      api.GET("/api/v1/payments/"),
      api.GET("/api/v1/deposits/"),
      api.GET("/api/v1/rental-orders/"),
      api.GET("/api/v1/reports/billing/"),
    ]);
    if (!invoiceResponse.error) {
      const nextInvoices = invoiceResponse.data?.results ?? [];
      setInvoices(nextInvoices);
      const open = nextInvoices.find((invoice) =>
        ["issued", "partially_paid"].includes(invoice.status),
      );
      setPaymentInvoice((current) => current ?? open?.id ?? null);
    }
    if (!paymentResponse.error)
      setPayments(paymentResponse.data?.results ?? []);
    if (!depositResponse.error)
      setDeposits(depositResponse.data?.results ?? []);
    if (!orderResponse.error) setOrders(orderResponse.data?.results ?? []);
    if (!reportResponse.error) setReport(reportResponse.data ?? null);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadBilling();
  }, [status, tenant]);

  const openInvoices = useMemo(
    () => invoices.filter((invoice) => ["issued", "partially_paid"].includes(invoice.status)),
    [invoices],
  );
  const eligibleOrders = orders.filter((order) =>
    ["reserved", "active", "completed"].includes(order.status),
  );

  async function createInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("invoice");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/invoices/from-order/", {
      body: {
        order_id: Number(form.get("order_id")),
        invoice_type: String(form.get("invoice_type")) as "final",
        due_days: Number(form.get("due_days") || 30),
      },
    });
    setBusy(null);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "發票建立失敗"));
      return;
    }
    setInvoiceOpen(false);
    await loadBilling();
  }

  async function issueInvoice(invoice: Invoice) {
    setBusy(`issue-${invoice.id}`);
    setError(null);
    const response = await api.POST("/api/v1/invoices/{id}/issue/", {
      params: { path: { id: invoice.id } },
    });
    setBusy(null);
    const issueError = responseError(response);
    if (issueError) {
      setError(apiErrorMessage(issueError, "發票發出失敗"));
      return;
    }
    await loadBilling();
  }

  async function recordPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("payment");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/payments/record/", {
      body: {
        invoice_id: Number(form.get("invoice_id")),
        amount: String(form.get("amount")),
        method: String(form.get("method")) as "bank_transfer",
        reference: String(form.get("reference") ?? ""),
      },
    });
    setBusy(null);
    const paymentError = responseError(response);
    if (paymentError) {
      setError(apiErrorMessage(paymentError, "付款記錄失敗"));
      return;
    }
    setPaymentOpen(false);
    await loadBilling();
  }

  async function recordDeposit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("deposit");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/deposits/record/", {
      body: {
        order_id: Number(form.get("order_id")),
        amount: String(form.get("amount")),
        note: String(form.get("note") ?? ""),
      },
    });
    setBusy(null);
    const depositError = responseError(response);
    if (depositError) {
      setError(apiErrorMessage(depositError, "按金記錄失敗"));
      return;
    }
    setDepositOpen(false);
    await loadBilling();
  }

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Operational finance</span>
            <h2>發票、收款與按金</h2>
            <p>由租約建立應收、記錄付款並追蹤未結餘額。</p>
          </div>
          <div className="detail-actions">
            <Button onClick={() => setDepositOpen(true)}>
              <ShieldCheck size={16} />
              記錄按金
            </Button>
            <Button onClick={() => setInvoiceOpen(true)} variant="primary">
              <FilePlus2 size={16} />
              建立發票
            </Button>
          </div>
        </section>

        <section className="metric-grid">
          <div className="metric">
            <CircleDollarSign size={19} />
            <span>已開票</span>
            <strong>{formatMoney(report?.invoiced)}</strong>
            <small>{invoices.length} 張發票</small>
          </div>
          <div className="metric">
            <Banknote size={19} />
            <span>已收款</span>
            <strong>{formatMoney(report?.paid)}</strong>
            <small>{formatMoney(report?.credits)} 貸項</small>
          </div>
          <div className="metric">
            <Receipt size={19} />
            <span>未結餘額</span>
            <strong>{formatMoney(report?.outstanding)}</strong>
            <small>{openInvoices.length} 張待收</small>
          </div>
          <div className="metric">
            <ShieldCheck size={19} />
            <span>持有按金</span>
            <strong>{formatMoney(report?.held_deposits)}</strong>
            <small>{report?.open_orders ?? 0} 張租約未結</small>
          </div>
        </section>

        <div className="toolbar">
          <div className="segmented">
            <button
              data-active={tab === "invoices"}
              onClick={() => setTab("invoices")}
              type="button"
            >
              發票
            </button>
            <button
              data-active={tab === "payments"}
              onClick={() => setTab("payments")}
              type="button"
            >
              付款
            </button>
            <button
              data-active={tab === "deposits"}
              onClick={() => setTab("deposits")}
              type="button"
            >
              按金
            </button>
          </div>
          {openInvoices.length ? (
            <Button
              onClick={() => {
                setPaymentInvoice(openInvoices[0].id);
                setPaymentOpen(true);
              }}
            >
              <Banknote size={16} />
              記錄付款
            </Button>
          ) : null}
        </div>

        {error ? <ErrorBanner>{error}</ErrorBanner> : null}

        {loading ? (
          <LoadingBlock rows={8} />
        ) : tab === "invoices" ? (
          invoices.length ? (
            <section className="panel">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>發票</th>
                      <th>租約 / 客戶</th>
                      <th>到期日</th>
                      <th>總額</th>
                      <th>已收 / 貸項</th>
                      <th>餘額</th>
                      <th>狀態</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <strong>{invoice.number}</strong>
                          <small style={{ display: "block", color: "#75817c" }}>
                            {invoice.invoice_type}
                          </small>
                        </td>
                        <td>
                          {invoice.order_number}
                          <small style={{ display: "block", color: "#75817c" }}>
                            {invoice.customer_name}
                          </small>
                        </td>
                        <td>{formatDate(invoice.due_date)}</td>
                        <td>{formatMoney(invoice.total)}</td>
                        <td>
                          {formatMoney(invoice.amount_paid)} /{" "}
                          {formatMoney(invoice.credit_total)}
                        </td>
                        <td>
                          <strong>{formatMoney(invoice.balance)}</strong>
                        </td>
                        <td>
                          <StatusBadge status={invoice.status} />
                        </td>
                        <td>
                          {invoice.status === "draft" ? (
                            <Button
                              disabled={busy === `issue-${invoice.id}`}
                              onClick={() => void issueInvoice(invoice)}
                              variant="ghost"
                            >
                              發出
                            </Button>
                          ) : ["issued", "partially_paid"].includes(
                              invoice.status,
                            ) ? (
                            <Button
                              onClick={() => {
                                setPaymentInvoice(invoice.id);
                                setPaymentOpen(true);
                              }}
                              variant="ghost"
                            >
                              收款
                            </Button>
                          ) : null}
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
                detail="由已確認租約建立臨時或最終發票。"
                title="尚未建立發票"
              />
            </section>
          )
        ) : tab === "payments" ? (
          payments.length ? (
            <section className="panel">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>時間</th>
                      <th>發票</th>
                      <th>方式</th>
                      <th>參考</th>
                      <th>金額</th>
                      <th>狀態</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>{formatDateTime(payment.received_at)}</td>
                        <td>{payment.invoice_number}</td>
                        <td>{payment.method.replaceAll("_", " ")}</td>
                        <td>{payment.reference || "—"}</td>
                        <td>
                          <strong>{formatMoney(payment.amount)}</strong>
                        </td>
                        <td>
                          <StatusBadge status={payment.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <section className="panel">
              <EmptyState detail="收款後會自動更新發票餘額。" title="尚無付款記錄" />
            </section>
          )
        ) : deposits.length ? (
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>租約</th>
                    <th>金額</th>
                    <th>收取時間</th>
                    <th>抵扣發票</th>
                    <th>狀態</th>
                    <th>備註</th>
                  </tr>
                </thead>
                <tbody>
                  {deposits.map((deposit) => (
                    <tr key={deposit.id}>
                      <td>{deposit.order_number}</td>
                      <td>
                        <strong>{formatMoney(deposit.amount)}</strong>
                      </td>
                      <td>{formatDateTime(deposit.received_at)}</td>
                      <td>{deposit.applied_invoice_number ?? "—"}</td>
                      <td>
                        <StatusBadge status={deposit.status} />
                      </td>
                      <td>{deposit.note || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="panel">
            <EmptyState detail="記錄按金後可在發票收款時抵扣。" title="尚無按金記錄" />
          </section>
        )}
      </div>

      <Modal
        onClose={() => setInvoiceOpen(false)}
        open={invoiceOpen}
        title="由租約建立發票"
      >
        <form className="stack-form" onSubmit={createInvoice}>
          <Field label="租約">
            <Select name="order_id" required>
              {eligibleOrders.map((order) => (
                <option key={order.id} value={order.id}>
                  {order.number} · {order.customer_name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="form-grid">
            <Field label="發票類型">
              <Select defaultValue="final" name="invoice_type">
                <option value="interim">臨時發票</option>
                <option value="final">最終發票</option>
              </Select>
            </Field>
            <Field label="付款期限">
              <Input defaultValue="30" min="0" name="due_days" type="number" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setInvoiceOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "invoice" || !eligibleOrders.length} type="submit" variant="primary">
              建立發票
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setPaymentOpen(false)}
        open={paymentOpen}
        title="記錄收款"
      >
        <form className="stack-form" onSubmit={recordPayment}>
          <Field label="發票">
            <Select
              name="invoice_id"
              onChange={(event) => setPaymentInvoice(Number(event.target.value))}
              required
              value={paymentInvoice ?? ""}
            >
              {openInvoices.map((invoice) => (
                <option key={invoice.id} value={invoice.id}>
                  {invoice.number} · 餘額 {formatMoney(invoice.balance)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="form-grid">
            <Field label="金額">
              <Input min="0.01" name="amount" required step="0.01" type="number" />
            </Field>
            <Field label="付款方式">
              <Select defaultValue="bank_transfer" name="method">
                <option value="bank_transfer">銀行轉帳</option>
                <option value="fps">FPS</option>
                <option value="credit_card">信用卡</option>
                <option value="cash">現金</option>
                <option value="other">其他</option>
              </Select>
            </Field>
            <Field className="field--full" label="參考編號">
              <Input name="reference" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setPaymentOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "payment" || !openInvoices.length} type="submit" variant="primary">
              確認收款
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setDepositOpen(false)}
        open={depositOpen}
        title="記錄按金"
      >
        <form className="stack-form" onSubmit={recordDeposit}>
          <Field label="租約">
            <Select name="order_id" required>
              {orders.map((order) => (
                <option key={order.id} value={order.id}>
                  {order.number} · {order.customer_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="金額">
            <Input min="0.01" name="amount" required step="0.01" type="number" />
          </Field>
          <Field label="備註">
            <Textarea name="note" />
          </Field>
          <div className="form-actions">
            <Button onClick={() => setDepositOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "deposit" || !orders.length} type="submit" variant="primary">
              確認按金
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
