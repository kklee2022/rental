"use client";

import {
  Download,
  FileSpreadsheet,
  FileUp,
  RotateCcw,
  ShieldAlert,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  Select,
  StatusBadge,
  Textarea,
} from "@/components/ui";
import {
  api,
  apiErrorMessage,
  apiMutation,
  apiUpload,
  downloadApiFile,
  responseError,
} from "@/lib/api";
import type { ImportBatch, ImportRow } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

type ImportRowView = Omit<
  ImportRow,
  "validation_errors" | "warnings" | "normalized_data"
> & {
  validation_errors: string[];
  warnings: string[];
  normalized_data: Record<string, unknown>;
};

const importTypes = [
  { value: "location", label: "地點", detail: "倉庫、車場及維修地點" },
  { value: "equipment_model", label: "機型", detail: "類別下的設備型號" },
  { value: "asset", label: "逐台資產", detail: "機身編號、牌照及讀數" },
  { value: "accessory", label: "配件", detail: "配件及相容機型" },
  { value: "meter_reading", label: "期初讀數", detail: "工時及里數" },
] as const;

const activeStatuses = new Set(["uploaded", "validating", "committing"]);

export default function ImportsPage() {
  const { tenant, status } = useAuth();
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [selected, setSelected] = useState<ImportBatch | null>(null);
  const [rows, setRows] = useState<ImportRowView[]>([]);
  const [importType, setImportType] = useState<ImportBatch["import_type"]>(
    "location",
  );
  const [duplicatePolicy, setDuplicatePolicy] =
    useState<ImportBatch["duplicate_policy"]>("error");
  const [file, setFile] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [mappingName, setMappingName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function loadBatches(preferredId?: number) {
    const response = await api.GET("/api/v1/imports/");
    const loadError = responseError(response);
    if (loadError) {
      setError(apiErrorMessage(loadError, "匯入批次載入失敗"));
      return;
    }
    const nextBatches = response.data?.results ?? [];
    setBatches(nextBatches);
    const nextSelected =
      nextBatches.find((batch) => batch.id === preferredId) ??
      nextBatches.find((batch) => batch.id === selected?.id) ??
      nextBatches[0] ??
      null;
    setSelected(nextSelected);
    if (nextSelected) await loadRows(nextSelected.id);
  }

  async function loadRows(batchId: number) {
    const response = await api.GET("/api/v1/import-rows/", {
      params: { query: { batch: batchId } },
    });
    if (!responseError(response)) {
      setRows((response.data?.results ?? []) as ImportRowView[]);
    }
  }

  useEffect(() => {
    if (status !== "authenticated" || !tenant) return;
    setLoading(true);
    void loadBatches().finally(() => setLoading(false));
  }, [status, tenant]);

  useEffect(() => {
    if (!selected || !activeStatuses.has(selected.status)) return;
    const timer = window.setInterval(() => {
      void loadBatches(selected.id);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [selected?.id, selected?.status]);

  const selectedType = useMemo(
    () => importTypes.find((item) => item.value === importType),
    [importType],
  );

  function parseMapping() {
    if (!mappingText.trim()) return {};
    const parsed = JSON.parse(mappingText);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("欄位映射必須是 JSON object");
    }
    return parsed;
  }

  async function upload() {
    if (!file) {
      setError("請先選擇 CSV 或 XLSX 檔案");
      return;
    }
    setBusy("upload");
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("import_type", importType);
      formData.append("duplicate_policy", duplicatePolicy);
      formData.append("column_mapping", JSON.stringify(parseMapping()));
      if (mappingName.trim()) formData.append("mapping_name", mappingName.trim());
      const response = await apiUpload<ImportBatch>("/api/v1/imports/", formData);
      const uploadError = responseError(response);
      if (uploadError || !response.data) {
        setError(apiErrorMessage(uploadError, "匯入上傳失敗"));
        return;
      }
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      await loadBatches(response.data.id);
    } catch (uploadError) {
      setError(
        uploadError instanceof Error ? uploadError.message : "匯入上傳失敗",
      );
    } finally {
      setBusy(null);
    }
  }

  async function runBatchAction(action: "commit" | "cancel" | "undo") {
    if (!selected) return;
    setBusy(action);
    setError(null);
    const response = await apiMutation<ImportBatch>(
      `/api/v1/imports/${selected.id}/${action}/`,
    );
    const actionError = responseError(response);
    setBusy(null);
    if (actionError) {
      setError(apiErrorMessage(actionError, "匯入操作失敗"));
      return;
    }
    await loadBatches(selected.id);
  }

  async function downloadTemplate(format: "xlsx" | "csv") {
    await downloadApiFile(
      `/api/v1/import-templates/${importType}/?file_format=${format}`,
      `${importType}-template.${format}`,
    );
  }

  return (
    <AppShell>
      <div className="page-stack">
        <section className="page-intro">
          <div>
            <span className="eyebrow">Data migration</span>
            <h2>資產資料匯入</h2>
            <p>上傳、映射、驗證、預覽，然後原子提交至營運資料。</p>
          </div>
          <div className="detail-actions">
            <Button onClick={() => void downloadTemplate("csv")}>
              <Download size={16} />
              CSV 範本
            </Button>
            <Button onClick={() => void downloadTemplate("xlsx")} variant="primary">
              <FileSpreadsheet size={16} />
              XLSX 範本
            </Button>
          </div>
        </section>

        {error ? <ErrorBanner>{error}</ErrorBanner> : null}

        <section className="panel import-upload-panel">
          <div className="segmented import-type-tabs">
            {importTypes.map((item) => (
              <button
                data-active={importType === item.value}
                key={item.value}
                onClick={() => setImportType(item.value)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="import-upload-grid">
            <button
              className={`dropzone ${file ? "dropzone--ready" : ""}`}
              onClick={() => fileInput.current?.click()}
              type="button"
            >
              <UploadCloud size={26} />
              <strong>{file?.name ?? "選擇 CSV 或 XLSX"}</strong>
              <span>{selectedType?.detail}</span>
              <small>最多 10 MB、5,000 列</small>
            </button>
            <input
              accept=".csv,.xlsx"
              hidden
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              ref={fileInput}
              type="file"
            />
            <div className="import-options">
              <Field label="重複資料處理">
                <Select
                  onChange={(event) =>
                    setDuplicatePolicy(
                      event.target.value as ImportBatch["duplicate_policy"],
                    )
                  }
                  value={duplicatePolicy}
                >
                  <option value="error">有重複即報錯</option>
                  <option value="update">更新既有資料</option>
                  <option value="skip">略過既有資料</option>
                </Select>
              </Field>
              <Field label="映射名稱">
                <Input
                  onChange={(event) => setMappingName(event.target.value)}
                  placeholder="可選，例如：舊系統地點"
                  value={mappingName}
                />
              </Field>
              <Field
                hint="可選 JSON，例如 {&quot;code&quot;:&quot;Location ID&quot;}"
                label="自訂欄位映射"
              >
                <Textarea
                  onChange={(event) => setMappingText(event.target.value)}
                  placeholder='{"code":"Location ID","name":"Location Name"}'
                  value={mappingText}
                />
              </Field>
              <Button
                disabled={busy === "upload"}
                onClick={() => void upload()}
                variant="primary"
              >
                <FileUp size={16} />
                {busy === "upload" ? "上傳中" : "上傳並驗證"}
              </Button>
            </div>
          </div>
        </section>

        <div className="import-workspace">
          <section className="panel">
            <header className="panel__header">
              <div>
                <span className="eyebrow">Import history</span>
                <h3>匯入批次</h3>
              </div>
              <span className="inline-note">{batches.length} 個批次</span>
            </header>
            {loading ? (
              <LoadingBlock rows={5} />
            ) : batches.length ? (
              <div className="import-batch-list">
                {batches.map((batch) => (
                  <button
                    className={`import-batch-row ${
                      selected?.id === batch.id ? "import-batch-row--active" : ""
                    }`}
                    key={batch.id}
                    onClick={() => {
                      setSelected(batch);
                      void loadRows(batch.id);
                    }}
                    type="button"
                  >
                    <span className="import-file-icon">
                      <FileSpreadsheet size={17} />
                    </span>
                    <span>
                      <strong>{batch.original_filename}</strong>
                      <small>
                        {batch.import_type_label} ·{" "}
                        {formatDateTime(batch.created_at)}
                      </small>
                    </span>
                    <span>
                      <StatusBadge status={batch.status} />
                      <small>
                        {batch.total_rows} 列 · {batch.error_rows} 錯誤
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                detail="下載範本後上傳 CSV 或 XLSX。"
                title="尚未有匯入批次"
              />
            )}
          </section>

          <section className="panel">
            <header className="panel__header">
              <div>
                <span className="eyebrow">Preview</span>
                <h3>{selected?.original_filename ?? "批次預覽"}</h3>
              </div>
              {selected ? <StatusBadge status={selected.status} /> : null}
            </header>
            {selected ? (
              <>
                <div className="import-summary">
                  <div>
                    <span>總列數</span>
                    <strong>{selected.total_rows}</strong>
                  </div>
                  <div>
                    <span>可提交</span>
                    <strong>{selected.valid_rows}</strong>
                  </div>
                  <div>
                    <span>警告</span>
                    <strong>{selected.warning_rows}</strong>
                  </div>
                  <div className={selected.error_rows ? "is-error" : ""}>
                    <span>錯誤</span>
                    <strong>{selected.error_rows}</strong>
                  </div>
                </div>
                {selected.failure_message ? (
                  <div className="inline-note">{selected.failure_message}</div>
                ) : null}
                <div className="import-actions">
                  {selected.can_commit ? (
                    <Button
                      disabled={busy === "commit"}
                      onClick={() => void runBatchAction("commit")}
                      variant="primary"
                    >
                      <FileUp size={15} />
                      確認提交
                    </Button>
                  ) : null}
                  {["uploaded", "failed", "preview_ready"].includes(
                    selected.status,
                  ) ? (
                    <Button
                      disabled={busy === "cancel"}
                      onClick={() => void runBatchAction("cancel")}
                      variant="danger"
                    >
                      <XCircle size={15} />
                      取消批次
                    </Button>
                  ) : null}
                  {selected.can_undo ? (
                    <Button
                      disabled={busy === "undo"}
                      onClick={() => void runBatchAction("undo")}
                    >
                      <RotateCcw size={15} />
                      撤銷
                    </Button>
                  ) : null}
                  {rows.some(
                    (row) =>
                      row.validation_errors.length > 0 || row.warnings.length > 0,
                  ) ? (
                    <Button
                      onClick={() =>
                        void downloadApiFile(
                          `/api/v1/imports/${selected.id}/error-report/`,
                          `import-errors-${selected.id}.csv`,
                        )
                      }
                    >
                      <ShieldAlert size={15} />
                      錯誤報告
                    </Button>
                  ) : null}
                </div>
                <div className="table-wrap import-preview-table">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>列</th>
                        <th>動作</th>
                        <th>資料摘要</th>
                        <th>驗證</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 100).map((row) => (
                        <tr key={row.id}>
                          <td>{row.row_number}</td>
                          <td>
                            <StatusBadge
                              status={
                                row.action === "error" ? "rejected" : row.action
                              }
                            />
                          </td>
                          <td>
                            {Object.entries(row.normalized_data)
                              .slice(0, 3)
                              .map(([key, value]) => `${key}: ${value}`)
                              .join(" · ")}
                          </td>
                          <td>
                            {row.validation_errors.length ? (
                              <span className="import-row-errors">
                                {row.validation_errors.join("; ")}
                              </span>
                            ) : row.warnings.length ? (
                              <span className="import-row-warning">
                                {row.warnings.join("; ")}
                              </span>
                            ) : (
                              <span className="import-row-valid">可提交</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <EmptyState
                detail="選取批次後可查看逐列差異。"
                title="尚未選取批次"
              />
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
