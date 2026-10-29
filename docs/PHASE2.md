# 階段 2 實作狀態

階段 2 的租賃核心與營運帳務後端已完成，全部 API 位於 `/api/v1/`，並沿用
`X-Tenant` 租戶 header、tenant-scoped ORM 及 append-only 審計。

## 業務模組

### 客戶

- 客戶、聯絡人及工地。
- 客戶狀態、信用額度、主要聯絡人唯一性及租戶內客戶編號唯一性。

### 車隊

- 設備類別、型號、倉庫／地點及逐台資產。
- 受控資產狀態機及不可修改的狀態事件。
- 工時／里數讀數不得倒退，讀數會更新資產目前讀數。
- 方案 `max_assets` 額度於建立資產時強制執行。

### 定價

- 價單、基本價格、最低消費、稅率、按金比例及有效期。
- 固定、按量及百分比收費元件，可套用至指定設備型號。
- 報價及租約行保留可重現的計算 snapshot。

### 租賃

- 報價建立、計價、提交、owner／admin 審批、拒絕及轉租約。
- 租約確認、具體資產分配、出倉、退租及取消。
- 續租會新增租約行及連續分配，不覆寫原租約行。
- 可用性 API 按具體型號及時間區間回傳可租資產。
- 合約發出及簽署會產生不可修改的版本與 SHA-256 hash。

### 帳務

- 訂單轉臨時／最終發票、發票明細及價格 snapshot。
- 付款、部分付款、退款、貸項通知及按金收取／抵扣／退款。
- 發票狀態及未結餘額由 completed payments、refunds 與 issued credits
  自動重算。
- 會計發票 CSV 匯出及 billing 報表。

## 併發與防撞

- 分配建立前會鎖定資產並在交易內檢查時間重疊。
- PostgreSQL 使用 `btree_gist` 及 `tstzrange(..., '[)')` exclusion
  constraint，資料庫層阻止同一資產的有效分配重疊。
- SQLite 測試環境以 insert／update trigger 驗證相同規則。
- 相鄰時段 `end_at == next_start_at` 被允許。
- 過期 held 分配可經 tenant-scoped Celery task 釋放。

## API 入口

- `/api/v1/customers/`
- `/api/v1/equipment-models/`
- `/api/v1/assets/`
- `/api/v1/rate-plans/`
- `/api/v1/quotes/`
- `/api/v1/rental-orders/`
- `/api/v1/contracts/`
- `/api/v1/invoices/`
- `/api/v1/payments/`
- `/api/v1/deposits/`
- `/api/v1/reports/fleet/`
- `/api/v1/reports/rentals/`
- `/api/v1/reports/billing/`
- `/api/v1/exports/accounting.csv`

## 角色邊界

- owner／admin：全部租戶功能，包括報價審批。
- rental：客戶、價單、報價及租約。
- warehouse：設備、資產狀態及讀數。
- finance：發票、付款、退款、貸項、按金及會計匯出。
- viewer：唯讀。

## 本階段未包含

- 資產 XLSX／CSV 匯入屬階段 2B。
- 手機掃碼、離線同步及物流責任鏈屬階段 3。
- 客戶前台、電子簽署供應商、支付網關及會計系統 API 整合屬後續階段。
- Django admin 僅供 platform superuser 檢視／修正現有 tenant-owned 資料；
  tenant-owned 新資料應經 API 建立。
