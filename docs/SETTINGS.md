# 公司設定與用戶管理

`/settings/` 只供租戶 owner 及 administrator 使用。

## 公司設定

可設定：

- 本公司名稱，會同步更新 tenant 顯示名稱。
- 客戶編號 prefix。
- 報價 prefix。
- 租約 prefix。
- 發票 prefix。

Prefix 會正規化為大寫，長度最多 12 位，只接受英文字母、數字及連字號。
文件編號格式為：

```text
<PREFIX>-<YEAR>-<6-DIGIT SEQUENCE>
```

客戶、資產、報價、租約及發票建立時，若未提供自訂編號，會使用對應
prefix 自動產生。手動輸入編號仍然支援。

## 資產類別

每個租戶可管理自己的設備類別，包括代碼、名稱、描述及資產 prefix。
同一租戶內的 prefix 必須唯一。建立資產但未輸入資產編號時，系統會使用
設備型號所屬類別的 prefix 自動編號。

已被設備型號引用的類別不可刪除。

## 用戶管理

用戶可在本公司內建立、編輯、停用、重設密碼及移除。移除用戶只會刪除該
租戶的 membership，不會刪除其平台帳戶。

可用角色：

- Owner
- Administrator
- Sales / rental
- Warehouse / fleet
- Driver
- Technician
- Finance
- Read-only

Owner 及 administrator 可管理公司設定及用戶。最後一名 active owner 不可
被降級或移除；方案 `max_users` 額度仍會強制執行。
Administrator 不可建立、提升、修改或移除 Owner membership；Owner 管理只
能由另一位 Owner 執行。

## API

- `GET|PATCH /api/v1/settings/`
- `GET|POST /api/v1/users/`
- `GET|PATCH|DELETE /api/v1/users/<membership-id>/`
- `GET|POST /api/v1/equipment-categories/`
- `PATCH|DELETE /api/v1/equipment-categories/<id>/`

所有端點要求有效的 `X-Tenant` header 及租戶 membership。
