# 機械租賃 ERP

Django + Django REST Framework 的模組化單體，第一階段提供多租戶 SaaS
平台、租戶隔離、角色、方案額度及不可變審計基礎。

## 本機啟動

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

本地未設定 PostgreSQL 時會使用 SQLite。營運介面需要另開一個終端：

```sh
cd frontend
npm install
DJANGO_API_URL=http://127.0.0.1:8000 npm run dev
```

完整容器環境會同時啟動 Django API 與 Next.js 營運介面：

```sh
docker compose up --build
```

服務啟動後：

- 健康檢查：`http://localhost:8000/health/live/`
- 就緒檢查：`http://localhost:8000/health/ready/`
- 營運介面：`http://localhost:3000/`
- OpenAPI schema：`http://localhost:8000/api/schema/`
- Swagger UI：`http://localhost:8000/api/docs/`
- 管理後台：`http://localhost:8000/admin/`

若預設 port 已被佔用，可設定 `WEB_PORT=8001 docker compose up --build`。
Django admin 僅供 platform superuser 使用；租戶 owner/admin 透過 API 管理。

## 租戶開通

```sh
.venv/bin/python manage.py create_plan standard --name Standard \
  --max-assets 100 --max-users 10 --feature asset_import
.venv/bin/python manage.py create_tenant acme --name "ACME Rental" \
  --plan standard --owner owner-username
```

API 支援 session 及 DRF token authentication。除 `/api/v1/me/` 外，
租戶 API 必須提供 `X-Tenant: <slug>`。主要端點：

- `GET /api/v1/me/`
- `GET /api/v1/tenant/`
- `GET|POST /api/v1/memberships/`
- `PATCH|DELETE /api/v1/memberships/<id>/`
- `GET /api/v1/audit-events/`

階段 2 租賃核心另提供：

- `/api/v1/customers/`、`/api/v1/sites/`
- `/api/v1/equipment-models/`、`/api/v1/assets/`
- `/api/v1/rate-plans/`、`/api/v1/quotes/`
- `/api/v1/rental-orders/`、`/api/v1/contracts/`
- `/api/v1/invoices/`、`/api/v1/payments/`、`/api/v1/deposits/`
- `/api/v1/reports/fleet/`、`/api/v1/reports/rentals/`、
  `/api/v1/reports/billing/`
- `/api/v1/exports/accounting.csv`
- `/api/v1/imports/`、`/api/v1/import-rows/`
- `/api/v1/import-templates/<type>/`

完整業務流程、防撞規則及角色邊界見
[`docs/PHASE2.md`](docs/PHASE2.md)。

OpenAPI、token authentication、營運介面功能及 runtime proxy 設計見
[`docs/OPENAPI_AND_UI.md`](docs/OPENAPI_AND_UI.md)。

階段 2B 匯入格式、限制、撤銷規則及安全邊界見
[`docs/PHASE2B.md`](docs/PHASE2B.md)。

OpenAPI contract 保存在 `docs/openapi.yaml`。更新 API 後執行：

```sh
python manage.py spectacular --file docs/openapi.yaml --validate
cd frontend && npm run openapi:types
```

營運介面使用 DRF token authentication；Django admin 及既有整合可繼續使用
session authentication。可建立示範環境：

```sh
.venv/bin/python manage.py seed_demo
```

示範登入為 `ops.admin` / `RentalDemo2026!`。只供本機展示，不應使用於
production。

## 隔離規則

- 業務模型必須繼承 `core.models.TenantScopedModel`。
- 日常查詢只用 `objects`；`all_tenants` 僅限平台層程式碼。
- 快取使用 `core.cache.tenant_cache`，檔案使用預設
  `TenantFileSystemStorage`。
- 背景工作使用 `core.jobs.run_tenant_job`，Celery task 使用
  `core.tasks.TenantTask` 並傳入 `tenant_id`。
- CSV 匯出使用 `core.exports.tenant_csv_response`。
- 審計事件由 ORM 及資料庫 trigger 雙重保護，不可更新或刪除。

設定 `AWS_STORAGE_BUCKET_NAME` 後，預設檔案儲存會切換到 private
S3-compatible storage，所有 object key 自動加 `tenants/<tenant-id>/` 前綴。

## 驗證

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test --settings=config.settings_test
```

GitHub Actions 會使用 PostgreSQL 及 Redis 跑同一套測試，並建立 production
image。備份與還原腳本位於 `scripts/`；實際排程、S3 bucket、Sentry 專案及
部署環境屬外部營運配置。

```sh
POSTGRES_DB=rental POSTGRES_USER=rental POSTGRES_PASSWORD=secret \
  sh scripts/backup_postgres.sh

CONFIRM_RESTORE=rental POSTGRES_DB=rental POSTGRES_USER=rental \
  POSTGRES_PASSWORD=secret sh scripts/restore_postgres.sh ./backups/rental-....dump
```
# rental
