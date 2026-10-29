"use client";

import {
  Building2,
  ClipboardList,
  FileText,
  Hash,
  Pencil,
  Plus,
  ReceiptText,
  Settings2,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
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
import { formatDateTime } from "@/lib/format";
import type {
  EquipmentCategory,
  Schemas,
  TenantSettings,
  TenantUser,
} from "@/lib/types";

type SettingsTab = "company" | "users";
type Role = Schemas["RoleEnum"];

const roles: Array<{ value: Role; label: string }> = [
  { value: "owner", label: "Owner" },
  { value: "admin", label: "Administrator" },
  { value: "rental", label: "Sales / rental" },
  { value: "warehouse", label: "Warehouse / fleet" },
  { value: "driver", label: "Driver" },
  { value: "technician", label: "Technician" },
  { value: "finance", label: "Finance" },
  { value: "viewer", label: "Read-only" },
];

const prefixFields: Array<{
  key: keyof Pick<
    TenantSettings,
    | "customer_prefix"
    | "quote_prefix"
    | "rental_prefix"
    | "invoice_prefix"
  >;
  label: string;
  hint: string;
  icon: typeof Hash;
}> = [
  {
    key: "customer_prefix",
    label: "客戶編號 Prefix",
    hint: "例如 CUS",
    icon: Users,
  },
  {
    key: "quote_prefix",
    label: "報價 Prefix",
    hint: "例如 QT",
    icon: FileText,
  },
  {
    key: "rental_prefix",
    label: "租約 Prefix",
    hint: "例如 LEASE",
    icon: ClipboardList,
  },
  {
    key: "invoice_prefix",
    label: "發票 Prefix",
    hint: "例如 BILL",
    icon: ReceiptText,
  },
];

export default function SettingsPage() {
  const { status, tenant, currentTenant, refresh } = useAuth();
  const [tab, setTab] = useState<SettingsTab>("company");
  const [categories, setCategories] = useState<EquipmentCategory[]>([]);
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [prefixes, setPrefixes] = useState({
    customer_prefix: "C",
    quote_prefix: "Q",
    rental_prefix: "R",
    invoice_prefix: "INV",
  });
  const [categoryModal, setCategoryModal] = useState(false);
  const [editingCategory, setEditingCategory] =
    useState<EquipmentCategory | null>(null);
  const [categoryToDelete, setCategoryToDelete] =
    useState<EquipmentCategory | null>(null);
  const [userModal, setUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<TenantUser | null>(null);
  const [userToDelete, setUserToDelete] = useState<TenantUser | null>(null);

  const canManage = useMemo(
    () => currentTenant?.role === "owner" || currentTenant?.role === "admin",
    [currentTenant],
  );
  const assignableRoles = useMemo(
    () =>
      currentTenant?.role === "owner"
        ? roles
        : roles.filter((role) => role.value !== "owner"),
    [currentTenant],
  );

  async function loadSettings() {
    if (!tenant || !canManage) return;
    setLoading(true);
    const headers = { "X-Tenant": tenant.slug };
    const [settingsResponse, categoryResponse, userResponse] = await Promise.all([
      api.GET("/api/v1/settings/", { headers }),
      api.GET("/api/v1/equipment-categories/", { headers }),
      api.GET("/api/v1/users/", { headers }),
    ]);
    const loadError =
      responseError(settingsResponse) ??
      responseError(categoryResponse) ??
      responseError(userResponse);
    if (loadError) {
      setError(apiErrorMessage(loadError, "設定載入失敗"));
      setLoading(false);
      return;
    }
    const nextSettings = settingsResponse.data ?? null;
    setCategories(categoryResponse.data?.results ?? []);
    setUsers(userResponse.data?.results ?? []);
    if (nextSettings) {
      setCompanyName(nextSettings.company_name);
      setPrefixes({
        customer_prefix: nextSettings.customer_prefix,
        quote_prefix: nextSettings.quote_prefix,
        rental_prefix: nextSettings.rental_prefix,
        invoice_prefix: nextSettings.invoice_prefix,
      });
    }
    setError(null);
    setLoading(false);
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant || !canManage) {
      setLoading(false);
      return;
    }
    void loadSettings();
  }, [status, tenant, canManage]);

  async function saveCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    const response = await api.PATCH("/api/v1/settings/", {
      headers: { "X-Tenant": tenant.slug },
      body: {
        company_name: companyName,
        ...prefixes,
      },
    });
    setSaving(false);
    const saveError = responseError(response);
    if (saveError) {
      setError(apiErrorMessage(saveError, "公司設定儲存失敗"));
      return;
    }
    setNotice("公司設定已儲存");
    await refresh();
    await loadSettings();
  }

  async function saveCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant) return;
    setSaving(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const body = {
      code: String(form.get("code")),
      name: String(form.get("name")),
      prefix: String(form.get("prefix")),
      description: String(form.get("description") ?? ""),
    };
    const response = editingCategory
      ? await api.PATCH("/api/v1/equipment-categories/{id}/", {
          headers: { "X-Tenant": tenant.slug },
          params: { path: { id: editingCategory.id } },
          body,
        })
      : await api.POST("/api/v1/equipment-categories/", {
          headers: { "X-Tenant": tenant.slug },
          body,
        });
    setSaving(false);
    const saveError = responseError(response);
    if (saveError) {
      setError(apiErrorMessage(saveError, "資產類別儲存失敗"));
      return;
    }
    setCategoryModal(false);
    setEditingCategory(null);
    setNotice("資產類別已儲存");
    await loadSettings();
  }

  async function deleteCategory() {
    if (!tenant || !categoryToDelete) return;
    setSaving(true);
    setError(null);
    const response = await api.DELETE("/api/v1/equipment-categories/{id}/", {
      headers: { "X-Tenant": tenant.slug },
      params: { path: { id: categoryToDelete.id } },
    });
    setSaving(false);
    const deleteError = responseError(response);
    if (deleteError) {
      setError(apiErrorMessage(deleteError, "資產類別刪除失敗"));
      return;
    }
    setCategoryToDelete(null);
    setNotice("資產類別已刪除");
    await loadSettings();
  }

  async function saveUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant) return;
    setSaving(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const body: Record<string, unknown> = {
      email: String(form.get("email") ?? ""),
      role: String(form.get("role")) as Role,
      is_active: form.get("is_active") === "on",
    };
    if (password) body.password = password;
    if (!editingUser) body.username = String(form.get("username") ?? "");
    const response = editingUser
      ? await api.PATCH("/api/v1/users/{id}/", {
          headers: { "X-Tenant": tenant.slug },
          params: { path: { id: editingUser.id } },
          body,
        })
      : await api.POST("/api/v1/users/", {
          headers: { "X-Tenant": tenant.slug },
          body,
        });
    setSaving(false);
    const saveError = responseError(response);
    if (saveError) {
      setError(apiErrorMessage(saveError, "用戶儲存失敗"));
      return;
    }
    setUserModal(false);
    setEditingUser(null);
    setNotice(editingUser ? "用戶資料已更新" : "用戶已建立");
    await loadSettings();
  }

  async function deleteUser() {
    if (!tenant || !userToDelete) return;
    setSaving(true);
    setError(null);
    const response = await api.DELETE("/api/v1/users/{id}/", {
      headers: { "X-Tenant": tenant.slug },
      params: { path: { id: userToDelete.id } },
    });
    setSaving(false);
    const deleteError = responseError(response);
    if (deleteError) {
      setError(apiErrorMessage(deleteError, "用戶移除失敗"));
      return;
    }
    setUserToDelete(null);
    setNotice("用戶已從本公司移除");
    await loadSettings();
  }

  if (!canManage && status === "authenticated") {
    return (
      <AppShell>
        <ErrorBanner>只有 Owner 或 Administrator 可以管理公司設定及用戶。</ErrorBanner>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="page-stack settings-page">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Tenant administration</span>
            <h2>公司設定與用戶</h2>
            <p>管理公司身份、編號規則、資產類別及存取權限。</p>
          </div>
        </section>

        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        {notice ? (
          <div className="field-notice">
            <ShieldCheck size={16} />
            {notice}
          </div>
        ) : null}

        <div className="field-tabs settings-tabs">
          <button
            data-active={tab === "company"}
            onClick={() => setTab("company")}
            type="button"
          >
            公司設定
          </button>
          <button
            data-active={tab === "users"}
            onClick={() => setTab("users")}
            type="button"
          >
            用戶管理
          </button>
        </div>

        {loading ? (
          <section className="panel">
            <LoadingBlock rows={6} />
          </section>
        ) : null}

        {!loading && tab === "company" ? (
          <div className="settings-company-layout">
            <section className="panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Company identity</span>
                  <h3>公司及編號</h3>
                </div>
                <Building2 size={19} />
              </header>
              <form className="field-form" onSubmit={saveCompany}>
                <Field label="本公司名稱">
                  <Input
                    onChange={(event) => setCompanyName(event.target.value)}
                    required
                    value={companyName}
                  />
                </Field>
                <div className="settings-prefix-grid">
                  {prefixFields.map((item) => {
                    const Icon = item.icon;
                    return (
                      <Field hint="1-12 位，只可使用英文字母、數字及連字號" key={item.key} label={item.label}>
                        <div className="settings-prefix-input">
                          <Icon size={16} />
                          <Input
                            maxLength={12}
                            onChange={(event) =>
                              setPrefixes((current) => ({
                                ...current,
                                [item.key]: event.target.value.toUpperCase(),
                              }))
                            }
                            pattern="[A-Za-z0-9][A-Za-z0-9-]{0,11}"
                            required
                            value={prefixes[item.key]}
                          />
                        </div>
                      </Field>
                    );
                  })}
                </div>
                <div className="settings-number-preview">
                  <span>編號格式</span>
                  <strong>{prefixes.quote_prefix || "Q"}-2026-000001</strong>
                  <small>文件號碼由 prefix、年份及流水號組成</small>
                </div>
                <div className="form-actions">
                  <Button disabled={saving} type="submit" variant="primary">
                    <Settings2 size={15} />
                    {saving ? "儲存中" : "儲存設定"}
                  </Button>
                </div>
              </form>
            </section>

            <section className="panel settings-category-panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Asset categories</span>
                  <h3>資產類別及 Prefix</h3>
                </div>
                <Button
                  onClick={() => {
                    setEditingCategory(null);
                    setCategoryModal(true);
                  }}
                  variant="primary"
                >
                  <Plus size={15} />
                  新增類別
                </Button>
              </header>
              {categories.length ? (
                <div className="settings-category-list">
                  {categories.map((category) => (
                    <div className="settings-category-row" key={category.id}>
                      <span className="settings-category-mark">
                        <Hash size={16} />
                      </span>
                      <div>
                        <strong>{category.name}</strong>
                        <small>
                          {category.code} · {category.description || "未設定描述"}
                        </small>
                      </div>
                      <span className="settings-prefix-chip">
                        {category.prefix}
                      </span>
                      <div className="settings-row-actions">
                        <Button
                          aria-label={`編輯 ${category.name}`}
                          className="icon-button"
                          onClick={() => {
                            setEditingCategory(category);
                            setCategoryModal(true);
                          }}
                          variant="ghost"
                        >
                          <Pencil size={15} />
                        </Button>
                        <Button
                          aria-label={`刪除 ${category.name}`}
                          className="icon-button"
                          onClick={() => setCategoryToDelete(category)}
                          variant="ghost"
                        >
                          <Trash2 size={15} />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  detail="新增類別後即可為資產自動編號。"
                  title="尚未建立資產類別"
                />
              )}
            </section>
          </div>
        ) : null}

        {!loading && tab === "users" ? (
          <section className="panel settings-users-panel">
            <header className="panel__header">
              <div>
                <span className="eyebrow">Company access</span>
                <h3>本公司用戶</h3>
              </div>
              <Button
                onClick={() => {
                  setEditingUser(null);
                  setUserModal(true);
                }}
                variant="primary"
              >
                <UserPlus size={15} />
                新增用戶
              </Button>
            </header>
            {users.length ? (
              <div className="table-wrap">
                <table className="data-table settings-user-table">
                  <thead>
                    <tr>
                      <th>用戶</th>
                      <th>角色</th>
                      <th>狀態</th>
                      <th>最近登入</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => (
                      <tr key={user.id}>
                        <td>
                          <strong>{user.username}</strong>
                          <small>{user.email || "未設定電郵"}</small>
                        </td>
                        <td>
                          <span className="settings-role">
                            <ShieldCheck size={14} />
                            {roles.find((role) => role.value === user.role)?.label ??
                              user.role}
                          </span>
                        </td>
                        <td>
                          <StatusBadge
                            status={user.is_active ? "active" : "cancelled"}
                          />
                        </td>
                        <td>{formatDateTime(user.last_login)}</td>
                        <td>
                          <div className="settings-row-actions">
                            <Button
                              aria-label={`編輯 ${user.username}`}
                              className="icon-button"
                              onClick={() => {
                                setEditingUser(user);
                                setUserModal(true);
                              }}
                              variant="ghost"
                            >
                              <Pencil size={15} />
                            </Button>
                            <Button
                              aria-label={`移除 ${user.username}`}
                              className="icon-button"
                              onClick={() => setUserToDelete(user)}
                              variant="ghost"
                            >
                              <Trash2 size={15} />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                detail="建立用戶並指派租戶內角色。"
                title="尚未建立用戶"
              />
            )}
          </section>
        ) : null}
      </div>

      <Modal
        description="Prefix 會用於自動產生的資產編號。"
        onClose={() => setCategoryModal(false)}
        open={categoryModal}
        title={editingCategory ? "編輯資產類別" : "新增資產類別"}
      >
        <form className="stack-form" onSubmit={saveCategory}>
          <div className="form-grid">
            <Field label="類別代碼">
              <Input
                defaultValue={editingCategory?.code ?? ""}
                name="code"
                required
              />
            </Field>
            <Field label="類別名稱">
              <Input
                defaultValue={editingCategory?.name ?? ""}
                name="name"
                required
              />
            </Field>
            <Field className="field--full" hint="例如 EXC、LIFT、PWR" label="資產 Prefix">
              <Input
                defaultValue={editingCategory?.prefix ?? ""}
                maxLength={12}
                name="prefix"
                pattern="[A-Za-z0-9][A-Za-z0-9-]{0,11}"
                required
              />
            </Field>
            <Field className="field--full" label="描述">
              <Textarea
                defaultValue={editingCategory?.description ?? ""}
                name="description"
              />
            </Field>
          </div>
          <div className="form-actions">
            <Button onClick={() => setCategoryModal(false)} type="button">
              取消
            </Button>
            <Button disabled={saving} type="submit" variant="primary">
              {saving ? "儲存中" : "儲存類別"}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        description="角色決定用戶可查看及操作的業務範圍。"
        onClose={() => setUserModal(false)}
        open={userModal}
        title={editingUser ? "編輯用戶" : "新增用戶"}
      >
        <form className="stack-form" onSubmit={saveUser}>
          <div className="form-grid">
            <Field label="用戶名稱">
              <Input
                defaultValue={editingUser?.username ?? ""}
                name="username"
                readOnly={Boolean(editingUser)}
                required={!editingUser}
              />
            </Field>
            <Field label="電郵">
              <Input
                defaultValue={editingUser?.email ?? ""}
                name="email"
                type="email"
              />
            </Field>
            <Field label="角色">
              <Select defaultValue={editingUser?.role ?? "warehouse"} name="role">
                {assignableRoles.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              hint={editingUser ? "留空則不變更" : "至少 8 位"}
              label="密碼"
            >
              <Input
                autoComplete="new-password"
                minLength={8}
                name="password"
                required={!editingUser}
                type="password"
              />
            </Field>
            <label className="field-check field--full">
              <input
                defaultChecked={editingUser?.is_active ?? true}
                name="is_active"
                type="checkbox"
              />
              <span>允許登入及使用此租戶</span>
            </label>
          </div>
          <div className="form-actions">
            <Button onClick={() => setUserModal(false)} type="button">
              取消
            </Button>
            <Button disabled={saving} type="submit" variant="primary">
              {saving ? "儲存中" : "儲存用戶"}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        onClose={() => setCategoryToDelete(null)}
        open={Boolean(categoryToDelete)}
        title="刪除資產類別"
      >
        <p className="settings-confirm-copy">
          確定刪除「{categoryToDelete?.name}」？已被設備型號引用的類別不可刪除。
        </p>
        <div className="form-actions">
          <Button onClick={() => setCategoryToDelete(null)} type="button">
            取消
          </Button>
          <Button
            disabled={saving}
            onClick={() => void deleteCategory()}
            variant="danger"
          >
            <Trash2 size={15} />
            刪除類別
          </Button>
        </div>
      </Modal>

      <Modal
        onClose={() => setUserToDelete(null)}
        open={Boolean(userToDelete)}
        title="移除公司用戶"
      >
        <p className="settings-confirm-copy">
          確定將「{userToDelete?.username}」從本公司移除？其帳戶不會被刪除。
        </p>
        <div className="form-actions">
          <Button onClick={() => setUserToDelete(null)} type="button">
            取消
          </Button>
          <Button
            disabled={saving}
            onClick={() => void deleteUser()}
            variant="danger"
          >
            <Trash2 size={15} />
            移除用戶
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}
