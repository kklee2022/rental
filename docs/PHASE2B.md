# 階段 2B：資產匯入

## 支援範圍

- 地點：倉庫、車場、工地及維修地點。
- 設備型號：必須引用已存在的設備類別。
- 逐台資產：型號、地點、序號、牌照、QR、期初工時及里數。
- 配件：配件代碼、狀態、地點及相容設備型號。
- 期初讀數：工時、里數、讀數時間及來源。

CSV 及 XLSX 使用相同的 canonical 欄位。若舊系統欄名不同，可提交
`column_mapping`，格式為 `canonical_field -> uploaded_header`，並可儲存為
租戶層欄位映射範本。

## 檔案限制

- 僅接受 `.csv` 及 `.xlsx`。
- 單檔上限 10 MB。
- 最多 5,000 個資料列。
- CSV 必須為 UTF-8；XLSX 會檢查壓縮後與解壓後的合理大小。
- 檔案存放在 tenant-prefixed private storage，預設 30 日後可由清理工作
  移除檔案內容；批次、列及審計 metadata 會保留。

## 批次生命週期

1. `uploaded`
2. `validating`
3. `preview_ready`
4. `committing`
5. `completed`

錯誤分支為 `failed`，使用者亦可取消未提交批次。只有
`preview_ready`、`error_rows == 0` 且有資料列的批次可提交。

提交在單一 transaction 中完成，任何一列失敗即整批回滾。批次完成後不可
再次提交。

## 驗證與重複處理

- 必填欄位、型別、日期、JSON、列舉值及關聯存在性。
- 檔內重複 key。
- 租戶內既有資料重複。
- 型號與資產的序號／QR 唯一性。
- 期初讀數不得低於資產現值或檔內前一行。
- `max_assets` 方案額度。
- 資產匯入只建立可用資產；既有資產的狀態與目前讀數不經資產匯入改寫。
- 重複策略可選 `error`、`update` 或 `skip`。

## 預覽與錯誤報告

`import_row` 保留原始列、正規化資料、action、錯誤及 warning。錯誤報告為
UTF-8 BOM CSV，包含原始上傳欄位，並對 formula-like cell 加防護前綴。

## 撤銷

- 只允許 create-only 且類型為地點、型號、資產或配件的批次。
- 地點、型號及配件在未被引用時可刪除。
- 已匯入但未使用的資產會經狀態機轉為 `retired`，保留狀態事件及審計鏈。
- 工時／里數讀數為 append-only，因此期間讀數批次不提供撤銷。
- 曾經 update 既有資料的批次不提供自動撤銷。

## API

- `GET /api/v1/import-templates/<type>/?file_format=xlsx`
- `GET|POST /api/v1/imports/`
- `GET /api/v1/imports/<id>/`
- `POST /api/v1/imports/<id>/commit/`
- `POST /api/v1/imports/<id>/cancel/`
- `POST /api/v1/imports/<id>/undo/`
- `GET /api/v1/imports/<id>/error-report/`
- `GET /api/v1/import-rows/?batch=<id>`
- `GET|POST /api/v1/import-mappings/`

所有端點要求租戶 `asset_import` feature。讀取需要租戶 membership，寫入
需要 owner/admin/warehouse 角色。

## 前端

`/imports/` 提供：

- 五種資料類型及 XLSX／CSV 範本下載。
- 拖拉式檔案選擇、重複策略、欄位映射及映射名稱。
- 非同步驗證狀態輪詢。
- 批次摘要、逐列 action／錯誤／warning 預覽。
- 提交、取消、撤銷及錯誤報告下載。
