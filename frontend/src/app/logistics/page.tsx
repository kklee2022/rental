"use client";

import {
  AlertTriangle,
  Camera,
  Check,
  CircleOff,
  CloudOff,
  CloudUpload,
  MapPin,
  PackageCheck,
  QrCode,
  RefreshCw,
  ScanLine,
  Signature,
  Truck,
  Warehouse,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

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
  responseError,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  createClientEventId,
  enqueueRequest,
  listQueuedRequests,
  removeQueuedRequest,
  type QueuedRequest,
} from "@/lib/offline-queue";
import type {
  AssetLogisticsEvent,
  DeliveryReceipt,
  InventoryCount,
  Location,
  LogisticsAttachment,
  MobileLogisticsSummary,
  Schemas,
  TransportJob,
} from "@/lib/types";

type FieldTab = "jobs" | "scan" | "receipt" | "inventory";
type EventType = AssetLogisticsEvent["event_type"];
type JobAction = "start" | "arrive" | "deliver" | "complete" | "cancel";

const tabs: Array<{ value: FieldTab; label: string }> = [
  { value: "jobs", label: "任務" },
  { value: "scan", label: "掃碼" },
  { value: "receipt", label: "交收" },
  { value: "inventory", label: "盤點" },
];

const eventTypes: Array<{ value: EventType; label: string }> = [
  { value: "scan", label: "現場掃碼" },
  { value: "prepare", label: "備貨完成" },
  { value: "load", label: "已裝車" },
  { value: "depart", label: "已離場" },
  { value: "arrive_site", label: "到達工地" },
  { value: "unload", label: "完成卸貨" },
  { value: "deliver", label: "客戶交收" },
  { value: "collect_request", label: "申請收車" },
  { value: "collect", label: "已收車" },
  { value: "receive_warehouse", label: "入倉" },
  { value: "transfer", label: "轉倉" },
  { value: "meter", label: "工時／里數" },
  { value: "exception", label: "異常回報" },
];

const attachmentCategories: Array<{
  value: Schemas["AttachmentCategoryEnum"];
  label: string;
}> = [
  { value: "photo", label: "現場照片" },
  { value: "document", label: "隨車文件" },
  { value: "exception", label: "異常附件" },
];

function queuedLabel(kind: QueuedRequest["kind"]) {
  if (kind === "asset_event") return "掃碼事件";
  if (kind === "delivery_receipt") return "電子簽收";
  if (kind === "inventory_scan") return "盤點掃碼";
  return "任務狀態";
}

