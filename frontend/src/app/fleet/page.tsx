"use client";

import { Gauge, MapPin, Plus, Search } from "lucide-react";
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
  Asset,
  EquipmentCategory,
  EquipmentModel,
  Location,
} from "@/lib/types";
import { formatNumber, titleCase } from "@/lib/format";

const transitionStatuses = [
  "available",
  "reserved",
  "preparing",
  "ready_for_dispatch",
  "in_transit",
  "on_site",
  "paused",
  "pending_collection",
  "return_inspection",
  "maintenance",
  "awaiting_parts",
  "safety_locked",
  "retired",
] as const;

export default function FleetPage() {
  const { tenant, status } = useAuth();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [models, setModels] = useState<EquipmentModel[]>([]);
  const [categories, setCategories] = useState<EquipmentCategory[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [tab, setTab] = useState<"assets" | "models">("assets");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [assetModal, setAssetModal] = useState(false);
  const [modelModal, setModelModal] = useState(false);
  const [categoryModal, setCategoryModal] = useState(false);
  const [transitionAsset, setTransitionAsset] = useState<Asset | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadFleet() {
    setLoading(true);
    const [assetResponse, modelResponse, categoryResponse, locationResponse] =
      await Promise.all([
        api.GET("/api/v1/assets/"),
        api.GET("/api/v1/equipment-models/"),
        api.GET("/api/v1/equipment-categories/"),
        api.GET("/api/v1/locations/"),
      ]);
    if (!assetResponse.error) setAssets(assetResponse.data?.results ?? []);
    if (!modelResponse.error) setModels(modelResponse.data?.results ?? []);
    if (!categoryResponse.error)
      setCategories(categoryResponse.data?.results ?? []);
    if (!locationResponse.error)
      setLocations(locationResponse.data?.results ?? []);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    void loadFleet();
  }, [status, tenant]);

  const filteredAssets = useMemo(() => {
    const term = search.toLocaleLowerCase().trim();
    return assets.filter((asset) => {
      if (!term) return true;
      return [
        asset.asset_number,
        asset.model_name,
        asset.serial_number,
        asset.registration_number,
        asset.status,
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(term);
    });
  }, [assets, search]);

  async function createAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/assets/", {
      body: {
        model: Number(form.get("model")),
        location: form.get("location") ? Number(form.get("location")) : null,
        asset_number: String(form.get("asset_number")),
        serial_number: String(form.get("serial_number") ?? ""),
        registration_number: String(form.get("registration_number") ?? ""),
        qr_code: String(form.get("qr_code") ?? ""),
        current_hours: String(form.get("current_hours") || "0"),
        current_kilometers: String(form.get("current_kilometers") || "0"),
        notes: String(form.get("notes") ?? ""),
      },
    });
    setSubmitting(false);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "資產建立失敗"));
      return;
    }
    setAssetModal(false);
    await loadFleet();
  }

  async function createModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/equipment-models/", {
      body: {
        category: Number(form.get("category")),
        code: String(form.get("code")),
        name: String(form.get("name")),
        manufacturer: String(form.get("manufacturer") ?? ""),
        model_number: String(form.get("model_number") ?? ""),
        specifications: {},
        is_active: true,
      },
    });
    setSubmitting(false);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "型號建立失敗"));
      return;
    }
    setModelModal(false);
    await loadFleet();
  }

  async function createCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/equipment-categories/", {
      body: {
        code: String(form.get("code")),
        name: String(form.get("name")),
        description: String(form.get("description") ?? ""),
      },
    });
    setSubmitting(false);
    const createError = responseError(response);
    if (createError) {
      setError(apiErrorMessage(createError, "類別建立失敗"));
      return;
    }
    setCategoryModal(false);
    await loadFleet();
  }

  async function transition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!transitionAsset) return;
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await api.POST("/api/v1/assets/{id}/transition/", {
      params: { path: { id: transitionAsset.id } },
      body: {
        status: String(form.get("status")) as Asset["status"],
        reason: String(form.get("reason") ?? ""),
        source: "web",
      },
    });
    setSubmitting(false);
    const transitionError = responseError(response);
    if (transitionError) {
      setError(apiErrorMessage(transitionError, "狀態轉換失敗"));
      return;
    }
    setTransitionAsset(null);
    await loadFleet();
  }

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Fleet control</span>
            <h2>逐台機械與可用狀態</h2>
            <p>追蹤機身編號、工時、里數及目前營運狀態。</p>
          </div>
          <div className="detail-actions">
            {tab === "models" ? (
              <Button onClick={() => setCategoryModal(true)}>
                <Plus size={16} />
                新增類別
              </Button>
            ) : null}
            <Button
              onClick={() =>
                tab === "assets" ? setAssetModal(true) : setModelModal(true)
              }
              variant="primary"
            >
              <Plus size={16} />
              {tab === "assets" ? "新增資產" : "新增型號"}
            </Button>
          </div>
        </section>

        <div className="toolbar">
          <div className="toolbar__group">
            <div className="segmented">
              <button
                data-active={tab === "assets"}
                onClick={() => setTab("assets")}
                type="button"
              >
                逐台資產
              </button>
              <button
                data-active={tab === "models"}
                onClick={() => setTab("models")}
                type="button"
              >
                設備型號
              </button>
            </div>
            {tab === "assets" ? (
              <div className="search-box">
                <Search size={16} />
                <Input
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜尋資產、型號或車牌"
                  value={search}
                />
              </div>
            ) : null}
          </div>
          <span className="inline-note">
            {assets.length} 台資產 · {models.length} 個型號
          </span>
        </div>

        {loading ? (
          <LoadingBlock rows={7} />
        ) : tab === "assets" ? (
          filteredAssets.length ? (
            <section className="panel">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>資產</th>
                      <th>型號</th>
                      <th>狀態</th>
                      <th>位置</th>
                      <th>工時</th>
                      <th>里數</th>
                      <th>牌照 / 序號</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAssets.map((asset) => (
                      <tr key={asset.id}>
                        <td>
                          <strong>{asset.asset_number}</strong>
                          <small style={{ display: "block", color: "#75817c" }}>
                            {asset.qr_code || "未設定 QR"}
                          </small>
                        </td>
                        <td>{asset.model_name}</td>
                        <td>
                          <StatusBadge status={asset.status} />
                        </td>
                        <td>
                          <span style={{ display: "inline-flex", gap: 5 }}>
                            <MapPin size={14} />
                            {asset.location_name || "未分配"}
                          </span>
                        </td>
                        <td>
                          <span style={{ display: "inline-flex", gap: 5 }}>
                            <Gauge size={14} />
                            {formatNumber(asset.current_hours)}
                          </span>
                        </td>
                        <td>{formatNumber(asset.current_kilometers)} km</td>
                        <td>
                          {asset.registration_number || "—"}
                          <small style={{ display: "block", color: "#75817c" }}>
                            {asset.serial_number || "—"}
                          </small>
                        </td>
                        <td>
                          <Button
                            disabled={asset.status === "retired"}
                            onClick={() => setTransitionAsset(asset)}
                            variant="ghost"
                          >
                            轉狀態
                          </Button>
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
                detail="先建立設備型號，再逐台加入資產。"
                title={search ? "找不到符合的資產" : "尚未建立資產"}
              />
            </section>
          )
        ) : models.length ? (
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>型號</th>
                    <th>類別</th>
                    <th>製造商</th>
                    <th>型號編號</th>
                    <th>資產數</th>
                    <th>狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((model) => (
                    <tr key={model.id}>
                      <td>
                        <strong>{model.name}</strong>
                        <small style={{ display: "block", color: "#75817c" }}>
                          {model.code}
                        </small>
                      </td>
                      <td>{model.category_name}</td>
                      <td>{model.manufacturer || "—"}</td>
                      <td>{model.model_number || "—"}</td>
                      <td>
                        {assets.filter((asset) => asset.model === model.id).length}
                      </td>
                      <td>
                        <StatusBadge
                          status={model.is_active ? "active" : "retired"}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="panel">
            <EmptyState detail="建立型號後可加入逐台資產。" title="尚未建立型號" />
          </section>
        )}
      </div>

      <Modal
        onClose={() => setAssetModal(false)}
        open={assetModal}
        title="新增資產"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={createAsset}>
          <div className="form-grid">
            <Field label="設備型號">
              <Select name="model" required>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="所在位置">
              <Select name="location">
                <option value="">未分配</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="資產編號">
              <Input name="asset_number" required />
            </Field>
            <Field label="序號">
              <Input name="serial_number" />
            </Field>
            <Field label="車牌">
              <Input name="registration_number" />
            </Field>
            <Field label="QR Code">
              <Input name="qr_code" />
            </Field>
            <Field label="目前工時">
              <Input defaultValue="0" min="0" name="current_hours" step="0.01" type="number" />
            </Field>
            <Field label="目前里數">
              <Input defaultValue="0" min="0" name="current_kilometers" step="0.01" type="number" />
            </Field>
            <Field className="field--full" label="備註">
              <Textarea name="notes" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setAssetModal(false)} type="button">
              取消
            </Button>
            <Button disabled={submitting || !models.length} type="submit" variant="primary">
              建立資產
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setModelModal(false)}
        open={modelModal}
        title="新增設備型號"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={createModel}>
          <div className="form-grid">
            <Field label="類別">
              <Select name="category" required>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="型號代碼">
              <Input name="code" required />
            </Field>
            <Field className="field--full" label="型號名稱">
              <Input name="name" required />
            </Field>
            <Field label="製造商">
              <Input name="manufacturer" />
            </Field>
            <Field label="製造商型號">
              <Input name="model_number" />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setModelModal(false)} type="button">
              取消
            </Button>
            <Button disabled={submitting || !categories.length} type="submit" variant="primary">
              建立型號
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setCategoryModal(false)}
        open={categoryModal}
        title="新增設備類別"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={createCategory}>
          <Field label="類別代碼">
            <Input name="code" required />
          </Field>
          <Field label="類別名稱">
            <Input name="name" required />
          </Field>
          <Field label="說明">
            <Textarea name="description" />
          </Field>
          <div className="form-actions">
            <Button onClick={() => setCategoryModal(false)} type="button">
              取消
            </Button>
            <Button disabled={submitting} type="submit" variant="primary">
              建立類別
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        description={transitionAsset ? `${transitionAsset.asset_number} · ${titleCase(transitionAsset.status)}` : undefined}
        onClose={() => setTransitionAsset(null)}
        open={Boolean(transitionAsset)}
        title="轉換資產狀態"
      >
        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        <form className="stack-form" onSubmit={transition}>
          <Field label="新狀態">
            <Select name="status" required>
              {transitionStatuses.map((item) => (
                <option key={item} value={item}>
                  {titleCase(item)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="原因">
            <Textarea name="reason" placeholder="例如：維修、客戶預約或回倉檢查" />
          </Field>
          <div className="form-actions">
            <Button onClick={() => setTransitionAsset(null)} type="button">
              取消
            </Button>
            <Button disabled={submitting} type="submit" variant="primary">
              確認轉換
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
