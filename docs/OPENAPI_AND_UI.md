# OpenAPI 與營運介面

## OpenAPI

- 執行期 schema：`/api/schema/`
- Swagger UI：`/api/docs/`
- Repository contract：`docs/openapi.yaml`
- 產生 TypeScript 型別：`cd frontend && npm run openapi:types`

Schema 只公開 `/api/v1/`，舊 `/api/` 路徑仍保留給第一階段相容測試，但不會
進入公開 contract。Security schemes 同時描述：

- Django session cookie。
- DRF bearer token。
- 租戶 `X-Tenant` header。

修改 API 後應同時執行：

```sh
python manage.py spectacular --file docs/openapi.yaml --validate
cd frontend
npm run openapi:types
npm run typecheck
npm run build
```

## 身分驗證

Django admin 及既有 server-rendered 整合使用 session authentication。
Next.js 營運介面使用 `POST /api/v1/auth/login/` 取得 DRF token，並以
`Authorization: Token <key>` 呼叫 API。

- Login 必須通過 Origin 驗證。
- Logout 會撤銷目前 token。
- Token 只儲存在目前瀏覽器的 local storage，不由 URL 或 server component
  傳遞。
- Session-backed CSRF 仍套用於 session-authenticated 寫入。

## 營運介面

Next.js App Router 提供：

- `/`：營運總覽、待辦、車隊狀態及進行中租約。
- `/customers/`：客戶、聯絡人及工地摘要，可新增客戶。
- `/fleet/`：逐台資產、型號、工時／里數及狀態轉換。
- `/quotes/`：報價搜尋、篩選及建立。
- `/quotes/[id]/`：明細、計價、提交、審批及轉租約。
- `/orders/`：租約列表。
- `/orders/[id]/`：出倉、回倉、續租、合約及資產分配。
- `/billing/`：發票、付款、按金及財務摘要。

介面經 runtime Route Handler `/api/[...path]` 反向代理至 Django。容器內
使用 `DJANGO_API_URL=http://web:8000`，不會把 dev URL 烘進 production
image。

## 本機展示

```sh
python manage.py seed_demo
docker compose up --build
```

- UI：`http://localhost:3000/`
- API：`http://localhost:8001/`
- 示範帳戶：`ops.admin`
- 示範密碼：`RentalDemo2026!`

示範資料只供本機驗證，不應部署至 production。
