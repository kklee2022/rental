"use client";

import {
  ArrowLeft,
  CheckCircle2,
  FileCheck2,
  Plus,
  Send,
  ShoppingCart,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
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
} from "@/components/ui";
import { api, apiErrorMessage, responseError } from "@/lib/api";
import type {
  Asset,
  EquipmentModel,
  Quote,
  RatePlan,
} from "@/lib/types";
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  titleCase,
  toDateTimeLocal,
} from "@/lib/format";

export default function QuoteDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { tenant, status } = useAuth();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [models, setModels] = useState<EquipmentModel[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [ratePlans, setRatePlans] = useState<RatePlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lineOpen, setLineOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<number | null>(null);

  const quoteId = Number(params.id);

  async function loadQuote() {
    if (!quoteId) return;
    setLoading(true);
    const [quoteResponse, modelResponse, assetResponse, planResponse] =
      await Promise.all([
        api.GET("/api/v1/quotes/{id}/", { params: { path: { id: quoteId } } }),
        api.GET("/api/v1/equipment-models/"),
        api.GET("/api/v1/assets/"),
        api.GET("/api/v1/rate-plans/"),
      ]);
    const loadError = responseError(quoteResponse);
    if (loadError) {
      setError(apiErrorMessage(loadError, "報價載入失敗"));
    } else {
      setQuote(quoteResponse.data ?? null);
    }
    if (!modelResponse.error) {
      const nextModels = modelResponse.data?.results ?? [];
      setModels(nextModels);
      setSelectedModel((current) => current ?? nextModels[0]?.id ?? null);
    }
    if (!assetResponse.error) setAssets(assetResponse.data?.results ?? []);
    if (!planResponse.error) setRatePlans(planResponse.data?.results ?? []);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadQuote();
  }, [status, tenant, quoteId]);

  async function runAction(
    action: "submit" | "approve" | "convert",
  ) {
    if (!quote) return;
    setBusy(action);
    setError(null);
    const response =
      action === "submit"
        ? await api.POST("/api/v1/quotes/{id}/submit/", {
            params: { path: { id: quote.id } },
          })
        : action === "approve"
          ? await api.POST("/api/v1/quotes/{id}/approve/", {
              params: { path: { id: quote.id } },
            })
          : await api.POST("/api/v1/quotes/{id}/convert/", {
              params: { path: { id: quote.id } },
            });
    setBusy(null);
    const actionError = responseError(response);
    if (actionError) {
      setError(apiErrorMessage(actionError, "操作失敗"));
      return;
    }
    if (action === "convert" && response.data && "id" in response.data) {
      router.push(`/orders/${response.data.id}`);
      return;
    }
    await loadQuote();
  }

  async function addLine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quote) return;
    setBusy("line");
    setError(null);
    const form = new FormData(event.currentTarget);
    const modelId = Number(form.get("equipment_model"));
    const assetValue = form.get("asset");
    const planValue = form.get("rate_plan");
    const startAt = new Date(String(form.get("start_at")));
    const endAt = new Date(String(form.get("end_at")));
    const response = await api.POST("/api/v1/quote-lines/", {
      body: {
        quote: quote.id,
        line_type: String(form.get("line_type")) as "equipment",
        description: String(form.get("description")),
        equipment_model: modelId || null,
        asset: assetValue ? Number(assetValue) : null,
        rate_plan: planValue ? Number(planValue) : null,
        quantity: String(form.get("quantity") || "1"),
        start_at: startAt.toISOString(),
        end_at: endAt.toISOString(),
        pricing_unit: String(form.get("pricing_unit")) as "day",
        unit_price: form.get("unit_price")
          ? String(form.get("unit_price"))
          : null,
        discount_amount: String(form.get("discount_amount") || "0"),
        sort_order: quote.lines?.length ?? 0,
      },
    });
    setBusy(null);
    const lineError = responseError(response);
    if (lineError) {
      setError(apiErrorMessage(lineError, "明細建立失敗"));
      return;
    }
    setLineOpen(false);
    await loadQuote();
  }

  if (loading) {
    return (
      <AppShell>
        <LoadingBlock rows={8} />
      </AppShell>
    );
  }
  if (!quote) {
    return (
      <AppShell>
        <ErrorBanner>{error ?? "找不到報價"}</ErrorBanner>
      </AppShell>
    );
  }

  const canApprove = ["owner", "admin"].includes(
    tenant?.membership.role ?? "",
  );
  const visibleAssets = assets.filter(
    (asset) => asset.model === selectedModel,
  );
  const now = new Date();
  now.setDate(now.getDate() + 1);
  now.setHours(9, 0, 0, 0);
  const defaultEnd = new Date(now);
  defaultEnd.setDate(defaultEnd.getDate() + 2);

  return (
    <AppShell>
      <div className="page-stack">
        <Link className="text-link" href="/quotes">
          <ArrowLeft size={15} /> 返回報價
        </Link>
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}

        <section className="detail-header">
          <div>
            <span className="eyebrow">Quote</span>
            <h2>{quote.number}</h2>
            <p>
              {quote.customer_name} · {quote.site_name ?? "未指定工地"}
            </p>
          </div>
          <div className="detail-actions">
            <StatusBadge status={quote.status} />
            {["draft", "rejected"].includes(quote.status) ? (
              <Button
                disabled={busy === "submit" || !quote.lines?.length}
                onClick={() => void runAction("submit")}
              >
                <Send size={15} />
                提交審批
              </Button>
            ) : null}
            {quote.status === "pending_approval" && canApprove ? (
              <Button
                disabled={busy === "approve"}
                onClick={() => void runAction("approve")}
                variant="primary"
              >
                <CheckCircle2 size={15} />
                批准報價
              </Button>
            ) : null}
            {quote.status === "approved" ? (
              <Button
                disabled={busy === "convert"}
                onClick={() => void runAction("convert")}
                variant="primary"
              >
                <ShoppingCart size={15} />
                轉為租約
              </Button>
            ) : null}
          </div>
        </section>

        <div className="detail-grid">
          <div className="detail-main">
            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Line items</span>
                  <h3>收費明細</h3>
                </div>
                {quote.status === "draft" ? (
                  <Button onClick={() => setLineOpen(true)} variant="primary">
                    <Plus size={15} />
                    加入明細
                  </Button>
                ) : null}
              </header>
              <div className="line-items">
                {quote.lines?.map((line) => (
                  <div className="line-item" key={line.id}>
                    <div>
                      <strong>{line.description}</strong>
                      <small>
                        {line.equipment_model_name ||
                          titleCase(line.line_type)}
                        {line.asset_number ? ` · ${line.asset_number}` : ""}
                      </small>
                      <small>
                        {formatDateTime(line.start_at)} →{" "}
                        {formatDateTime(line.end_at)}
                      </small>
                    </div>
                    <div>
                      <span>{formatNumber(line.quantity)} 單位</span>
                      <small>{formatMoney(line.unit_price)} / 單位</small>
                    </div>
                    <div className="line-item__amount">
                      <strong>{formatMoney(line.line_total)}</strong>
                      <small>稅 {formatMoney(line.tax_amount)}</small>
                    </div>
                  </div>
                ))}
                {!quote.lines?.length ? (
                  <div className="table-empty">尚未加入收費明細</div>
                ) : null}
              </div>
              <div className="totals">
                <div>
                  <span>小計</span>
                  <span>{formatMoney(quote.subtotal)}</span>
                </div>
                <div>
                  <span>折扣</span>
                  <span>-{formatMoney(quote.discount_total)}</span>
                </div>
                <div>
                  <span>稅項</span>
                  <span>{formatMoney(quote.tax_total)}</span>
                </div>
                <div>
                  <span>總額</span>
                  <span>{formatMoney(quote.total)}</span>
                </div>
              </div>
            </section>
          </div>

          <aside className="detail-side">
            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Terms</span>
                  <h3>報價資料</h3>
                </div>
              </header>
              <dl className="definition-list">
                <div>
                  <dt>客戶</dt>
                  <dd>{quote.customer_name}</dd>
                </div>
                <div>
                  <dt>工地</dt>
                  <dd>{quote.site_name ?? "—"}</dd>
                </div>
                <div>
                  <dt>有效期</dt>
                  <dd>{quote.valid_until ?? "—"}</dd>
                </div>
                <div>
                  <dt>幣別</dt>
                  <dd>{quote.currency}</dd>
                </div>
                <div>
                  <dt>按金</dt>
                  <dd>{formatMoney(quote.deposit_total)}</dd>
                </div>
                <div>
                  <dt>審批</dt>
                  <dd>{quote.approved_by_username ?? "未批"}</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <div className="status-list">
                <div className="timeline">
                  <div className="timeline-item">
                    <span className="timeline-item__dot" />
                    <div>
                      <strong>建立報價</strong>
                      <span>{formatDateTime(quote.created_at)}</span>
                    </div>
                  </div>
                  {quote.approved_at ? (
                    <div className="timeline-item">
                      <span className="timeline-item__dot" />
                      <div>
                        <strong>批准</strong>
                        <span>{formatDateTime(quote.approved_at)}</span>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          </aside>
        </div>
      </div>

      <Modal
        description="租金會依價單及收費元件重新計算。"
        onClose={() => setLineOpen(false)}
        open={lineOpen}
        title="加入收費明細"
        width="720px"
      >
        <form className="stack-form" onSubmit={addLine}>
          <div className="form-grid">
            <Field label="明細類型">
              <Select defaultValue="equipment" name="line_type">
                <option value="equipment">設備租金</option>
                <option value="operator">操作員</option>
                <option value="delivery">運輸</option>
                <option value="accessory">配件</option>
                <option value="site">場地</option>
                <option value="risk">風險 / 保險</option>
              </Select>
            </Field>
            <Field label="描述">
              <Input name="description" required />
            </Field>
            <Field label="設備型號">
              <Select
                name="equipment_model"
                onChange={(event) => setSelectedModel(Number(event.target.value))}
                value={selectedModel ?? ""}
              >
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="指定資產">
              <Select name="asset">
                <option value="">自動分配</option>
                {visibleAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.asset_number}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="價單">
              <Select name="rate_plan">
                <option value="">手動價格</option>
                {ratePlans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="計價單位">
              <Select defaultValue="day" name="pricing_unit">
                <option value="hour">小時</option>
                <option value="day">日</option>
                <option value="week">週</option>
                <option value="month">月</option>
                <option value="fixed">固定</option>
                <option value="per_unit">按量</option>
              </Select>
            </Field>
            <Field label="開始時間">
              <Input
                defaultValue={toDateTimeLocal(now)}
                name="start_at"
                required
                type="datetime-local"
              />
            </Field>
            <Field label="結束時間">
              <Input
                defaultValue={toDateTimeLocal(defaultEnd)}
                name="end_at"
                required
                type="datetime-local"
              />
            </Field>
            <Field label="數量">
              <Input defaultValue="1" min="0" name="quantity" step="0.01" type="number" />
            </Field>
            <Field label="單價">
              <Input min="0" name="unit_price" step="0.01" type="number" />
            </Field>
            <Field label="折扣">
              <Input defaultValue="0" min="0" name="discount_amount" step="0.01" type="number" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setLineOpen(false)} type="button">
              取消
            </Button>
            <Button disabled={busy === "line"} type="submit" variant="primary">
              <FileCheck2 size={15} />
              加入並重新計價
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
