# 第一階段實作狀態

依據 `machinery-rental-erp-implementation-plan.md` 的階段 1 驗收條件，
目前原始碼已完成以下基礎：

## 已完成

- Django／DRF、PostgreSQL／Redis／S3 相容儲存的環境接口。
- 租戶、方案、會員、角色及功能額度模型。
- `X-Tenant` API 租戶選擇、會員驗證及停用租戶攔截。
- ORM 預設租戶過濾、bulk create／update 防護及 fail-closed context。
- 租戶前綴快取、私有檔案命名空間、CSV 匯出過濾。
- Celery tenant task base 及同步背景工作執行邊界。
- owner／admin 會員管理 API、人數額度及最後一位 owner 保護。
- ORM 與 PostgreSQL／SQLite trigger 層的不可變審計。
- 租戶建立、方案建立及啟停管理命令與 Django admin。
- JSON logs、request ID、liveness／readiness 及可選 Sentry。
- PostgreSQL／Redis 容器、Gunicorn image、GitHub Actions CI。
- PostgreSQL custom-format 備份及受確認保護的還原腳本。

## 外部上線工作

以下項目需要實際環境而非只靠 repository 完成：

- 建立 production PostgreSQL、Redis、S3 bucket 及最小權限帳戶。
- 設定 DNS、TLS、secret manager、Sentry DSN 及部署平台。
- 開啟並監控每日備份、S3 lifecycle、還原演練及保留政策。
- 在 production 規格執行跨租戶測試、負載測試及故障復原演練。
