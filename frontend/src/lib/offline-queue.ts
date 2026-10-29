export type QueuedRequestKind =
  | "asset_event"
  | "delivery_receipt"
  | "inventory_scan"
  | "job_action";

export type QueuedFile = {
  name: string;
  type: string;
  blob: Blob;
};

export type QueuedRequest = {
  id: string;
  tenantSlug: string;
  kind: QueuedRequestKind;
  payload: Record<string, unknown>;
  createdAt: string;
  file?: QueuedFile;
};

const DATABASE_NAME = "machinery-rental-offline";
const STORE_NAME = "requests";
const DATABASE_VERSION = 1;

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("tenantSlug", "tenantSlug", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function createClientEventId() {
  return crypto.randomUUID();
}

export async function listQueuedRequests(
  tenantSlug: string,
): Promise<QueuedRequest[]> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const index = transaction.objectStore(STORE_NAME).index("tenantSlug");
    const requests = await requestResult(index.getAll(tenantSlug));
    return requests.sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt),
    );
  } finally {
    database.close();
  }
}

export async function enqueueRequest(
  input: Omit<QueuedRequest, "id" | "createdAt">,
): Promise<QueuedRequest> {
  const queued: QueuedRequest = {
    ...input,
    id: createClientEventId(),
    createdAt: new Date().toISOString(),
  };
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    await requestResult(transaction.objectStore(STORE_NAME).put(queued));
    return queued;
  } finally {
    database.close();
  }
}

export async function removeQueuedRequest(id: string): Promise<void> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    await requestResult(transaction.objectStore(STORE_NAME).delete(id));
  } finally {
    database.close();
  }
}
