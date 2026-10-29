# 階段 3：手機及倉務物流

## 交付形式

階段 3 以可安裝的 mobile-first PWA 交付，同一套 Next.js 介面可在 iOS、
Android、平板及桌面瀏覽器使用。PWA 提供 standalone 啟動、app icon 及
service worker app-shell cache；需要 App Store／Play Store 原生殼時，可在
不改動 API 的前提下以 Capacitor 或同類容器包裝。

## 倉務工作台

`/logistics/` 提供四個現場工作區：

- 任務：查看司機任務、路線、車輛、聯絡人、資產及責任鏈。
- 掃碼：使用鏡頭、掃碼槍或手動輸入 QR／條碼／資產編號。
- 交收：客戶電子簽名、接受／拒絕原因及交收附件。
- 盤點：建立地點盤點批次、逐台掃碼、完成差異計算。

只有具備 `mobile_logistics` feature 的租戶可使用物流 API。自訂權限：

- owner／admin／warehouse 可管理全部任務及盤點。
- driver 只可讀取及操作指派給自己的運輸任務。
- technician 可記錄資產事件。

## 責任鏈

每宗物流事件保存：

- 資產、運輸任務、事件類型及來源。
- 起點、目的地、工地、GPS 座標及發生時間。
- 操作人、離線同步時間、備註及 metadata。

事件為 append-only。資產狀態依既有狀態機更新；轉倉事件只更新可信最後
位置，不會繞過保養、安全封鎖或租約狀態規則。

電子簽收支援觸控／滑鼠簽名，以及以簽收人姓名代替手寫簽名的無障礙方式。

## 離線同步

現場記錄先寫入裝置的 IndexedDB outbox：

- 掃碼／工時／里數／異常事件。
- 任務狀態操作。
- 盤點掃碼。
- 電子簽收。
- 掃碼事件附帶的現場照片。

恢復連線後依建立時間同步。每筆記錄使用 client-generated UUID；API 以
`tenant + client_event_id` 唯一約束提供 idempotency，因此重試不會產生
重複事件、盤點列或簽收。

Service worker 只快取介面、manifest 及靜態資源，不快取 `/api/` 的租戶
資料。照片上傳限制為 10 MB，支援 JPEG、PNG、WebP、HEIC 及 PDF。

## API

- `GET /api/v1/logistics/summary/`
- `GET|POST /api/v1/logistics/jobs/`
- `POST /api/v1/logistics/jobs/<id>/start/`
- `POST /api/v1/logistics/jobs/<id>/arrive/`
- `POST /api/v1/logistics/jobs/<id>/deliver/`
- `POST /api/v1/logistics/jobs/<id>/complete/`
- `GET|POST /api/v1/logistics/events/`
- `GET|POST /api/v1/logistics/delivery-receipts/`
- `GET|POST /api/v1/logistics/attachments/`
- `GET /api/v1/logistics/attachments/<id>/download/`
- `GET|POST /api/v1/logistics/inventory-counts/`
- `POST /api/v1/logistics/inventory-counts/<id>/scan/`
- `POST /api/v1/logistics/inventory-counts/<id>/complete/`

## 驗收範圍

- 離線掃碼後恢復連線不會產生重複事件。
- 司機不能讀取或修改未指派任務。
- 電子簽收可接受或拒絕，拒絕時必須提供原因。
- 出倉任務必須有已接受的簽收才可結案。
- 盤點會標示找到、缺少及非預期資產。
- 附件、事件、盤點及任務均受 tenant 隔離。
