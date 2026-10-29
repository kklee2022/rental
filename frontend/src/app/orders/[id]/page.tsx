"use client";

import {
  ArrowLeft,
  CalendarPlus,
  CheckCircle2,
  FileSignature,
  PackageCheck,
  Truck,
  Undo2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  Button,
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
import type { Contract, RentalOrder } from "@/lib/types";
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  titleCase,
  toDateTimeLocal,
} from "@/lib/format";

type Action = "confirm" | "dispatch" | "return" | "contract" | "sign";

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const { tenant, status } = useAuth();
  const [order, setOrder] = useState<RentalOrder | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renewOpen, setRenewOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [signOpen, setSignOpen] = useState(false);

  const orderId = Number(params.id);

  async function loadOrder() {
    if (!orderId) return;
    setLoading(true);
    const [orderResponse, contractResponse] = await Promise.all([
      api.GET("/api/v1/rental-orders/{id}/", {
        params: { path: { id: orderId } },
      }),
      api.GET("/api/v1/contracts/"),
    ]);
    const loadError = responseError(orderResponse);
    if (loadError) {
      setError(apiErrorMessage(loadError, "租約載入失敗"));
    } else {
      setOrder(orderResponse.data ?? null);
    }
    if (!contractResponse.error) {
      setContract(
        contractResponse.data?.results.find((item) => item.order === orderId) ??
          null,
      );
    }
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadOrder();
  }, [status, tenant, orderId]);

  async function runAction(action: Action) {
    if (!order) return;
    setBusy(action);
    setError(null);
    const response =
      action === "confirm"
        ? await api.POST("/api/v1/rental-orders/{id}/confirm/", {
            params: { path: { id: order.id } },
          })
        : action === "dispatch"
          ? await api.POST("/api/v1/rental-orders/{id}/dispatch/", {
              params: { path: { id: order.id } },
            })
          : action === "return"
            ? await api.POST("/api/v1/rental-orders/{id}/return_rental/", {
                params: { path: { id: order.id } },
              })
            : await api.POST("/api/v1/rental-orders/{id}/issue-contract/", {
                params: { path: { id: order.id } },
              });
    setBusy(null);
    const actionError = responseError(response);
    if (actionError) {
      setError(apiErrorMessage(actionError, "操作失敗"));
      return;
    }
    await loadOrder();
  }

  async function renew(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!order) return;
    setBusy("renew");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/rental-orders/{id}/renew/", {
      params: { path: { id: order.id } },
      body: {
        asset: Number(form.get("asset")),
        start_at: new Date(String(form.get("start_at"))).toISOString(),
        end_at: new Date(String(form.get("end_at"))).toISOString(),
        unit_price: form.get("unit_price")
          ? String(form.get("unit_price"))
          : undefined,
        description: String(form.get("description") || "Rental renewal"),
      },
    });
    setBusy(null);
    const renewError = responseError(response);
    if (renewError) {
      setError(apiErrorMessage(renewError, "續租失敗"));
      return;
    }
    setRenewOpen(false);
    await loadOrder();
  }

  async function cancelOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!order) return;
    setBusy("cancel");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/rental-orders/{id}/cancel/", {
      params: { path: { id: order.id } },
      body: { reason: String(form.get("reason")) },
    });
    setBusy(null);
    const cancelError = responseError(response);
    if (cancelError) {
      setError(apiErrorMessage(cancelError, "取消租約失敗"));
      return;
    }
    setCancelOpen(false);
    await loadOrder();
  }

  async function sign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contract) return;
    setBusy("sign");
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/contracts/{id}/sign/", {
      params: { path: { id: contract.id } },
      body: { signed_by_name: String(form.get("signed_by_name")) },
    });
    setBusy(null);
    const signError = responseError(response);
    if (signError) {
      setError(apiErrorMessage(signError, "合約簽署失敗"));
      return;
    }
    setSignOpen(false);
    await loadOrder();
  }

  if (loading) {
    return (
      <AppShell>
        <LoadingBlock rows={8} />
      </AppShell>
    );
  }
  if (!order) {
    return (
      <AppShell>
        <ErrorBanner>{error ?? "找不到租約"}</ErrorBanner>
      </AppShell>
    );
  }

  const allocatedAssets: Array<{
    id: number;
    label: string;
    status: string;
  }> = (order.lines ?? []).flatMap((line) => {
    if (!line.asset || !line.asset_number) return [];
    return [
      {
        id: line.asset,
        label: line.asset_number,
        status: line.allocations?.[0]?.status ?? "confirmed",
      },
    ];
  });
  const start = new Date(order.end_at);
  const end = new Date(order.end_at);
  end.setDate(end.getDate() + 1);

  return (
    <AppShell>
      <div className="page-stack">
        <Link className="text-link" href="/orders">
          <ArrowLeft size={15} /> 返回租約
        </Link>
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}

        <section className="detail-header">
          <div>
            <span className="eyebrow">Rental order</span>
            <h2>{order.number}</h2>
            <p>
              {order.customer_name} · {order.site_name ?? "未指定工地"}
            </p>
          </div>
          <div className="detail-actions">
            <StatusBadge status={order.status} />
            {order.status === "draft" ? (
              <>
                <Button
                  disabled={busy === "confirm"}
                  onClick={() => void runAction("confirm")}
                  variant="primary"
                >
                  <CheckCircle2 size={15} />
                  確認及分配
                </Button>
                <Button onClick={() => setCancelOpen(true)} variant="danger">
                  <XCircle size={15} />
                  取消
                </Button>
              </>
            ) : null}
            {order.status === "reserved" ? (
              <Button
                disabled={busy === "dispatch"}
                onClick={() => void runAction("dispatch")}
                variant="primary"
              >
                <Truck size={15} />
                出倉
              </Button>
            ) : null}
            {order.status === "active" ? (
              <>
                <Button
                  disabled={busy === "return"}
                  onClick={() => void runAction("return")}
                  variant="primary"
                >
                  <Undo2 size={15} />
                  回倉
                </Button>
                <Button onClick={() => setRenewOpen(true)}>
                  <CalendarPlus size={15} />
                  續租
                </Button>
              </>
            ) : null}
            {["reserved", "active"].includes(order.status) && !contract ? (
              <Button onClick={() => void runAction("contract")}>
                <FileSignature size={15} />
                發出合約
              </Button>
            ) : null}
            {contract?.status === "issued" ? (
              <Button onClick={() => setSignOpen(true)} variant="primary">
                <FileSignature size={15} />
                簽署合約
              </Button>
            ) : null}
          </div>
        </section>

        <div className="detail-grid">
          <div className="detail-main">
            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Allocation</span>
                  <h3>租約明細與資產分配</h3>
                </div>
              </header>
              <div className="line-items">
                {order.lines?.map((line) => (
                  <div className="line-item" key={line.id}>
                    <div>
                      <strong>{line.description}</strong>
                      <small>
                        {line.asset_number || "待分配"} ·{" "}
                        {titleCase(line.line_type)}
                      </small>
                      <small>
                        {formatDateTime(line.start_at)} →{" "}
                        {formatDateTime(line.end_at)}
                      </small>
                    </div>
                    <div>
                      <span>{formatNumber(line.quantity)} 單位</span>
                      <small>
                        {line.allocations?.length ?? 0} 個分配時段
                      </small>
                    </div>
                    <div className="line-item__amount">
                      <strong>{formatMoney(line.line_total)}</strong>
                      <small>稅 {formatMoney(line.tax_amount)}</small>
                    </div>
                  </div>
                ))}
              </div>
              <div className="totals">
                <div>
                  <span>小計</span>
                  <span>{formatMoney(order.subtotal)}</span>
                </div>
                <div>
                  <span>稅項</span>
                  <span>{formatMoney(order.tax_total)}</span>
                </div>
                <div>
                  <span>按金</span>
                  <span>{formatMoney(order.deposit_total)}</span>
                </div>
                <div>
                  <span>租約總額</span>
                  <span>{formatMoney(order.total)}</span>
                </div>
              </div>
            </section>

            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Responsibility chain</span>
                  <h3>租約時間線</h3>
                </div>
              </header>
              <div className="timeline" style={{ padding: "17px" }}>
                <div className="timeline-item">
                  <span className="timeline-item__dot" />
                  <div>
                    <strong>租約建立</strong>
                    <span>{formatDateTime(order.created_at)}</span>
                  </div>
                </div>
                {order.confirmed_at ? (
                  <div className="timeline-item">
                    <span className="timeline-item__dot" />
                    <div>
                      <strong>已確認及分配</strong>
                      <span>{formatDateTime(order.confirmed_at)}</span>
                    </div>
                  </div>
                ) : null}
                {order.dispatched_at ? (
                  <div className="timeline-item">
                    <span className="timeline-item__dot" />
                    <div>
                      <strong>已出倉</strong>
                      <span>{formatDateTime(order.dispatched_at)}</span>
                    </div>
                  </div>
                ) : null}
                {order.returned_at ? (
                  <div className="timeline-item">
                    <span className="timeline-item__dot" />
                    <div>
                      <strong>已回倉</strong>
                      <span>{formatDateTime(order.returned_at)}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>
          </div>

          <aside className="detail-side">
            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Schedule</span>
                  <h3>租期資料</h3>
                </div>
              </header>
              <dl className="definition-list">
                <div>
                  <dt>開始</dt>
                  <dd>{formatDateTime(order.start_at)}</dd>
                </div>
                <div>
                  <dt>結束</dt>
                  <dd>{formatDateTime(order.end_at)}</dd>
                </div>
                <div>
                  <dt>準備緩衝</dt>
                  <dd>{order.prep_buffer_minutes} 分鐘</dd>
                </div>
                <div>
                  <dt>回倉緩衝</dt>
                  <dd>{order.return_buffer_minutes} 分鐘</dd>
                </div>
                <div>
                  <dt>報價</dt>
                  <dd>
                    {order.quote ? (
                      <Link className="table-link" href={`/quotes/${order.quote}`}>
                        #{order.quote}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </dd>
                </div>
                <div>
                  <dt>合約</dt>
                  <dd>{contract ? `v${contract.current_version}` : "未發出"}</dd>
                </div>
              </dl>
            </section>

            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Assigned assets</span>
                  <h3>已分配機械</h3>
                </div>
              </header>
              <div className="status-list">
                {allocatedAssets.length ? (
                  allocatedAssets.map((asset) => (
                    <div className="status-row" key={asset.id}>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <PackageCheck size={15} />
                        {asset.label}
                      </span>
                      <span />
                      <StatusBadge status={asset.status} />
                    </div>
                  ))
                ) : (
                  <span className="inline-note">尚未分配具體資產</span>
                )}
              </div>
            </section>
          </aside>
        </div>
      </div>

      <Modal
        onClose={() => setRenewOpen(false)}
        open={renewOpen}
        title="續租"
        description="續租會建立新的租約行及連續分配時段。"
      >
        <form className="stack-form" onSubmit={renew}>
          <Field label="資產">
            <Select name="asset" required>
              {allocatedAssets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="form-grid">
            <Field label="新開始時間">
              <Input
                defaultValue={toDateTimeLocal(start)}
                name="start_at"
                required
                type="datetime-local"
              />
            </Field>
            <Field label="新結束時間">
              <Input
                defaultValue={toDateTimeLocal(end)}
                name="end_at"
                required
                type="datetime-local"
              />
            </Field>
            <Field label="單價">
              <Input min="0" name="unit_price" step="0.01" type="number" />
            </Field>
            <Field label="描述">
              <Input defaultValue="Rental renewal" name="description" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setRenewOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "renew" || !allocatedAssets.length} type="submit" variant="primary">
              確認續租
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setCancelOpen(false)}
        open={cancelOpen}
        title="取消租約"
      >
        <form className="stack-form" onSubmit={cancelOrder}>
          <Field label="取消原因">
            <Textarea name="reason" required />
          </Field>
          <div className="form-actions">
            <Button onClick={() => setCancelOpen(false)} type="button">
              返回
            </Button>
            <Button disabled={busy === "cancel"} type="submit" variant="danger">
              確認取消租約
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setSignOpen(false)}
        open={signOpen}
        title="簽署合約"
      >
        <form className="stack-form" onSubmit={sign}>
          <Field label="簽署人姓名">
            <Input name="signed_by_name" required />
          </Field>
          <div className="form-actions">
            <Button onClick={() => setSignOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "sign"} type="submit" variant="primary">
              確認簽署
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
