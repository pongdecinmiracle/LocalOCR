# LocalOCR — System Design & Initial Deployment Report

> 🇹🇭 ภาษาไทย: ดู [รายงานภาษาไทย](#localocr--รายงานการออกแบบระบบและขั้นตอนการติดตั้งเริ่มต้น-ภาษาไทย) ด้านล่าง
>
> Related documents: [README.md](README.md) (features & user guide) ·
> [RUNNING.md](RUNNING.md) (day-to-day operation manual)

---

## Part 1 — System Design

### 1.1 What the system does

LocalOCR is a self-hosted document data-extraction system. Users upload PDFs
or scanned images, draw boxes over the fields they want (invoice number,
date, totals, line-item tables), save that layout as a reusable **template**,
then batch-extract those fields from any number of documents using a **local
vision language model** — and export the results to Excel. No document or
piece of data ever leaves the machine it runs on.

### 1.2 Architecture

The system is composed of four containerized services orchestrated by Docker
Compose:

```
                ┌────────────┐   /api/*   ┌───────────┐        ┌────────────┐
  browser  ───► │  frontend  │ ─────────► │  backend  │ ─────► │     db     │
                │  (nginx)   │            │ (FastAPI) │        │ PostgreSQL │
                └────────────┘            └─────┬─────┘        └────────────┘
                                                │  ┌──────────┐  ┌──────────┐
                                                ├─►│  ollama  │  │  volume  │
                                                │  │ (vision) │  │  /data   │
                                                   └──────────┘  └──────────┘
```

| Service | Technology | Responsibility |
|---------|-----------|----------------|
| **frontend** | nginx 1.27 | Serves the single-page UI; reverse-proxies `/api` to the backend; enforces rate limits and security headers; the **only** published port |
| **backend** | Python 3.12 · FastAPI · uvicorn (4 workers) | Authentication, template/document management, page rendering, the extraction job queue, Excel export |
| **db** | PostgreSQL 16 | Accounts, templates, upload metadata, extraction jobs |
| **ollama** | Ollama (pinned image) + `qwen2.5vl:7b` | Runs the local vision model that reads the documents |

**Design rationale:** each service can be scaled, restarted, upgraded, and
health-checked independently; the database and the model runtime are standard
off-the-shelf images; only nginx is exposed to the network, so the backend,
database, and model are unreachable from outside the Docker network.

### 1.3 Data design

Structured data lives in PostgreSQL; bulk files live on a Docker named volume.

**Database tables**

| Table | Contents |
|-------|----------|
| `users` | Account, PBKDF2 password hash + per-user salt, admin flag, `token_version` (see 1.5) |
| `templates` | Field layout as a JSON document (boxes, types, table columns), owned per user |
| `uploads` | Upload metadata + per-page dimensions (JSON), owned per user |
| `extraction_jobs` | Job queue: status, progress, results (see 1.4) |

**File volume layout** (`file_data` volume, mounted at `/data`)

```
/data/users/<user_id>/
    uploads/<upload_id>/<original file>     the uploaded document
    pages/<upload_id>/page_<i>.png          pages rendered at LOCALOCR_DPI
    exports/<name>.xlsx                     generated Excel files (newest 20 kept)
/data/secret.key                            fallback cookie-signing key
```

Every file path is namespaced by `user_id` and every API route checks
ownership, so users cannot see each other's documents, templates, or results.

Three named volumes survive container rebuilds: `db_data` (database),
`file_data` (user files), `ollama_data` (the ~6 GB model).

### 1.4 Extraction pipeline (background job design)

Extraction is **asynchronous** by design — a large batch must never block the
web tier or hit an HTTP timeout:

1. `POST /api/extract` validates the template, model readiness, and document
   ownership, then inserts a row into `extraction_jobs` (status `queued`) and
   returns a `job_id` immediately.
2. Each backend worker process runs one background worker thread. Workers
   claim queued jobs with `SELECT … FOR UPDATE SKIP LOCKED` — a safe,
   DB-native queue that needs no extra infrastructure (no Redis/broker).
3. The claimed job is processed document by document; progress (`done`,
   `current_file`, partial `results`) is committed to the DB after each one.
4. The browser polls `GET /api/extract/jobs/{id}` (~1.2 s interval) to drive
   the progress bar, and renders results when the status becomes `done`.
5. Jobs interrupted by a server restart are marked failed at boot, so clients
   never wait on a job that no worker will finish.

Because all job state lives in PostgreSQL, any worker process can serve the
polling endpoint, several jobs run concurrently across processes, and jobs
from different users are processed fairly in queue order. This is what allows
**10+ concurrent users**: the four HTTP workers stay free for interactive
requests while the model grinds through queued documents.

For each page, the **entire page image** is sent to the vision model once,
with a prompt listing every field on that page. The drawn boxes are not
crops — they define which fields exist, their types, and a coarse location
hint ("top-right"). Full-page context is significantly more accurate than
tight per-field crops, which starve the model of visual tokens.

### 1.5 Security design

| Layer | Mechanism |
|-------|-----------|
| Passwords | PBKDF2-HMAC-SHA256, 200k iterations, per-user random salt |
| Sessions | HMAC-signed httpOnly cookie (30 days, `SameSite=Lax`); tokens embed a per-user `token_version` — any password change bumps it and instantly invalidates all existing sessions |
| Brute force | nginx rate-limits `/api/login` and `/api/register` per IP (10 req/min); the backend additionally locks an IP+account pair for 5 minutes after 5 failed attempts |
| Registration | `LOCALOCR_ALLOW_REGISTRATION=false` makes the instance invite-only; the first-ever account is always allowed (admin bootstrap) |
| Uploads | Filenames sanitized (path-traversal safe), extension allowlist, per-file size cap, per-user storage quota, page-count cap |
| Containers | Backend drops to an unprivileged user; pinned image versions; rotated logs; nginx sends CSP / nosniff / frame-deny headers |
| Transport | HTTP within the trusted LAN; for anything beyond, a TLS reverse proxy + `LOCALOCR_COOKIE_SECURE=true` is required |

### 1.6 Configuration & schema management

All configuration is environment-driven via a single `.env` file (see the
table in [README.md](README.md#configuration)) — the same images run in dev
and production. The database schema is managed by **Alembic migrations** that
run automatically at container start; databases created by older versions are
detected and adopted in place, so upgrades are always `git pull` +
`docker compose up -d --build` with no manual steps.

A pytest suite (auth, lockout, session revocation, upload sanitization,
quotas, job queue) and a GitHub Actions pipeline (tests + image builds) guard
regressions.

---

## Part 2 — Initial Deployment on a New PC (pull → run)

### 2.1 Prerequisites

- **Docker Desktop** (Windows/macOS, WSL2 backend on Windows) or Docker
  Engine + Compose v2 (Linux)
- **~12 GB free disk** (6 GB model + working data)
- **Internet for the first run only** (base images + model)
- *(Optional)* NVIDIA GPU ≥ 6 GB VRAM — much faster extraction

Python, Node.js, and a local Ollama install are **not** required.

### 2.2 Step-by-step initialization

```bash
# 1. Get the code
git clone <repository-url>
cd LocalOCR

# 2. Create the configuration file
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
```

**3. Edit `.env`** — two values are mandatory:

| Variable | Value |
|----------|-------|
| `POSTGRES_PASSWORD` | A long random password. The stack refuses to start without it. |
| `LOCALOCR_SECRET_KEY` | A long random value, e.g. from `python -c "import secrets; print(secrets.token_hex(32))"` |

Also decide now: `LOCALOCR_ALLOW_REGISTRATION` (set `false` for invite-only)
and `LOCALOCR_PORT` (default `8080`).

**4. CPU-only host?** The compose file ships with NVIDIA GPU passthrough
**enabled** for the `ollama` service. If this PC has no NVIDIA GPU, comment
out the `deploy:` block under `ollama` in `docker-compose.yml` first.

```bash
# 5. Build and start all four services
docker compose up -d --build

# 6. Download the vision model into the ollama container (one time, ~6 GB)
docker compose exec ollama ollama pull qwen2.5vl:7b
```

**7. Create the administrator.** Open `http://localhost:8080`, click
**Create an account**, and sign up — **the first account automatically
becomes the admin**. The engine status (top right) must read
**"✓ qwen2.5vl:7b ready"**.

### 2.3 What happens automatically on first start

Understanding this explains why no manual initialization is needed:

1. **Volumes are created** (`db_data`, `file_data`, `ollama_data`) and
   PostgreSQL initializes itself with the credentials from `.env`.
2. The backend entrypoint **fixes data-volume ownership** and drops to an
   unprivileged user.
3. **Alembic migrations run** (`python -m app.migrate`): on a fresh database
   they create the full schema; on a database from an older version they
   stamp and upgrade it in place. Jobs orphaned by a previous shutdown are
   marked failed.
4. If `LOCALOCR_SECRET_KEY` is empty, a random signing key is generated and
   persisted to the data volume.
5. Four uvicorn workers start, each launching one extraction worker thread.
6. The **first registered account is promoted to admin** (and a safety check
   re-promotes the oldest account if a database ever ends up with no admin).

### 2.4 Verification checklist

| Check | Expected |
|-------|----------|
| `docker compose ps` | 4 services up; `backend` and `db` show **healthy** |
| `http://localhost:8080` | Login screen loads |
| Engine status after login | **✓ qwen2.5vl:7b ready** |
| Upload `samples/sample_invoice.png` | Thumbnail appears with page count |
| `docker compose logs backend --tail 20` | `backend ready (model=qwen2.5vl:7b)`, no errors |

### 2.5 Optional: LAN access for other machines

The app listens on `http://<host-ip>:<LOCALOCR_PORT>` already. On Windows
hosts, allow it through the firewall (elevated PowerShell):

```powershell
New-NetFirewallRule -DisplayName "LocalOCR" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private
```

and make sure the Wi-Fi/Ethernet network is categorized **Private**. Details,
HTTPS guidance, and troubleshooting: [RUNNING.md](RUNNING.md) sections 4–5.

---
---

# LocalOCR — รายงานการออกแบบระบบและขั้นตอนการติดตั้งเริ่มต้น (ภาษาไทย)

> 🇬🇧 English: see the [English report](#localocr--system-design--initial-deployment-report) above.
>
> เอกสารที่เกี่ยวข้อง: [README.md](README.md) (คุณสมบัติและวิธีใช้งาน) ·
> [RUNNING.md](RUNNING.md) (คู่มือการใช้งานประจำวัน)

---

## ส่วนที่ 1 — การออกแบบระบบ

### 1.1 ระบบนี้ทำอะไร

LocalOCR คือระบบดึงข้อมูลจากเอกสารแบบติดตั้งใช้งานเองในเครื่อง (self-hosted)
ผู้ใช้อัปโหลดไฟล์ PDF หรือภาพสแกน วาดกรอบครอบช่องข้อมูลที่ต้องการ (เลขที่ใบแจ้งหนี้
วันที่ ยอดรวม ตารางรายการสินค้า) บันทึกเลย์เอาต์นั้นเป็น **เทมเพลต** ที่ใช้ซ้ำได้
แล้วสั่งดึงข้อมูลจากเอกสารจำนวนมากพร้อมกันด้วย **โมเดล vision ที่รันในเครื่อง**
และส่งออกผลลัพธ์เป็น Excel — เอกสารและข้อมูลทุกชิ้นไม่ออกไปนอกเครื่องที่รันระบบเลย

### 1.2 สถาปัตยกรรม

ระบบประกอบด้วยเซอร์วิส 4 ตัวที่รันในคอนเทนเนอร์ ควบคุมด้วย Docker Compose:

```
                ┌────────────┐   /api/*   ┌───────────┐        ┌────────────┐
  เบราว์เซอร์ ──► │  frontend  │ ─────────► │  backend  │ ─────► │     db     │
                │  (nginx)   │            │ (FastAPI) │        │ PostgreSQL │
                └────────────┘            └─────┬─────┘        └────────────┘
                                                │  ┌──────────┐  ┌──────────┐
                                                ├─►│  ollama  │  │  volume  │
                                                │  │ (vision) │  │  /data   │
                                                   └──────────┘  └──────────┘
```

| เซอร์วิส | เทคโนโลยี | หน้าที่ |
|---------|-----------|--------|
| **frontend** | nginx 1.27 | เสิร์ฟหน้าเว็บ (SPA); reverse-proxy `/api` ไปยัง backend; ทำ rate limit และ security headers; เป็นพอร์ต**เดียว**ที่เปิดสู่ภายนอก |
| **backend** | Python 3.12 · FastAPI · uvicorn (4 workers) | ยืนยันตัวตน จัดการเทมเพลต/เอกสาร เรนเดอร์หน้าเอกสาร คิวงานดึงข้อมูล ส่งออก Excel |
| **db** | PostgreSQL 16 | บัญชีผู้ใช้ เทมเพลต ข้อมูลไฟล์ และงานในคิว |
| **ollama** | Ollama (ตรึงเวอร์ชัน image) + `qwen2.5vl:7b` | รันโมเดล vision ที่อ่านเอกสาร |

**เหตุผลการออกแบบ:** แต่ละเซอร์วิสสามารถขยาย รีสตาร์ต อัปเกรด และตรวจสุขภาพ
แยกจากกันได้ ฐานข้อมูลและตัวรันโมเดลใช้ image มาตรฐาน และมีเพียง nginx
เท่านั้นที่เข้าถึงได้จากเครือข่าย — backend, ฐานข้อมูล และโมเดล
เข้าถึงจากภายนอก Docker network ไม่ได้

### 1.3 การออกแบบข้อมูล

ข้อมูลเชิงโครงสร้างเก็บใน PostgreSQL ส่วนไฟล์ขนาดใหญ่เก็บบน Docker named volume

**ตารางในฐานข้อมูล**

| ตาราง | เก็บอะไร |
|-------|---------|
| `users` | บัญชี, รหัสผ่านแฮชแบบ PBKDF2 + salt รายผู้ใช้, สถานะแอดมิน, `token_version` (ดู 1.5) |
| `templates` | เลย์เอาต์ช่องข้อมูลเป็นเอกสาร JSON (กรอบ ชนิด คอลัมน์ตาราง) แยกตามเจ้าของ |
| `uploads` | ข้อมูลไฟล์ที่อัปโหลด + ขนาดของแต่ละหน้า (JSON) แยกตามเจ้าของ |
| `extraction_jobs` | คิวงาน: สถานะ ความคืบหน้า ผลลัพธ์ (ดู 1.4) |

**โครงสร้างไฟล์บน volume** (`file_data` ติดตั้งที่ `/data`)

```
/data/users/<user_id>/
    uploads/<upload_id>/<ไฟล์ต้นฉบับ>        เอกสารที่อัปโหลด
    pages/<upload_id>/page_<i>.png           หน้าที่เรนเดอร์ตาม LOCALOCR_DPI
    exports/<ชื่อ>.xlsx                      ไฟล์ Excel (เก็บ 20 ไฟล์ล่าสุด)
/data/secret.key                             กุญแจเซ็นคุกกี้ (กรณีไม่ตั้งใน .env)
```

ทุกเส้นทางไฟล์แยกตาม `user_id` และทุก API ตรวจสอบความเป็นเจ้าของ
ผู้ใช้จึงมองไม่เห็นเอกสาร เทมเพลต หรือผลลัพธ์ของกันและกัน

Named volume สามตัวคงอยู่แม้ build คอนเทนเนอร์ใหม่: `db_data` (ฐานข้อมูล),
`file_data` (ไฟล์ผู้ใช้), `ollama_data` (โมเดล ~6 GB)

### 1.4 ขั้นตอนการดึงข้อมูล (การออกแบบงานเบื้องหลัง)

การดึงข้อมูลถูกออกแบบให้เป็นแบบ **asynchronous** — งานชุดใหญ่ต้องไม่บล็อก
เว็บเซิร์ฟเวอร์หรือชน HTTP timeout:

1. `POST /api/extract` ตรวจสอบเทมเพลต ความพร้อมของโมเดล และความเป็นเจ้าของเอกสาร
   แล้วเพิ่มแถวลงตาราง `extraction_jobs` (สถานะ `queued`) และคืน `job_id` ทันที
2. โปรเซส backend แต่ละตัวรัน worker thread เบื้องหลังหนึ่งเส้น ซึ่งจองงานจากคิวด้วย
   `SELECT … FOR UPDATE SKIP LOCKED` — คิวที่ปลอดภัยในตัวฐานข้อมูลเอง
   ไม่ต้องมีโครงสร้างพื้นฐานเพิ่ม (ไม่ต้องใช้ Redis/broker)
3. งานที่จองแล้วถูกประมวลผลทีละเอกสาร และบันทึกความคืบหน้า (`done`,
   `current_file`, ผลลัพธ์บางส่วน) ลงฐานข้อมูลหลังจบแต่ละเอกสาร
4. เบราว์เซอร์ poll `GET /api/extract/jobs/{id}` (ทุก ~1.2 วินาที)
   เพื่ออัปเดตแถบความคืบหน้า และแสดงผลเมื่อสถานะเป็น `done`
5. งานที่ค้างจากการรีสตาร์ตเซิร์ฟเวอร์จะถูกทำเครื่องหมายว่าล้มเหลวตอนบูต
   ผู้ใช้จึงไม่ต้องรองานที่ไม่มีใครทำต่อ

เนื่องจากสถานะงานทั้งหมดอยู่ใน PostgreSQL โปรเซสใดก็ตอบ endpoint สำหรับ poll ได้
งานหลายงานรันพร้อมกันข้ามโปรเซสได้ และงานของผู้ใช้แต่ละคนถูกประมวลผล
อย่างยุติธรรมตามลำดับคิว — นี่คือสิ่งที่ทำให้รองรับ **ผู้ใช้พร้อมกัน 10+ คน**:
HTTP workers ทั้งสี่ยังว่างรับคำขอปกติ ขณะที่โมเดลทยอยประมวลผลเอกสารในคิว

ในแต่ละหน้า ระบบส่ง **ภาพทั้งหน้า** ให้โมเดล vision ครั้งเดียว พร้อม prompt
ที่ระบุทุกช่องข้อมูลบนหน้านั้น กรอบที่วาดไม่ใช่การครอปภาพ — แต่เป็นตัวกำหนดว่า
มีช่องอะไรบ้าง ชนิดอะไร และคำใบ้ตำแหน่งคร่าว ๆ ("มุมขวาบน") เพราะบริบทเต็มหน้า
แม่นยำกว่าการครอปแคบ ๆ ทีละช่องอย่างมีนัยสำคัญ

### 1.5 การออกแบบด้านความปลอดภัย

| ชั้น | กลไก |
|-----|------|
| รหัสผ่าน | PBKDF2-HMAC-SHA256 จำนวน 200,000 รอบ พร้อม salt สุ่มรายผู้ใช้ |
| เซสชัน | คุกกี้ httpOnly เซ็นด้วย HMAC (30 วัน, `SameSite=Lax`); โทเคนฝัง `token_version` ของผู้ใช้ — เปลี่ยนรหัสผ่านเมื่อใด เซสชันเดิมทั้งหมดใช้ไม่ได้ทันที |
| ป้องกันเดารหัสผ่าน | nginx จำกัด `/api/login` และ `/api/register` ต่อ IP (10 ครั้ง/นาที); backend ล็อกคู่ IP+บัญชี 5 นาทีหลังพลาด 5 ครั้ง |
| การสมัครสมาชิก | `LOCALOCR_ALLOW_REGISTRATION=false` ทำให้เป็นระบบเชิญเท่านั้น; บัญชีแรกสุดสร้างได้เสมอ (bootstrap แอดมิน) |
| การอัปโหลด | ชื่อไฟล์ถูก sanitize (กัน path traversal), allowlist นามสกุลไฟล์, จำกัดขนาดต่อไฟล์, โควตาต่อผู้ใช้, จำกัดจำนวนหน้า |
| คอนเทนเนอร์ | backend รันด้วยผู้ใช้ไร้สิทธิพิเศษ; ตรึงเวอร์ชัน image; log หมุนเวียนอัตโนมัติ; nginx ส่ง CSP / nosniff / frame-deny headers |
| การรับส่งข้อมูล | HTTP ภายใน LAN ที่เชื่อถือได้; ถ้าเกินกว่านั้นต้องมี TLS reverse proxy + `LOCALOCR_COOKIE_SECURE=true` |

### 1.6 การจัดการค่าตั้งค่าและ schema

ค่าตั้งค่าทั้งหมดขับเคลื่อนด้วย environment variables ผ่านไฟล์ `.env` ไฟล์เดียว
(ดูตารางใน [README.md](README.md#configuration)) — image ชุดเดียวกันใช้ได้ทั้ง
dev และ production ส่วน schema ของฐานข้อมูลจัดการด้วย **Alembic migrations**
ที่รันอัตโนมัติตอนคอนเทนเนอร์เริ่มทำงาน ฐานข้อมูลจากเวอร์ชันเก่าจะถูกตรวจจับ
และอัปเกรดให้เอง การอัปเดตระบบจึงเหลือแค่ `git pull` +
`docker compose up -d --build` โดยไม่มีขั้นตอน manual

มีชุดทดสอบ pytest (ยืนยันตัวตน การล็อกเอาต์ การเพิกถอนเซสชัน การ sanitize
ไฟล์อัปโหลด โควตา คิวงาน) และ GitHub Actions (รันเทสต์ + build image)
คอยป้องกัน regression

---

## ส่วนที่ 2 — การติดตั้งเริ่มต้นบนเครื่องใหม่ (pull → run)

### 2.1 สิ่งที่ต้องมีก่อน

- **Docker Desktop** (Windows/macOS ใช้ WSL2 backend บน Windows) หรือ
  Docker Engine + Compose v2 (Linux)
- **พื้นที่ดิสก์ว่าง ~12 GB** (โมเดล 6 GB + ข้อมูลใช้งาน)
- **อินเทอร์เน็ตเฉพาะครั้งแรก** (ดาวน์โหลด image และโมเดล)
- *(ไม่บังคับ)* การ์ดจอ NVIDIA VRAM ≥ 6 GB — ดึงข้อมูลเร็วขึ้นมาก

**ไม่ต้อง**ติดตั้ง Python, Node.js หรือ Ollama บนเครื่อง

### 2.2 ขั้นตอนการติดตั้งทีละขั้น

```bash
# 1. ดึงโค้ด
git clone <repository-url>
cd LocalOCR

# 2. สร้างไฟล์ค่าตั้งค่า
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
```

**3. แก้ไข `.env`** — สองค่านี้บังคับต้องตั้ง:

| ตัวแปร | ค่า |
|--------|-----|
| `POSTGRES_PASSWORD` | รหัสผ่านสุ่มที่ยาว — ระบบไม่ยอมเริ่มทำงานถ้าไม่ตั้ง |
| `LOCALOCR_SECRET_KEY` | ค่าสุ่มที่ยาว เช่นจาก `python -c "import secrets; print(secrets.token_hex(32))"` |

ควรตัดสินใจตอนนี้ด้วย: `LOCALOCR_ALLOW_REGISTRATION` (ตั้ง `false`
ถ้าต้องการระบบเชิญเท่านั้น) และ `LOCALOCR_PORT` (ค่าเริ่มต้น `8080`)

**4. เครื่องไม่มีการ์ดจอ NVIDIA?** ไฟล์ compose เปิดใช้ GPU passthrough
สำหรับเซอร์วิส `ollama` ไว้แล้ว ถ้าเครื่องนี้ไม่มีการ์ดจอ NVIDIA
ให้คอมเมนต์บล็อก `deploy:` ใต้ `ollama` ใน `docker-compose.yml` ออกก่อน

```bash
# 5. Build และเริ่มเซอร์วิสทั้งสี่
docker compose up -d --build

# 6. ดาวน์โหลดโมเดลเข้าคอนเทนเนอร์ ollama (ครั้งเดียว ~6 GB)
docker compose exec ollama ollama pull qwen2.5vl:7b
```

**7. สร้างบัญชีผู้ดูแลระบบ** — เปิด `http://localhost:8080` คลิก
**Create an account** แล้วสมัคร — **บัญชีแรกจะเป็นแอดมินโดยอัตโนมัติ**
สถานะเครื่องมือ (มุมขวาบน) ต้องขึ้นว่า **"✓ qwen2.5vl:7b ready"**

### 2.3 สิ่งที่เกิดขึ้นอัตโนมัติตอนเริ่มครั้งแรก

เข้าใจส่วนนี้แล้วจะเห็นว่าทำไมจึงไม่ต้องมีขั้นตอน initialize ด้วยมือ:

1. **Volume ถูกสร้าง** (`db_data`, `file_data`, `ollama_data`) และ PostgreSQL
   ตั้งค่าตัวเองด้วยข้อมูลจาก `.env`
2. Entrypoint ของ backend **แก้สิทธิ์ความเป็นเจ้าของ data volume**
   แล้วสลับไปรันด้วยผู้ใช้ไร้สิทธิพิเศษ
3. **Alembic migrations รัน** (`python -m app.migrate`): ฐานข้อมูลใหม่จะถูกสร้าง
   schema ครบชุด ส่วนฐานข้อมูลจากเวอร์ชันเก่าจะถูก stamp และอัปเกรดให้ในที่
   งานที่ค้างจากการปิดเครื่องครั้งก่อนถูกทำเครื่องหมายว่าล้มเหลว
4. ถ้า `LOCALOCR_SECRET_KEY` ว่าง ระบบจะสุ่มกุญแจเซ็นคุกกี้และบันทึกลง volume
5. uvicorn workers สี่ตัวเริ่มทำงาน แต่ละตัวมี worker thread สำหรับงานดึงข้อมูล
6. **บัญชีแรกที่สมัครถูกยกเป็นแอดมิน** (และมีกลไกสำรอง: ถ้าฐานข้อมูลไม่มีแอดมินเลย
   บัญชีที่เก่าที่สุดจะถูกยกเป็นแอดมินให้)

### 2.4 รายการตรวจสอบหลังติดตั้ง

| ตรวจ | ผลที่ควรได้ |
|------|------------|
| `docker compose ps` | เซอร์วิสทั้ง 4 ตัวรันอยู่; `backend` และ `db` ขึ้น **healthy** |
| `http://localhost:8080` | หน้าจอล็อกอินแสดงขึ้น |
| สถานะเครื่องมือหลังล็อกอิน | **✓ qwen2.5vl:7b ready** |
| อัปโหลด `samples/sample_invoice.png` | รูปย่อปรากฏพร้อมจำนวนหน้า |
| `docker compose logs backend --tail 20` | มี `backend ready (model=qwen2.5vl:7b)` และไม่มี error |

### 2.5 เพิ่มเติม: เปิดให้เครื่องอื่นใน LAN เข้าถึง

แอปเปิดรับที่ `http://<ip-เครื่องโฮสต์>:<LOCALOCR_PORT>` อยู่แล้ว บนเครื่อง Windows
ต้องอนุญาตพอร์ตผ่านไฟร์วอลล์ (PowerShell แบบ Run as administrator):

```powershell
New-NetFirewallRule -DisplayName "LocalOCR" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private
```

และตรวจว่าเครือข่าย Wi-Fi/Ethernet ถูกจัดเป็นประเภท **Private**
รายละเอียด คำแนะนำ HTTPS และการแก้ปัญหา: [RUNNING.md](RUNNING.md) หัวข้อ 4–5
