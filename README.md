# LocalOCR

A fully local document data-extraction tool. Upload PDFs/images, **draw boxes**
over the fields you care about, save that layout as a reusable **template**, then
batch-extract those fields from any number of documents and **export to Excel** —
all running on your own machine via a local vision LLM.

- **Engine:** [Ollama](https://ollama.com) + `qwen2.5vl:7b` (vision LLM), on your GPU.
- **Backend:** Python + FastAPI (renders pages, calls the model, writes xlsx).
- **Frontend:** a single-page browser UI with a canvas box editor. No build step.
- **Accounts:** each user signs in; templates and uploaded documents are private
  to that account.
- **Nothing leaves your computer.**

## User accounts

LocalOCR has a built-in login system. On first visit you **create an account**
(username + password), then sign in. Everything you upload and every template you
build is **private to your account** — other users can't see your documents or
templates.

- Passwords are hashed (PBKDF2-HMAC-SHA256, per-user salt) — never stored in
  plain text.
- Sign-in uses a secure httpOnly session cookie that lasts 30 days.
- Accounts and per-user data live under `data/` (see [Layout](#layout)); this
  folder is git-ignored and never leaves your machine.

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
> behind an **HTTPS reverse proxy** (or use an SSH tunnel). See
> [Run · Linux server](#linux-server).

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
| **Windows** | Built and tested on Windows 11. The `run.ps1` / `run.bat` launchers are Windows; the code itself is cross-platform. |
| **Python 3.10+** | Runs the backend, page rendering, and Excel export. |
| **[Ollama](https://ollama.com/download)** | Hosts the local vision model. |
| **Vision model** `qwen2.5vl:7b` | ~6 GB, pulled once with `ollama pull` (see Setup). Does the actual reading. |
| **NVIDIA GPU (recommended)** | ≥6 GB VRAM for smooth performance. CPU-only works but is much slower. |
| **Disk space** | ~6 GB for the model + ~1 GB for the Python venv and rendered pages. |
| **Internet** | One-time only — for `pip install` and the model pull. Everything runs fully offline afterwards. |

**Not required:** Node.js (the frontend is plain HTML/JS with no build step) and Git
(only needed if you `git clone` the repo).

## Setup (one time)

### Windows

```powershell
# 1. Python deps
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Vision model (~6 GB, one time)
ollama pull qwen2.5vl:7b
```

### Linux server (optional)

```bash
# 1. Install Ollama (skip if already installed)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Python deps
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 3. Vision model (~6 GB, one time)
ollama pull qwen2.5vl:7b
```

PyMuPDF ships prebuilt wheels, so no extra system packages are needed. For GPU
acceleration, install the NVIDIA driver — Ollama detects the GPU automatically.

## Run

### Windows

```powershell
.\run.ps1        # or double-click run.bat
```

This starts Ollama (if needed), launches the server, and opens
<http://127.0.0.1:8000>.

**To stop it:** press **`Ctrl + C`** in the terminal, or run **`.\stop.ps1`**
(or double-click **`stop.bat`**). Ollama is left running.

### Linux server

```bash
chmod +x run.sh        # first time only
./run.sh
```

This starts Ollama if it isn't already running and launches the server on
<http://127.0.0.1:8000>. It does **not** open a browser (servers are usually
headless).

**To stop it:** press **`Ctrl + C`**, or run **`./stop.sh`** (if running via
systemd: `sudo systemctl stop localocr`).

**To reach it from another machine**, bind to all interfaces:

```bash
LOCALOCR_HOST=0.0.0.0 ./run.sh
```

Then browse to `http://<server-ip>:8000`.

> ⚠️ **Security:** the app has username/password login, but on plain HTTP those
> credentials travel unencrypted. When exposing it on `0.0.0.0`, put it behind an
> **HTTPS reverse proxy**, or keep the default `127.0.0.1` and reach it through an
> SSH tunnel (`ssh -L 8000:127.0.0.1:8000 user@server`).

**Run it as a background service (systemd):** create
`/etc/systemd/system/localocr.service` —

```ini
[Unit]
Description=LocalOCR
After=network.target

[Service]
WorkingDirectory=/path/to/LocalOCR
ExecStart=/path/to/LocalOCR/run.sh
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

then `sudo systemctl enable --now localocr`.

### Environment overrides (both platforms)

| Var | Default | Purpose |
|-----|---------|---------|
| `LOCALOCR_HOST` | `127.0.0.1` | Interface to bind (Linux `run.sh`). Use `0.0.0.0` for LAN access. |
| `LOCALOCR_PORT` | `8000` | Port to serve on (Linux `run.sh`). |

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
  If it says *Ollama not running*, start Ollama (`ollama serve`); if it says the
  model isn't ready, run `ollama pull qwen2.5vl:7b`.
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

- **สถานะเครื่องมือ (Engine status)** แสดงที่มุมขวาบน ต้องขึ้นว่า **"✓ qwen2.5vl:7b ready"** — หากขึ้นว่า *Ollama not running* ให้เริ่ม Ollama ด้วยคำสั่ง `ollama serve`; หากขึ้นว่าโมเดลยังไม่พร้อม ให้รัน `ollama pull qwen2.5vl:7b`
- **ค่าที่ดึงออกมาผิด?** ตรวจให้แน่ใจว่ากรอบครอบตรงช่องที่ต้องการ และ **Type** ตรงกับชนิดข้อมูล (ใช้ Number สำหรับจำนวนเงิน, Date สำหรับวันที่) — สแกนที่ความละเอียดสูงขึ้นจะดึงข้อมูลได้แม่นยำกว่า ดู `LOCALOCR_DPI` ด้านล่าง
- **การรันซ้ำ** ทำได้ง่าย เพียงปรับเทมเพลตแล้วดึงข้อมูลใหม่
- ทุกอย่างทำงานในเครื่องของคุณ — เอกสารไม่ถูกส่งออกไปนอกเครื่อง

## Configuration

Environment variables (optional):

| Var | Default | Meaning |
|-----|---------|---------|
| `LOCALOCR_MODEL` | `qwen2.5vl:7b` | Ollama vision model to use |
| `LOCALOCR_DPI` | `200` | Page render resolution |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |

## Layout

```
backend/    FastAPI app, auth, rendering, Ollama client, extraction, Excel export
frontend/   index.html + app.js + styles.css (login gate + box editor UI)
data/       runtime data (git-ignored):
              users.json                      account records (hashed passwords)
              secret.key                      session-signing key
              users/<user_id>/templates/      that user's templates (json)
              users/<user_id>/uploads/        that user's original files
              users/<user_id>/pages/          rendered page images
              users/<user_id>/exports/        generated xlsx files
samples/    a generated sample invoice to try
```

## Try it now

Upload `samples/sample_invoice.png`, draw boxes over the invoice number, date,
total, and the line-item table, save the template, and run extraction.
