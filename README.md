# LocalOCR

A fully local document data-extraction tool. Upload PDFs/images, **draw boxes**
over the fields you care about, save that layout as a reusable **template**, then
batch-extract those fields from any number of documents and **export to Excel** —
all running on your own machine via a local vision LLM.

LocalOCR runs as a set of **separate, containerized services** orchestrated with
Docker Compose:

| Service | Tech | Role |
|---------|------|------|
| **frontend** | nginx | Serves the single-page UI and reverse-proxies `/api` to the backend |
| **backend** | Python · FastAPI · uvicorn | Renders pages, calls the model, runs extraction, writes xlsx |
| **db** | PostgreSQL | Stores accounts, templates, and upload metadata |
| **ollama** | [Ollama](https://ollama.com) + `qwen2.5vl:7b` | The local vision LLM that does the reading |

Files (uploaded originals, rendered page images, Excel exports) live on a shared
Docker volume; structured data lives in PostgreSQL. **Nothing leaves your computer.**

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

## User accounts

LocalOCR has a built-in login system. On first visit you **create an account**
(username + password), then sign in. Everything you upload and every template you
build is **private to your account** — other users can't see your documents or
templates.

- Passwords are hashed (PBKDF2-HMAC-SHA256, per-user salt) — never stored in
  plain text.
- Sign-in uses a secure httpOnly session cookie that lasts 30 days, signed with
  `LOCALOCR_SECRET_KEY`.
- Accounts and templates are stored in PostgreSQL; per-user files live on the
  backend's data volume (see [Layout](#layout)). Both stay on your machine.

### Admin page

The **first account you create becomes the administrator**. Admins see an extra
**⚙ Admin** tab for managing users:

- View all users with their role and document/template counts
- **Add** new accounts (optionally as admins)
- **Reset** any user's password
- **Grant or revoke** admin rights
- **Delete** a user — this also removes all of that user's documents and templates

Safeguards prevent removing the last remaining admin or deleting your own account
from the panel.

> **Note on exposure:** the login protects access, but on a plain-HTTP server
> passwords travel unencrypted. If you expose LocalOCR beyond localhost, put it
> behind an **HTTPS reverse proxy**. See [Run · Security](#reaching-it-from-another-machine).

## How it works

For each page, LocalOCR sends the **whole page** to the vision model and asks for
all the template's fields at once as structured JSON. The boxes you draw define
*which* fields exist, their type (text / number / date / **table**), table
columns, and a location hint that tells the model where to look. Full-page
context is far more accurate than tiny per-field crops.

## Prerequisites

Install these **before** running setup:

| Requirement | Notes |
|-------------|-------|
| **[Docker](https://www.docker.com/products/docker-desktop/) + Compose v2** | The only hard requirement. Docker Desktop (Windows/macOS) or Docker Engine + `docker compose` (Linux). |
| **Vision model** `qwen2.5vl:7b` | ~6 GB, pulled once into the `ollama` container (see Setup). Does the actual reading. |
| **NVIDIA GPU (optional)** | ≥6 GB VRAM for smooth performance. CPU-only works but is much slower. See [GPU](#gpu-acceleration). |
| **Disk space** | ~6 GB for the model + a few GB for images and rendered pages. |
| **Internet** | One-time only — to pull the base images and the model. Everything runs offline afterwards. |

**Not required:** Python, Node.js, or a local Ollama install — everything runs
inside containers.

## Setup (one time)

```bash
# 1. Configure (sets DB password, session secret, port, etc.)
cp .env.example .env
#    then edit .env — at minimum set a strong POSTGRES_PASSWORD and LOCALOCR_SECRET_KEY
#    generate a secret:  python -c "import secrets; print(secrets.token_hex(32))"

# 2. Build and start all four services
docker compose up -d --build

# 3. Pull the vision model into the ollama container (~6 GB, one time)
docker compose exec ollama ollama pull qwen2.5vl:7b
```

Then open **<http://localhost:8080>** (or whatever `LOCALOCR_PORT` you set) and
create your first account — it becomes the admin.

> The `run.ps1` / `run.bat` / `run.sh` launchers wrap these steps (they create
> `.env`, build, start, and open the browser). `stop.ps1` / `stop.bat` /
> `stop.sh` run `docker compose down`.

## Run

```bash
docker compose up -d        # start (detached)
docker compose logs -f      # follow logs
docker compose down         # stop (data preserved in named volumes)
docker compose down -v      # stop AND wipe all data (DB + files + model)
```

On Windows you can instead run `.\run.ps1` (or double-click `run.bat`) to start
and `.\stop.ps1` (or `stop.bat`) to stop.

### Reaching it from another machine

The frontend publishes `LOCALOCR_PORT` (default `8080`) on the host, so it's
already reachable at `http://<host-ip>:8080`. To change the published port, set
`LOCALOCR_PORT` in `.env`.

> ⚠️ **Security:** the app has username/password login, but on plain HTTP those
> credentials travel unencrypted. For anything beyond localhost, terminate
> **HTTPS** in front of the `frontend` service (e.g. a reverse proxy such as
> Caddy/Traefik/nginx, or a cloud load balancer) and set
> `LOCALOCR_COOKIE_SECURE=true` in `.env` so the session cookie is marked Secure.

### GPU acceleration

By default the `ollama` service runs on CPU. For NVIDIA GPUs, install the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
and uncomment the `deploy:` GPU block under the `ollama` service in
`docker-compose.yml`, then `docker compose up -d`.

## How to use the application

> 🇹🇭 ภาษาไทย: ดู [วิธีใช้งานแอปพลิเคชัน (ภาษาไทย)](#วิธีใช้งานแอปพลิเคชัน-ภาษาไทย) ด้านล่าง

### Step 0 · Sign in

The first time you open the app you'll see a sign-in screen. Click **Create an
account**, choose a username and password, and submit — you're taken straight
into the app. Next time, just **Sign in**. Your name appears top-right with a
**Logout** button. Everything you do is saved to your account.

The app then has three tabs across the top — work through them left to right.

### Step 1 · Documents — upload your files

- Open the **1 · Documents** tab.
- **Drag and drop** your files onto the drop zone, or click **browse** to pick
  them. You can add many at once.
- Supported formats: **PDF, PNG, JPG/JPEG, TIFF, BMP, WEBP**. Multi-page PDFs are
  fully supported — every page is rendered.
- Each uploaded file appears as a thumbnail tile showing its page count. Click
  **remove** on a tile to drop it.

> Tip: upload one representative document first to build the template, then come
> back and add the rest of the batch before extracting.

### Step 2 · Template Editor — mark the fields you want

A *template* is a saved layout that tells the app which fields to pull out. You
only build it once per document type, then reuse it forever.

1. Open the **2 · Template Editor** tab.
2. In the **Document** dropdown, pick the file you want to lay out. Use the
   **‹ ›** arrows to move between pages.
3. **Drag a box** over a field on the page (e.g. around the invoice number). When
   you release the mouse, a dialog opens:
   - **Field name** — becomes the column header in Excel (e.g. `invoice_number`).
   - **Type** — choose **Text**, **Number**, **Date**, or **Table**.
   - For a **Table** field, add a row of **columns** (name + type) for each column
     in the table — e.g. `description (text)`, `qty (number)`, `unit_price
     (number)`, `amount (number)`.
   - Click **Save field**.
4. Repeat for every field you want. Each box is colour-coded (blue = simple
   field, purple = table) and labelled on the page.
5. Manage fields in the right-hand **Fields** list:
   - Click a field's **name** to highlight its box (and jump to its page).
   - Click **✎** to edit its name/type/columns.
   - Click **✕** to delete it.
   - To move or resize a box, delete it and redraw.
6. Type a **Template name** at the top right (e.g. "ACME Invoice") and click
   **💾 Save template**.

To edit an existing template later: choose it in the dropdown, click **Load**,
make changes, and **Save** again. **New** starts a blank template; **Delete**
removes the selected one.

> The boxes don't have to be pixel-perfect — they act as *location hints*. The
> model reads the whole page for context, so a roughly-placed box around the
> right area works well. Just make sure each box is over the correct field.

### Step 3 · Extract & Export — run it and get Excel

1. Open the **3 · Extract & Export** tab.
2. Pick your **Template** from the dropdown.
3. Tick the **documents to process** (all are checked by default; use **select
   all** to toggle).
4. Click **▶ Run extraction**. A processing animation shows progress as each
   document is read by the local model. (Large/multi-page files take longer.)
5. Review the **Results** — a summary table of the simple fields, plus a table
   per document for any table fields.
6. Click **⬇ Export to Excel**, then the **Download** link that appears.

### The Excel file

- A **`Data`** sheet: one row per document, one column per simple field, with a
  `_file` column naming the source document.
- One **extra sheet per table field** (named after the field): one row per table
  row, with a `_file` column linking each row back to its document.

### Tips & troubleshooting

- **Engine status** is shown top-right. It must read **"✓ qwen2.5vl:7b ready"**.
  If it says *Ollama not running*, check `docker compose ps` (the `ollama`
  container should be up); if it says the model isn't ready, run
  `docker compose exec ollama ollama pull qwen2.5vl:7b`.
- **A value came out wrong?** Make sure the box is over the intended field, and
  that the field **Type** matches (use Number for amounts, Date for dates).
  Higher-resolution scans extract better — see `LOCALOCR_DPI` below.
- **Re-running** is cheap: tweak the template and extract again.
- Everything runs locally — your documents never leave your machine.

## วิธีใช้งานแอปพลิเคชัน (ภาษาไทย)

> 🇬🇧 English: see [How to use the application](#how-to-use-the-application) above.

### ขั้นที่ 0 · เข้าสู่ระบบ (Sign in)

เมื่อเปิดแอปครั้งแรกจะพบหน้าจอเข้าสู่ระบบ คลิก **Create an account** เพื่อสร้างบัญชี
ตั้งชื่อผู้ใช้และรหัสผ่าน แล้วกดยืนยัน ระบบจะพาเข้าสู่แอปทันที ครั้งต่อไปเพียง **Sign in**
ชื่อของคุณจะแสดงที่มุมขวาบนพร้อมปุ่ม **Logout** — ข้อมูลทุกอย่างจะถูกบันทึกไว้กับบัญชีของคุณ
และเป็นส่วนตัวเฉพาะคุณเท่านั้น

จากนั้นแอปจะมี 3 แท็บอยู่ด้านบน ให้ทำงานไล่จากซ้ายไปขวา

### ขั้นที่ 1 · Documents — อัปโหลดไฟล์ของคุณ

- เปิดแท็บ **1 · Documents**
- **ลากแล้ววาง** ไฟล์ลงในกรอบ หรือคลิก **browse** เพื่อเลือกไฟล์ เลือกได้หลายไฟล์พร้อมกัน
- รองรับไฟล์: **PDF, PNG, JPG/JPEG, TIFF, BMP, WEBP** รองรับ PDF หลายหน้า โดยจะเรนเดอร์ทุกหน้า
- ไฟล์ที่อัปโหลดจะแสดงเป็นรูปย่อพร้อมจำนวนหน้า คลิก **remove** บนไฟล์เพื่อลบออก

> เคล็ดลับ: อัปโหลดเอกสารตัวอย่าง 1 ไฟล์ก่อนเพื่อสร้างเทมเพลต แล้วค่อยกลับมาเพิ่มไฟล์ที่เหลือก่อนเริ่มดึงข้อมูล

### ขั้นที่ 2 · Template Editor — กำหนดช่องข้อมูลที่ต้องการ

*เทมเพลต (template)* คือเลย์เอาต์ที่บันทึกไว้ ซึ่งบอกแอปว่าจะดึงข้อมูลช่องใดบ้าง สร้างเพียงครั้งเดียวต่อรูปแบบเอกสารหนึ่งชนิด แล้วนำกลับมาใช้ซ้ำได้ตลอด

1. เปิดแท็บ **2 · Template Editor**
2. ในเมนู **Document** เลือกไฟล์ที่ต้องการกำหนดเลย์เอาต์ ใช้ปุ่มลูกศร **‹ ›** เพื่อเปลี่ยนหน้า
3. **ลากกรอบ** ครอบช่องข้อมูลบนหน้าเอกสาร (เช่น ครอบเลขที่ใบแจ้งหนี้) เมื่อปล่อยเมาส์จะมีหน้าต่างขึ้นมา:
   - **Field name** — ชื่อช่อง จะกลายเป็นหัวคอลัมน์ใน Excel (เช่น `invoice_number`)
   - **Type** — เลือก **Text** (ข้อความ), **Number** (ตัวเลข), **Date** (วันที่), หรือ **Table** (ตาราง)
   - สำหรับช่องแบบ **Table** ให้เพิ่ม **คอลัมน์ (columns)** (ชื่อ + ชนิด) สำหรับแต่ละคอลัมน์ในตาราง เช่น `description (text)`, `qty (number)`, `unit_price (number)`, `amount (number)`
   - คลิก **Save field**
4. ทำซ้ำกับทุกช่องที่ต้องการ แต่ละกรอบจะมีสี (ฟ้า = ช่องทั่วไป, ม่วง = ตาราง) และมีป้ายชื่อกำกับบนหน้า
5. จัดการช่องต่าง ๆ ได้ในรายการ **Fields** ทางด้านขวา:
   - คลิก **ชื่อ** ของช่องเพื่อไฮไลต์กรอบ (และข้ามไปยังหน้าที่กรอบนั้นอยู่)
   - คลิก **✎** เพื่อแก้ไขชื่อ / ชนิด / คอลัมน์
   - คลิก **✕** เพื่อลบ
   - หากต้องการย้ายหรือปรับขนาดกรอบ ให้ลบแล้ววาดใหม่
6. พิมพ์ **Template name** ที่มุมขวาบน (เช่น "ACME Invoice") แล้วคลิก **💾 Save template**

หากต้องการแก้ไขเทมเพลตที่มีอยู่ภายหลัง: เลือกจากเมนูแล้วคลิก **Load** แก้ไขตามต้องการ แล้ว **Save** อีกครั้ง — ปุ่ม **New** เริ่มเทมเพลตเปล่า, ปุ่ม **Delete** ลบเทมเพลตที่เลือกอยู่

> ไม่จำเป็นต้องวาดกรอบให้พอดีเป๊ะ เพราะกรอบทำหน้าที่เป็น *จุดบอกตำแหน่ง* เท่านั้น โมเดลจะอ่านทั้งหน้าเพื่อดูบริบท ดังนั้นวาดกรอบคร่าว ๆ รอบบริเวณที่ถูกต้องก็ใช้งานได้ดี ขอเพียงให้กรอบอยู่ตรงช่องที่ถูกต้อง

### ขั้นที่ 3 · Extract & Export — เริ่มดึงข้อมูลและส่งออกเป็น Excel

1. เปิดแท็บ **3 · Extract & Export**
2. เลือก **Template** จากเมนู
3. ติ๊กเลือก **เอกสารที่จะประมวลผล** (ค่าเริ่มต้นเลือกทั้งหมด ใช้ **select all** เพื่อสลับเลือก / ไม่เลือก)
4. คลิก **▶ Run extraction** จะมีแอนิเมชันแสดงความคืบหน้าขณะที่โมเดลในเครื่องอ่านเอกสารทีละไฟล์ (ไฟล์ใหญ่หรือหลายหน้าจะใช้เวลานานขึ้น)
5. ตรวจดู **Results** — ตารางสรุปช่องข้อมูลทั่วไป พร้อมตารางแยกต่อเอกสารสำหรับช่องที่เป็นตาราง
6. คลิก **⬇ Export to Excel** แล้วคลิกลิงก์ **Download** ที่ปรากฏขึ้น

### ไฟล์ Excel

- ชีต **`Data`**: หนึ่งแถวต่อหนึ่งเอกสาร และหนึ่งคอลัมน์ต่อหนึ่งช่องข้อมูลทั่วไป พร้อมคอลัมน์ `_file` ระบุชื่อไฟล์ต้นทาง
- **ชีตเพิ่มอีกหนึ่งชีตต่อหนึ่งช่องตาราง** (ตั้งชื่อตามช่องนั้น): หนึ่งแถวต่อหนึ่งแถวของตาราง พร้อมคอลัมน์ `_file` เชื่อมแต่ละแถวกลับไปยังเอกสารต้นทาง

### เคล็ดลับและการแก้ปัญหา

- **สถานะเครื่องมือ (Engine status)** แสดงที่มุมขวาบน ต้องขึ้นว่า **"✓ qwen2.5vl:7b ready"** — หากขึ้นว่า *Ollama not running* ให้ตรวจสอบว่าคอนเทนเนอร์ `ollama` ทำงานอยู่ด้วย `docker compose ps`; หากขึ้นว่าโมเดลยังไม่พร้อม ให้รัน `docker compose exec ollama ollama pull qwen2.5vl:7b`
- **ค่าที่ดึงออกมาผิด?** ตรวจให้แน่ใจว่ากรอบครอบตรงช่องที่ต้องการ และ **Type** ตรงกับชนิดข้อมูล (ใช้ Number สำหรับจำนวนเงิน, Date สำหรับวันที่) — สแกนที่ความละเอียดสูงขึ้นจะดึงข้อมูลได้แม่นยำกว่า ดู `LOCALOCR_DPI` ด้านล่าง
- **การรันซ้ำ** ทำได้ง่าย เพียงปรับเทมเพลตแล้วดึงข้อมูลใหม่
- ทุกอย่างทำงานในเครื่องของคุณ — เอกสารไม่ถูกส่งออกไปนอกเครื่อง

## Configuration

All configuration is via environment variables, set in `.env` (see
`.env.example`). They are passed to the services by `docker-compose.yml`.

| Var | Default | Meaning |
|-----|---------|---------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `localocr` | Database credentials |
| `LOCALOCR_PORT` | `8080` | Host port the app is published on |
| `LOCALOCR_SECRET_KEY` | _(generated)_ | Secret used to sign session cookies — set a long random value in production |
| `LOCALOCR_COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `WEB_CONCURRENCY` | `2` | Number of uvicorn workers in the backend |
| `LOCALOCR_MODEL` | `qwen2.5vl:7b` | Ollama vision model to use |
| `LOCALOCR_DPI` | `200` | Page render resolution |

Internal service URLs (`DATABASE_URL`, `OLLAMA_HOST`, `LOCALOCR_DATA_DIR`) are
wired up in `docker-compose.yml` and rarely need changing.

## Layout

```
docker-compose.yml   defines the four services + named volumes
.env.example         configuration template (copy to .env)
backend/             backend service
  Dockerfile, requirements.txt, entrypoint.sh
  app/
    main.py          FastAPI app (API only)
    config.py        env-driven settings
    database.py      SQLAlchemy engine/session
    models.py        ORM: users, templates, uploads
    security.py      password hashing + session tokens
    deps.py          shared FastAPI dependencies (db, current_user/admin)
    services/        users.py, templates.py (DB-backed logic)
    routers/         auth, admin, uploads, templates, extraction
    pdf_utils.py · extract.py · excel_export.py · ollama_client.py
frontend/            frontend service
  Dockerfile, nginx.conf, index.html, app.js, styles.css
samples/             a generated sample invoice to try

Persistent data lives in Docker named volumes (not in the repo):
  db_data       PostgreSQL  — accounts, templates, upload metadata
  file_data     /data/users/<user_id>/{uploads,pages,exports}/ + secret.key
  ollama_data   the downloaded vision model
```

## Try it now

Upload `samples/sample_invoice.png`, draw boxes over the invoice number, date,
total, and the line-item table, save the template, and run extraction.
