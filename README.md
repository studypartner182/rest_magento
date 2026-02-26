# Mock Magento REST API (ADF Ingestion Practice)

Realistic Magento-style admin REST API simulation for Azure Data Factory ingestion flows.

## Features

- Magento-like admin token endpoints:
  - `POST /rest/V1/integration/admin/token`
  - `POST /rest/V1/integration/admin/refresh`
- JWT auth with access + refresh tokens
  - Access token expiry: 2 minutes
  - Refresh token expiry: 10 minutes
- Protected Magento-style resources:
  - `GET /rest/V1/orders`
  - `GET /rest/V1/products`
  - `GET /rest/V1/customers`
- ADF-friendly pagination (`pageSize`, `currentPage`)
- Incremental loading (`updated_after`)
- In-memory rate limiting (20 req/min/IP) with `Retry-After`
- Error simulation controls (`fail`, `delay`, `random_error`)
- Request/auth/rate-limit/token-expiry logging

## Project Structure

```text
mock_magento/
  main.py
  auth.py
  config.py
  data/
    orders.json
    products.json
    customers.json
requirements.txt
README.md
```

## Local Setup

### 1) Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run API

```bash
uvicorn mock_magento.main:app --host 0.0.0.0 --port 8000 --reload
```

## Default Admin Credentials

- Username: `admin`
- Password: `Admin@123`

## cURL Examples

### Get access + refresh token

```bash
curl -s -X POST 'http://localhost:8000/rest/V1/integration/admin/token' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin@123"}'
```

### Access orders endpoint (authorized)

```bash
ACCESS_TOKEN="<paste_access_token>"
curl -s 'http://localhost:8000/rest/V1/orders?pageSize=5&currentPage=1' \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

### Trigger 401 (invalid credentials)

```bash
curl -i -X POST 'http://localhost:8000/rest/V1/integration/admin/token' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"wrong-password"}'
```

### Trigger 429 (rate limiting)

```bash
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    'http://localhost:8000/rest/V1/orders' \
    -H "Authorization: Bearer ${ACCESS_TOKEN}"
done
```

### Trigger 500 (forced failure)

```bash
curl -i 'http://localhost:8000/rest/V1/orders?fail=true' \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

### Test incremental load

```bash
curl -s 'http://localhost:8000/rest/V1/orders?updated_after=2025-01-10T00:00:00Z&pageSize=50&currentPage=1' \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

## ADF Mapping Guidance

This API is designed to mirror common ADF ingestion patterns:

- **Web activity**: Call `/integration/admin/token` to fetch JWT.
- **REST linked service**: Use `Authorization: Bearer <access_token>`.
- **Pagination loop**: Iterate with `pageSize` and `currentPage`.
- **Until activity**: Stop when `items` is empty.
- **Retry policy**: Handle `429` and `500` with backoff.
- **Token refresh path**: On `401`, call `/integration/admin/refresh` or get new token.
- **Incremental ingestion**: Filter with `updated_after` watermark.