function fileSizeLabel(size: number) {
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function SignaturePad({
  value,
  onChange,
  fallbackName,
}: {
  value: string;
  onChange: (value: string) => void;
  fallbackName: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);

  function point(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = event.currentTarget;
    const bounds = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * canvas.width,
      y: ((event.clientY - bounds.top) / bounds.height) * canvas.height,
    };
  }

  function begin(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = event.currentTarget;
    const context = canvas.getContext("2d");
    if (!context) return;
    const location = point(event);
    drawingRef.current = true;
    canvas.setPointerCapture(event.pointerId);
    context.strokeStyle = "#17201d";
    context.lineWidth = 4;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    context.moveTo(location.x, location.y);
  }

  function draw(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    const location = point(event);
    context.lineTo(location.x, location.y);
    context.stroke();
  }

  function end(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    onChange(event.currentTarget.toDataURL("image/png"));
  }

  function clear() {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    onChange("");
  }

  return (
    <div className="signature-pad">
      <canvas
        aria-label="電子簽名"
        className="signature-pad__canvas"
        height={180}
        onPointerCancel={end}
        onPointerDown={begin}
        onPointerMove={draw}
        onPointerUp={end}
        ref={canvasRef}
        width={640}
      />
      <div className="signature-pad__footer">
        <span>{value ? "簽名已擷取" : "請於方格內簽名"}</span>
        <div>
          {!value && fallbackName.trim() ? (
            <Button
              onClick={() => onChange(`typed:${fallbackName.trim()}`)}
              type="button"
              variant="ghost"
            >
              <Signature size={14} />
              以姓名代替簽名
            </Button>
          ) : null}
          <Button disabled={!value} onClick={clear} type="button" variant="ghost">
            <X size={14} />
            清除
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function LogisticsPage() {
  const { status, tenant } = useAuth();
  const [tab, setTab] = useState<FieldTab>("jobs");
  const [jobs, setJobs] = useState<TransportJob[]>([]);
  const [events, setEvents] = useState<AssetLogisticsEvent[]>([]);
  const [counts, setCounts] = useState<InventoryCount[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [summary, setSummary] = useState<MobileLogisticsSummary | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [selectedInventoryId, setSelectedInventoryId] = useState<number | null>(
    null,
  );
  const [inventoryLocationId, setInventoryLocationId] = useState("");
  const [scanValue, setScanValue] = useState("");
  const [inventoryScanValue, setInventoryScanValue] = useState("");
  const [eventType, setEventType] = useState<EventType>("scan");
  const [transferLocationId, setTransferLocationId] = useState("");
  const [eventNotes, setEventNotes] = useState("");
  const [eventFile, setEventFile] = useState<File | null>(null);
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentCategory, setAttachmentCategory] =
    useState<Schemas["AttachmentCategoryEnum"]>("photo");
  const [signerName, setSignerName] = useState("");
  const [signerPhone, setSignerPhone] = useState("");
  const [signatureData, setSignatureData] = useState("");
  const [accepted, setAccepted] = useState(true);
  const [rejectionReason, setRejectionReason] = useState("");
  const [receiptNotes, setReceiptNotes] = useState("");
  const [outbox, setOutbox] = useState<QueuedRequest[]>([]);
  const [online, setOnline] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncingRef = useRef(false);
  const tenantSlug = tenant?.slug ?? null;

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );
  const activeInventory = useMemo(
    () =>
      counts.find((count) => count.id === selectedInventoryId) ??
      counts.find((count) => count.status === "in_progress") ??
      null,
    [counts, selectedInventoryId],
  );
  const selectedEvents = useMemo(
    () =>
      events.filter(
        (event) =>
          !selectedJob || event.job === selectedJob.id || event.actor === null,
      ),
    [events, selectedJob],
  );

  const loadData = useCallback(async () => {
    if (status !== "authenticated" || !tenant) return;
    setLoading(true);
    const headers = { "X-Tenant": tenant.slug };
    const [jobsResponse, eventsResponse, countsResponse, locationsResponse, summaryResponse] =
      await Promise.all([
        api.GET("/api/v1/logistics/jobs/", {
          params: { query: { page: 1 } },
          headers,
        }),
        api.GET("/api/v1/logistics/events/", {
          params: { query: { page: 1 } },
          headers,
        }),
        api.GET("/api/v1/logistics/inventory-counts/", {
          params: { query: { page: 1 } },
          headers,
        }),
        api.GET("/api/v1/locations/", {
          params: { query: { page: 1 } },
          headers,
        }),
        api.GET("/api/v1/logistics/summary/", { headers }),
      ]);
    const loadError =
      responseError(jobsResponse) ??
      responseError(eventsResponse) ??
      responseError(countsResponse) ??
      responseError(locationsResponse) ??
      responseError(summaryResponse);
    if (loadError) {
      setError(apiErrorMessage(loadError, "物流資料載入失敗"));
      setLoading(false);
      return;
    }
    const nextJobs = jobsResponse.data?.results ?? [];
    const nextCounts = countsResponse.data?.results ?? [];
    setJobs(nextJobs);
    setEvents(eventsResponse.data?.results ?? []);
    setCounts(nextCounts);
    setLocations(locationsResponse.data?.results ?? []);
    setSummary(summaryResponse.data ?? null);
    setSelectedJobId((current) =>
      current && nextJobs.some((job) => job.id === current)
        ? current
        : nextJobs[0]?.id ?? null,
    );
    setSelectedInventoryId(
      (current) =>
        nextCounts.find((count) => count.id === current)?.id ??
        nextCounts.find((count) => count.status === "in_progress")?.id ??
        null,
    );
    setInventoryLocationId((current) => current || String(locationsResponse.data?.results[0]?.id ?? ""));
    setError(null);
    setLoading(false);
  }, [status, tenant]);

  const refreshOutbox = useCallback(async () => {
    if (!tenantSlug) return;
    try {
      setOutbox(await listQueuedRequests(tenantSlug));
    } catch {
      setError("無法讀取本機離線佇列");
    }
  }, [tenantSlug]);

  const processQueuedRequest = useCallback(
    async (queued: QueuedRequest) => {
      if (queued.kind === "asset_event") {
        const result = await apiMutation<AssetLogisticsEvent>(
          "/api/v1/logistics/events/",
          { body: queued.payload, tenantSlug: queued.tenantSlug },
        );
        if (responseError(result)) return result.error;
        if (queued.file && queued.payload.job && result.data) {
          const formData = new FormData();
          formData.append("job", String(queued.payload.job));
          formData.append("asset", String(result.data.asset));
          formData.append("category", "photo");
          formData.append("captured_at", result.data.occurred_at);
          formData.append("file", queued.file.blob, queued.file.name);
          const upload = await apiUpload<LogisticsAttachment>(
            "/api/v1/logistics/attachments/",
            formData,
            queued.tenantSlug,
          );
          if (responseError(upload)) return upload.error;
        }
        return null;
      }
      if (queued.kind === "job_action") {
        const result = await apiMutation<TransportJob>(
          `/api/v1/logistics/jobs/${queued.payload.jobId}/${queued.payload.action}/`,
          {
            body: { reason: queued.payload.reason ?? "" },
            tenantSlug: queued.tenantSlug,
          },
        );
        return responseError(result);
      }
      if (queued.kind === "inventory_scan") {
        const result = await apiMutation<InventoryCount>(
          `/api/v1/logistics/inventory-counts/${queued.payload.countId}/scan/`,
          {
            body: {
              asset_identifier: queued.payload.asset_identifier,
              client_event_id: queued.payload.client_event_id,
              notes: queued.payload.notes ?? "",
            },
            tenantSlug: queued.tenantSlug,
          },
        );
        return responseError(result);
      }
      const result = await apiMutation<DeliveryReceipt>(
        "/api/v1/logistics/delivery-receipts/",
        { body: queued.payload, tenantSlug: queued.tenantSlug },
      );
      return responseError(result);
    },
    [],
  );

  const syncOutbox = useCallback(async () => {
    if (!tenantSlug || !navigator.onLine || syncingRef.current) return;
    syncingRef.current = true;
    setSyncing(true);
    let synced = 0;
    let firstError: unknown = null;
    try {
      const queuedRequests = await listQueuedRequests(tenantSlug);
      for (const queued of queuedRequests) {
        const syncError = await processQueuedRequest(queued);
        if (syncError) {
          firstError = syncError;
          break;
        }
        await removeQueuedRequest(queued.id);
        synced += 1;
      }
      await refreshOutbox();
      if (synced) {
        setNotice(`已同步 ${synced} 筆離線記錄`);
        await loadData();
      }
      if (firstError) {
        setError(apiErrorMessage(firstError, "部分離線記錄未能同步"));
      }
    } finally {
      syncingRef.current = false;
      setSyncing(false);
    }
  }, [
    tenantSlug,
    processQueuedRequest,
    refreshOutbox,
    loadData,
  ]);

  useEffect(() => {
    setOnline(navigator.onLine);
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  useEffect(() => {
    void loadData();
    void refreshOutbox();
  }, [loadData, refreshOutbox]);

  useEffect(() => {
    if (!online || !tenantSlug) return;
    void syncOutbox();
  }, [online, tenantSlug, syncOutbox]);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js");
    }
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (detectorTimerRef.current) clearInterval(detectorTimerRef.current);
    };
  }, []);

  async function queueOrShow(
    kind: QueuedRequest["kind"],
    payload: Record<string, unknown>,
    message: string,
    file?: File,
  ) {
    await enqueueRequest({
      tenantSlug: tenant?.slug ?? "",
      kind,
      payload,
      file: file
        ? { name: file.name, type: file.type || "image/jpeg", blob: file }
        : undefined,
    });
    await refreshOutbox();
    setNotice(message);
  }

  async function recordEvent() {
    if (!tenant) return;
    if (!scanValue.trim()) {
      setError("請輸入或掃描資產編號");
      return;
    }
    setBusy("event");
    setError(null);
    setNotice(null);
    const clientEventId = createClientEventId();
    const payload: Record<string, unknown> = {
      job: selectedJob?.id ?? null,
      asset_identifier: scanValue.trim(),
      event_type: eventType,
      source: online ? "mobile" : "offline",
      client_event_id: clientEventId,
      occurred_at: new Date().toISOString(),
      notes: eventNotes,
      metadata: {
        captured_online: online,
        device: "mobile-web",
      },
    };
    if (eventType === "transfer" && transferLocationId) {
      payload.to_location = Number(transferLocationId);
    }
    if (!online) {
      await queueOrShow(
        "asset_event",
        payload,
        "掃碼事件已儲存，連線後自動同步",
        eventFile ?? undefined,
      );
      setScanValue("");
      setEventNotes("");
      setEventFile(null);
      setBusy(null);
      return;
    }
    const result = await apiMutation<AssetLogisticsEvent>(
      "/api/v1/logistics/events/",
      { body: payload, tenantSlug: tenant.slug },
    );
    const actionError = responseError(result);
    if (actionError) {
      if (actionError instanceof Error) {
        await queueOrShow(
          "asset_event",
          payload,
          "連線中斷，掃碼事件已加入同步佇列",
          eventFile ?? undefined,
        );
      } else {
        setError(apiErrorMessage(actionError, "掃碼事件未能記錄"));
      }
      setBusy(null);
      return;
    }
    if (eventFile && result.data) {
      const formData = new FormData();
      formData.append("job", String(selectedJob?.id ?? ""));
      formData.append("asset", String(result.data.asset));
      formData.append("event", String(result.data.id));
      formData.append("category", "photo");
      formData.append("file", eventFile);
      const upload = await apiUpload<LogisticsAttachment>(
        "/api/v1/logistics/attachments/",
        formData,
        tenant.slug,
      );
      if (responseError(upload)) {
        setError(apiErrorMessage(responseError(upload), "事件已記錄，但附件上傳失敗"));
      }
    }
    setScanValue("");
    setEventNotes("");
    setEventFile(null);
    setNotice("掃碼事件已記錄");
    await loadData();
    setBusy(null);
  }

  async function transitionJob(action: JobAction) {
    if (!selectedJob) return;
    setBusy(action);
    setError(null);
    setNotice(null);
    if (!online) {
      await queueOrShow(
        "job_action",
        { jobId: selectedJob.id, action, reason: "" },
        "任務狀態已排隊同步",
      );
      setBusy(null);
      return;
    }
    const result = await apiMutation<TransportJob>(
      `/api/v1/logistics/jobs/${selectedJob.id}/${action}/`,
      { body: { reason: "" }, tenantSlug: tenant?.slug },
    );
    const actionError = responseError(result);
    if (actionError) {
      setError(apiErrorMessage(actionError, "任務狀態更新失敗"));
    } else {
      setNotice("任務狀態已更新");
      await loadData();
    }
    setBusy(null);
  }

  async function uploadAttachment() {
    if (!selectedJob || !attachmentFile) {
      setError("請選擇任務及附件");
      return;
    }
    if (!online) {
      setError("附件需要連線後上傳");
      return;
    }
    setBusy("attachment");
    setError(null);
    const formData = new FormData();
    formData.append("job", String(selectedJob.id));
    formData.append("category", attachmentCategory);
    formData.append("file", attachmentFile);
    const result = await apiUpload<LogisticsAttachment>(
      "/api/v1/logistics/attachments/",
      formData,
      tenant?.slug,
    );
    const uploadError = responseError(result);
    if (uploadError) {
      setError(apiErrorMessage(uploadError, "附件上傳失敗"));
    } else {
      setAttachmentFile(null);
      setNotice(`附件 ${result.data?.original_filename ?? ""} 已上傳`);
    }
    setBusy(null);
  }

  async function submitReceipt() {
    if (!tenant || !selectedJob || !signerName.trim() || !signatureData) {
      setError("請選擇任務、填寫簽收人並完成簽名");
      return;
    }
    if (!accepted && !rejectionReason.trim()) {
      setError("拒絕接收需要填寫原因");
      return;
    }
    setBusy("receipt");
    setError(null);
    setNotice(null);
    const payload: Record<string, unknown> = {
      job: selectedJob.id,
      signer_name: signerName.trim(),
      signer_phone: signerPhone.trim(),
      accepted,
      rejection_reason: rejectionReason,
      signature_data: signatureData,
      signed_at: new Date().toISOString(),
      client_event_id: createClientEventId(),
      notes: receiptNotes,
    };
    if (!online) {
      await queueOrShow(
        "delivery_receipt",
        payload,
        "電子簽收已儲存，連線後自動同步",
      );
      setSignerName("");
      setSignerPhone("");
      setSignatureData("");
      setReceiptNotes("");
      setBusy(null);
      return;
    }
    const result = await apiMutation<DeliveryReceipt>(
      "/api/v1/logistics/delivery-receipts/",
      { body: payload, tenantSlug: tenant.slug },
    );
    const receiptError = responseError(result);
    if (receiptError) {
      if (receiptError instanceof Error) {
        await queueOrShow(
          "delivery_receipt",
          payload,
          "連線中斷，電子簽收已加入同步佇列",
        );
      } else {
        setError(apiErrorMessage(receiptError, "電子簽收未能儲存"));
      }
      setBusy(null);
      return;
    }
    setSignerName("");
    setSignerPhone("");
    setSignatureData("");
    setReceiptNotes("");
    setNotice("電子簽收已記錄");
    await loadData();
    setBusy(null);
  }

  async function startInventory() {
    if (!inventoryLocationId) {
      setError("請選擇盤點地點");
      return;
    }
    if (!online) {
      setError("開始盤點需要網絡連線");
      return;
    }
    setBusy("inventory-start");
    setError(null);
    const result = await apiMutation<InventoryCount>(
      "/api/v1/logistics/inventory-counts/",
      {
        body: {
          location: Number(inventoryLocationId),
          notes: "",
        },
        tenantSlug: tenant?.slug,
      },
    );
    const startError = responseError(result);
    if (startError) {
      setError(apiErrorMessage(startError, "盤點未能開始"));
    } else {
      setSelectedInventoryId(result.data?.id ?? null);
      setNotice("盤點已開始");
      await loadData();
    }
    setBusy(null);
  }

  async function scanInventory() {
    if (!activeInventory || !inventoryScanValue.trim()) {
      setError("請選擇進行中的盤點並掃描資產");
      return;
    }
    const clientEventId = createClientEventId();
    const payload = {
      countId: activeInventory.id,
      asset_identifier: inventoryScanValue.trim(),
      client_event_id: clientEventId,
      notes: "",
    };
    setBusy("inventory-scan");
    setError(null);
    if (!online) {
      await queueOrShow("inventory_scan", payload, "盤點掃碼已排隊同步");
      setInventoryScanValue("");
      setBusy(null);
      return;
    }
    const result = await apiMutation<InventoryCount>(
      `/api/v1/logistics/inventory-counts/${activeInventory.id}/scan/`,
      { body: payload, tenantSlug: tenant?.slug },
    );
    const scanError = responseError(result);
    if (scanError) {
      setError(apiErrorMessage(scanError, "盤點掃碼失敗"));
    } else {
      setInventoryScanValue("");
      setNotice("盤點掃碼已記錄");
      await loadData();
    }
    setBusy(null);
  }

  async function completeInventory() {
    if (!activeInventory) return;
    if (!online) {
      setError("完成盤點需要網絡連線");
      return;
    }
    setBusy("inventory-complete");
    setError(null);
    const result = await apiMutation<InventoryCount>(
      `/api/v1/logistics/inventory-counts/${activeInventory.id}/complete/`,
      { tenantSlug: tenant?.slug },
    );
    const completeError = responseError(result);
    if (completeError) {
      setError(apiErrorMessage(completeError, "盤點未能完成"));
    } else {
      setNotice("盤點已完成");
      setSelectedInventoryId(null);
      await loadData();
    }
    setBusy(null);
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("此裝置不支援鏡頭掃碼");
      return;
    }
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;
      setCameraActive(true);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      type DetectorResult = { rawValue: string };
      type Detector = { detect(source: HTMLVideoElement): Promise<DetectorResult[]> };
      type DetectorConstructor = new (options: {
        formats: string[];
      }) => Detector;
      const DetectorClass = (
        window as unknown as { BarcodeDetector?: DetectorConstructor }
      ).BarcodeDetector;
      if (!DetectorClass) {
        setNotice("鏡頭已開啟；此瀏覽器請使用掃碼槍或手動輸入");
        return;
      }
      const detector = new DetectorClass({
        formats: ["qr_code", "code_128", "ean_13"],
      });
      detectorTimerRef.current = setInterval(() => {
        if (!videoRef.current) return;
        void detector.detect(videoRef.current).then((results) => {
          if (results[0]?.rawValue) {
            setScanValue(results[0].rawValue);
            stopCamera();
          }
        });
      }, 500);
    } catch {
      setError("未能開啟鏡頭，請檢查瀏覽器權限");
      stopCamera();
    }
  }

  function stopCamera() {
    if (detectorTimerRef.current) {
      clearInterval(detectorTimerRef.current);
      detectorTimerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
  }

  const jobEvents = selectedEvents.slice(0, 12);
  const metrics = summary ?? {
    scheduled_jobs: jobs.filter((job) => job.status === "scheduled").length,
    active_jobs: jobs.filter((job) =>
      ["in_progress", "at_site"].includes(job.status),
    ).length,
    awaiting_receipt: jobs.filter(
      (job) => job.direction === "outbound" && job.status === "delivered",
    ).length,
    pending_collection: 0,
    recent_events: [],
  };

  return (
    <AppShell>
      <div className="page-stack field-console">
        <section className="page-intro field-intro">
          <div>
            <span className="eyebrow">Field operations</span>
            <h2>倉務與交收</h2>
            <p>掃碼、運輸任務、電子簽收及離線同步。</p>
          </div>
          <div className="field-sync-state">
            <span className={online ? "is-online" : "is-offline"}>
              {online ? <Wifi size={15} /> : <WifiOff size={15} />}
              {online ? "已連線" : "離線"}
            </span>
            <button
              className="field-sync-button"
              disabled={!online || syncing || outbox.length === 0}
              onClick={() => void syncOutbox()}
              type="button"
            >
              <CloudUpload size={15} />
              {syncing ? "同步中" : `待同步 ${outbox.length}`}
            </button>
          </div>
        </section>

        {error ? <ErrorBanner>{error}</ErrorBanner> : null}
        {notice ? (
          <div className="field-notice">
            <Check size={16} />
            {notice}
          </div>
        ) : null}

        <section className="field-metric-grid" aria-label="物流摘要">
          <div>
            <Truck size={17} />
            <span>待出車</span>
            <strong>{metrics.scheduled_jobs}</strong>
          </div>
          <div>
            <ScanLine size={17} />
            <span>運送中</span>
            <strong>{metrics.active_jobs}</strong>
          </div>
          <div>
            <Signature size={17} />
            <span>待簽收</span>
            <strong>{metrics.awaiting_receipt}</strong>
          </div>
          <div>
            <Warehouse size={17} />
            <span>待回倉</span>
            <strong>{metrics.pending_collection}</strong>
          </div>
        </section>

        <div className="field-tabs" role="tablist" aria-label="倉務工作區">
          {tabs.map((item) => (
            <button
              aria-selected={tab === item.value}
              data-active={tab === item.value}
              key={item.value}
              onClick={() => setTab(item.value)}
              role="tab"
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        {loading ? (
          <section className="panel">
            <LoadingBlock rows={5} />
          </section>
        ) : null}

        {!loading && tab === "jobs" ? (
          <div className="field-job-layout">
            <section className="panel field-job-list">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Assigned work</span>
                  <h3>今日任務</h3>
                </div>
                <span className="inline-note">{jobs.length} 宗</span>
              </header>
              {jobs.length ? (
                <div className="field-job-list__body">
                  {jobs.map((job) => (
                    <button
                      className={`field-job-row ${
                        selectedJob?.id === job.id ? "field-job-row--active" : ""
                      }`}
                      key={job.id}
                      onClick={() => setSelectedJobId(job.id)}
                      type="button"
                    >
                      <span className="field-job-row__icon">
                        {job.direction === "transfer" ? (
                          <Warehouse size={18} />
                        ) : (
                          <Truck size={18} />
                        )}
                      </span>
                      <span>
                        <strong>{job.number}</strong>
                        <small>
                          {job.customer_name ||
                            job.destination_site_name ||
                            job.destination_location_name ||
                            job.depot_name}
                        </small>
                      </span>
                      <span>
                        <StatusBadge status={job.status} />
                        <small>{formatDateTime(job.scheduled_start)}</small>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <EmptyState detail="目前沒有指派任務。" title="沒有待辦任務" />
              )}
            </section>

            <section className="panel field-job-detail">
              {selectedJob ? (
                <>
                  <header className="field-job-detail__header">
                    <div>
                      <span className="eyebrow">
                        {selectedJob.transport_reference || "Transport task"}
                      </span>
                      <h3>{selectedJob.number}</h3>
                      <p>
                        {selectedJob.customer_name ||
                          selectedJob.destination_site_name}
                      </p>
                    </div>
                    <StatusBadge status={selectedJob.status} />
                  </header>
                  <div className="field-route">
                    <div>
                      <MapPin size={15} />
                      <span>起點</span>
                      <strong>{selectedJob.depot_name}</strong>
                    </div>
                    <span className="field-route__line" />
                    <div>
                      <MapPin size={15} />
                      <span>目的地</span>
                      <strong>
                        {selectedJob.destination_site_name ||
                          selectedJob.destination_location_name}
                      </strong>
                      <small>
                        {selectedJob.destination_site_address ||
                          selectedJob.contact_name}
                      </small>
                    </div>
                  </div>
                  <div className="field-job-facts">
                    <div>
                      <span>車輛</span>
                      <strong>{selectedJob.vehicle || "未指派"}</strong>
                    </div>
                    <div>
                      <span>司機</span>
                      <strong>{selectedJob.driver_username || "未指派"}</strong>
                    </div>
                    <div>
                      <span>預定時段</span>
                      <strong>
                        {formatDateTime(selectedJob.scheduled_start)} 至{" "}
                        {formatDateTime(selectedJob.scheduled_end)}
                      </strong>
                    </div>
                    <div>
                      <span>聯絡</span>
                      <strong>
                        {selectedJob.contact_name ||
                          selectedJob.contact_phone ||
                          "—"}
                      </strong>
                    </div>
                  </div>
                  <div className="field-assets">
                    {selectedJob.items.map((item) => (
                      <div className="field-asset" key={item.id}>
                        <span>
                          <PackageCheck size={17} />
                        </span>
                        <div>
                          <strong>{item.asset_number}</strong>
                          <small>
                            {item.model_name} · {item.qr_code || "未設定 QR"}
                          </small>
                        </div>
                        <StatusBadge status={item.asset_status} />
                      </div>
                    ))}
                  </div>
                  <div className="field-job-actions">
                    {selectedJob.status === "scheduled" ? (
                      <Button
                        disabled={busy === "start"}
                        onClick={() => void transitionJob("start")}
                        variant="primary"
                      >
                        <Truck size={15} />
                        開始任務
                      </Button>
                    ) : null}
                    {selectedJob.status === "in_progress" ? (
                      <Button
                        disabled={busy === "arrive"}
                        onClick={() => void transitionJob("arrive")}
                        variant="primary"
                      >
                        <MapPin size={15} />
                        到達工地
                      </Button>
                    ) : null}
                    {selectedJob.status === "at_site" ? (
                      <Button
                        disabled={busy === "deliver"}
                        onClick={() => void transitionJob("deliver")}
                        variant="primary"
                      >
                        <PackageCheck size={15} />
                        完成交付
                      </Button>
                    ) : null}
                    {selectedJob.status === "delivered" ? (
                      <Button
                        disabled={busy === "complete"}
                        onClick={() => void transitionJob("complete")}
                        variant="primary"
                      >
                        <Check size={15} />
                        結案
                      </Button>
                    ) : null}
                    <Button onClick={() => setTab("scan")} variant="secondary">
                      <QrCode size={15} />
                      掃碼
                    </Button>
                    <Button onClick={() => setTab("receipt")} variant="secondary">
                      <Signature size={15} />
                      簽收
                    </Button>
                  </div>
                  <div className="field-attachment">
                    <Field label="現場附件">
                      <div className="field-inline-controls">
                        <Select
                          aria-label="附件類別"
                          onChange={(event) =>
                            setAttachmentCategory(
                              event.target
                                .value as Schemas["AttachmentCategoryEnum"],
                            )
                          }
                          value={attachmentCategory}
                        >
                          {attachmentCategories.map((item) => (
                            <option key={item.value} value={item.value}>
                              {item.label}
                            </option>
                          ))}
                        </Select>
                        <input
                          accept="image/jpeg,image/png,image/webp,image/heic,application/pdf"
                          className="field-file-input"
                          onChange={(event) =>
                            setAttachmentFile(event.target.files?.[0] ?? null)
                          }
                          type="file"
                        />
                        <Button
                          disabled={!attachmentFile || busy === "attachment"}
                          onClick={() => void uploadAttachment()}
                          variant="secondary"
                        >
                          <CloudUpload size={15} />
                          上傳
                        </Button>
                      </div>
                    </Field>
                    {attachmentFile ? (
                      <small>
                        {attachmentFile.name} · {fileSizeLabel(attachmentFile.size)}
                      </small>
                    ) : null}
                  </div>
                  <div className="field-event-chain">
                    <div className="field-section-heading">
                      <div>
                        <span className="eyebrow">Responsibility chain</span>
                        <h3>最近事件</h3>
                      </div>
                      <span className="inline-note">{jobEvents.length} 筆</span>
                    </div>
                    {jobEvents.length ? (
                      <div className="field-event-list">
                        {jobEvents.map((event) => (
                          <div className="field-event" key={event.id}>
                            <span className="field-event__dot" />
                            <div>
                              <strong>
                                {event.asset_number} ·{" "}
                                {eventTypes.find(
                                  (item) => item.value === event.event_type,
                                )?.label ?? event.event_type}
                              </strong>
                              <small>
                                {formatDateTime(event.occurred_at)} ·{" "}
                                {event.from_location_name ||
                                  event.site_name ||
                                  "流動位置"}
                                {event.to_location_name
                                  ? ` → ${event.to_location_name}`
                                  : ""}
                              </small>
                            </div>
                            <span>{event.actor_username || "system"}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        detail="尚無掃碼或交收事件。"
                        title="事件鏈尚未開始"
                      />
                    )}
                  </div>
                </>
              ) : (
                <EmptyState
                  detail="選取任務後可查看路線、資產及事件鏈。"
                  title="尚未選取任務"
                />
              )}
            </section>
          </div>
        ) : null}

        {!loading && tab === "scan" ? (
          <div className="field-workspace-grid">
            <section className="panel field-scan-panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Scan event</span>
                  <h3>資產掃碼</h3>
                </div>
                <StatusBadge status={online ? "active" : "offline"} />
              </header>
              <div className="field-form">
                <Field label="運輸任務">
                  <Select
                    onChange={(event) =>
                      setSelectedJobId(
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                    value={selectedJobId ?? ""}
                  >
                    <option value="">不指定任務</option>
                    {jobs.map((job) => (
                      <option key={job.id} value={job.id}>
                        {job.number} · {job.customer_name || job.direction}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="QR／條碼／資產編號">
                  <div className="field-scan-input">
                    <QrCode size={18} />
                    <Input
                      autoComplete="off"
                      onChange={(event) => setScanValue(event.target.value)}
                      placeholder="掃描或輸入編號"
                      value={scanValue}
                    />
                    <Button
                      aria-label={cameraActive ? "關閉鏡頭" : "開啟鏡頭"}
                      className="icon-button"
                      onClick={() =>
                        cameraActive ? stopCamera() : void startCamera()
                      }
                      type="button"
                      variant="ghost"
                    >
                      {cameraActive ? <CircleOff size={18} /> : <Camera size={18} />}
                    </Button>
                  </div>
                </Field>
                {cameraActive ? (
                  <div className="field-camera">
                    <video muted playsInline ref={videoRef} />
                    <span>將 QR／條碼置於畫面中央</span>
                  </div>
                ) : null}
                <Field label="事件">
                  <Select
                    onChange={(event) =>
                      setEventType(event.target.value as EventType)
                    }
                    value={eventType}
                  >
                    {eventTypes.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                {eventType === "transfer" ? (
                  <Field label="轉入地點">
                    <Select
                      onChange={(event) =>
                        setTransferLocationId(event.target.value)
                      }
                      value={transferLocationId}
                    >
                      <option value="">選擇地點</option>
                      {locations.map((location) => (
                        <option key={location.id} value={location.id}>
                          {location.code} · {location.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}
                <Field label="現場照片">
                  <input
                    accept="image/jpeg,image/png,image/webp,image/heic"
                    capture="environment"
                    className="field-file-input"
                    onChange={(event) =>
                      setEventFile(event.target.files?.[0] ?? null)
                    }
                    type="file"
                  />
                </Field>
                <Field label="備註">
                  <Textarea
                    onChange={(event) => setEventNotes(event.target.value)}
                    placeholder="延誤、損壞、位置或其他現場資料"
                    value={eventNotes}
                  />
                </Field>
                <Button
                  disabled={busy === "event"}
                  onClick={() => void recordEvent()}
                  variant="primary"
                >
                  <ScanLine size={16} />
                  {busy === "event" ? "記錄中" : "記錄掃碼事件"}
                </Button>
              </div>
            </section>

            <section className="panel field-queue-panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Local outbox</span>
                  <h3>離線佇列</h3>
                </div>
                <span className="inline-note">{outbox.length} 筆</span>
              </header>
              {outbox.length ? (
                <div className="field-queue-list">
                  {outbox.map((queued) => (
                    <div className="field-queue-item" key={queued.id}>
                      <CloudOff size={17} />
                      <div>
                        <strong>{queuedLabel(queued.kind)}</strong>
                        <small>
                          {String(
                            queued.payload.asset_identifier ??
                              queued.payload.signer_name ??
                              queued.payload.action ??
                              queued.payload.countId,
                          )}
                        </small>
                      </div>
                      <span>{formatDateTime(queued.createdAt)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  detail="所有現場記錄均已同步。"
                  title="佇列為空"
                  action={
                    <Button
                      onClick={() => void refreshOutbox()}
                      variant="secondary"
                    >
                      <RefreshCw size={15} />
                      重新整理
                    </Button>
                  }
                />
              )}
            </section>
          </div>
        ) : null}

        {!loading && tab === "receipt" ? (
          <div className="field-workspace-grid">
            <section className="panel field-receipt-panel">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Proof of delivery</span>
                  <h3>電子交收</h3>
                </div>
                {selectedJob ? <StatusBadge status={selectedJob.status} /> : null}
              </header>
              <div className="field-form">
                <Field label="運輸任務">
                  <Select
                    onChange={(event) =>
                      setSelectedJobId(Number(event.target.value))
                    }
                    value={selectedJobId ?? ""}
                  >
                    {jobs.map((job) => (
                      <option key={job.id} value={job.id}>
                        {job.number} · {job.customer_name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <div className="field-form-row">
                  <Field label="簽收人">
                    <Input
                      onChange={(event) => setSignerName(event.target.value)}
                      placeholder="姓名"
                      value={signerName}
                    />
                  </Field>
                  <Field label="聯絡電話">
                    <Input
                      inputMode="tel"
                      onChange={(event) => setSignerPhone(event.target.value)}
                      placeholder="可選"
                      value={signerPhone}
                    />
                  </Field>
                </div>
                <label className="field-check">
                  <input
                    checked={accepted}
                    onChange={(event) => setAccepted(event.target.checked)}
                    type="checkbox"
                  />
                  <span>設備及配件已完成點收</span>
                </label>
                {!accepted ? (
                  <Field label="拒絕接收原因">
                    <Textarea
                      onChange={(event) =>
                        setRejectionReason(event.target.value)
                      }
                      value={rejectionReason}
                    />
                  </Field>
                ) : null}
                <Field label="客戶簽名">
                  <SignaturePad
                    fallbackName={signerName}
                    onChange={setSignatureData}
                    value={signatureData}
                  />
                </Field>
                <Field label="交收備註">
                  <Textarea
                    onChange={(event) => setReceiptNotes(event.target.value)}
                    placeholder="損壞、短缺或現場安排"
                    value={receiptNotes}
                  />
                </Field>
                <Button
                  disabled={busy === "receipt"}
                  onClick={() => void submitReceipt()}
                  variant="primary"
                >
                  <Signature size={16} />
                  {busy === "receipt" ? "儲存中" : "完成電子簽收"}
                </Button>
              </div>
            </section>

            <section className="panel field-receipt-context">
              {selectedJob ? (
                <>
                  <header className="panel__header">
                    <div>
                      <span className="eyebrow">Site handover</span>
                      <h3>{selectedJob.destination_site_name}</h3>
                    </div>
                    <MapPin size={18} />
                  </header>
                  <div className="field-handover">
                    <div>
                      <span>聯絡人</span>
                      <strong>{selectedJob.contact_name || "—"}</strong>
                    </div>
                    <div>
                      <span>電話</span>
                      <strong>{selectedJob.contact_phone || "—"}</strong>
                    </div>
                    <div>
                      <span>地址</span>
                      <strong>{selectedJob.destination_site_address || "—"}</strong>
                    </div>
                  </div>
                  <div className="field-receipt-assets">
                    {selectedJob.items.map((item) => (
                      <div key={item.id}>
                        <Check size={15} />
                        <span>{item.asset_number}</span>
                        <small>{item.model_name}</small>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <EmptyState
                  detail="選取運輸任務後可準備交收。"
                  title="尚未選取任務"
                />
              )}
            </section>
          </div>
        ) : null}

        {!loading && tab === "inventory" ? (
          <div className="field-workspace-grid">
            <section className="panel field-inventory-start">
              <header className="panel__header">
                <div>
                  <span className="eyebrow">Warehouse count</span>
                  <h3>開始盤點</h3>
                </div>
                <Warehouse size={19} />
              </header>
              <div className="field-form">
                <Field label="盤點地點">
                  <Select
                    onChange={(event) =>
                      setInventoryLocationId(event.target.value)
                    }
                    value={inventoryLocationId}
                  >
                    {locations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.code} · {location.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Button
                  disabled={busy === "inventory-start"}
                  onClick={() => void startInventory()}
                  variant="primary"
                >
                  <Warehouse size={16} />
                  建立盤點批次
                </Button>
              </div>
              <div className="field-count-list">
                {counts.slice(0, 6).map((count) => (
                  <button
                    className={`field-count-row ${
                      activeInventory?.id === count.id
                        ? "field-count-row--active"
                        : ""
                    }`}
                    key={count.id}
                    onClick={() => setSelectedInventoryId(count.id)}
                    type="button"
                  >
                    <span>
                      <strong>{count.number}</strong>
                      <small>
                        {count.location_name} · {formatDateTime(count.started_at)}
                      </small>
                    </span>
                    <StatusBadge status={count.status} />
                    <small>
                      找到 {count.found_assets} · 缺少 {count.missing_assets}
                    </small>
                  </button>
                ))}
              </div>
            </section>

            <section className="panel field-inventory-active">
              {activeInventory ? (
                <>
                  <header className="panel__header">
                    <div>
                      <span className="eyebrow">{activeInventory.number}</span>
                      <h3>{activeInventory.location_name}</h3>
                    </div>
                    <StatusBadge status={activeInventory.status} />
                  </header>
                  <div className="field-count-summary">
                    <div>
                      <span>預期</span>
                      <strong>{activeInventory.expected_assets}</strong>
                    </div>
                    <div>
                      <span>找到</span>
                      <strong>{activeInventory.found_assets}</strong>
                    </div>
                    <div>
                      <span>缺失</span>
                      <strong>{activeInventory.missing_assets}</strong>
                    </div>
                    <div>
                      <span>非預期</span>
                      <strong>{activeInventory.unexpected_assets}</strong>
                    </div>
                  </div>
                  {activeInventory.status === "in_progress" ? (
                    <div className="field-inventory-scan">
                      <div className="field-scan-input">
                        <QrCode size={18} />
                        <Input
                          autoComplete="off"
                          onChange={(event) =>
                            setInventoryScanValue(event.target.value)
                          }
                          placeholder="掃描資產 QR／編號"
                          value={inventoryScanValue}
                        />
                      </div>
                      <Button
                        disabled={busy === "inventory-scan"}
                        onClick={() => void scanInventory()}
                        variant="primary"
                      >
                        <ScanLine size={16} />
                        記錄
                      </Button>
                      <Button
                        disabled={busy === "inventory-complete"}
                        onClick={() => void completeInventory()}
                        variant="secondary"
                      >
                        <PackageCheck size={16} />
                        完成盤點
                      </Button>
                    </div>
                  ) : null}
                  <div className="field-count-lines">
                    {activeInventory.lines.length ? (
                      activeInventory.lines.map((line) => (
                        <div className="field-count-line" key={line.id}>
                          <span
                            className={`field-count-line__mark field-count-line__mark--${line.result}`}
                          >
                            {line.result === "found" ? (
                              <Check size={14} />
                            ) : (
                              <AlertTriangle size={14} />
                            )}
                          </span>
                          <div>
                            <strong>{line.asset_number}</strong>
                            <small>{line.model_name}</small>
                          </div>
                          <StatusBadge status={line.result} />
                        </div>
                      ))
                    ) : (
                      <EmptyState
                        detail="掃描資產後會顯示差異。"
                        title="尚未掃碼"
                      />
                    )}
                  </div>
                </>
              ) : (
                <EmptyState
                  detail="建立批次後可離線掃碼並同步。"
                  title="尚無進行中的盤點"
                />
              )}
            </section>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
