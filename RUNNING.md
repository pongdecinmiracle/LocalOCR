# LocalOCR — How to Run the App

A step-by-step manual for installing, starting, operating, and troubleshooting
LocalOCR. For *using* the app (uploading, templates, extraction) see the
[How to use the application](README.md#how-to-use-the-application) section of
the README.

> 🇹🇭 ภาษาไทย: ดู [คู่มือการรันแอป (ภาษาไทย)](#localocr--คู่มือการรันแอป-ภาษาไทย) ด้านล่าง

---

## 1. What you need

| Requirement | Notes |
|-------------|-------|
| **Docker Desktop** (Windows/macOS) or **Docker Engine + Compose v2** (Linux) | The only hard requirement. On Windows, use the WSL2 backend (default). |
| **~12 GB free disk** | ~6 GB for the vision model, the rest for images, the database, and your documents. |
| **NVIDIA GPU** *(optional)* | ≥6 GB VRAM makes extraction much faster. CPU-only works but is slow. |
| **Internet** *(first run only)* | To pull base images and the model. Fully offline afterwards. |

You do **not** need Python, Node.js, or a local Ollama install — everything
runs in containers.

---

## 2. First-time setup

All commands run from the project folder (the one containing
`docker-compose.yml`).

### Step 1 — Create your configuration

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Open `.env` in any editor and set **at minimum**:

| Setting | What to put there |
|---------|-------------------|
| `POSTGRES_PASSWORD` | A long random password. **Required — the stack refuses to start without it.** |
| `LOCALOCR_SECRET_KEY` | A long random value. Generate one with: `python -c "import secrets; print(secrets.token_hex(32))"` (or any 64-char random hex string). |

Worth deciding now:

| Setting | Default | Consider |
|---------|---------|----------|
| `LOCALOCR_ALLOW_REGISTRATION` | `true` | Set `false` for invite-only — only admins can add accounts. |
| `LOCALOCR_PORT` | `8080` | The port the app is served on. |
| `LOCALOCR_USER_QUOTA_MB` | `2048` | Storage allowance per user. |

### Step 2 — (Optional) GPU

The compose file ships with NVIDIA GPU passthrough **enabled** for the model
service. If you do **not** have an NVIDIA GPU, open `docker-compose.yml` and
comment out the `deploy:` block under the `ollama` service, otherwise the
stack may fail to start:

```yaml
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

(On Linux with a GPU, install the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
first. On Windows, Docker Desktop's WSL2 backend handles it.)

### Step 3 — Build and start everything

```bash
docker compose up -d --build
```

The first build takes a few minutes. Database migrations run automatically on
startup — no manual schema steps, now or after updates.

> **Shortcut (Windows):** `.\run.ps1` (or double-click `run.bat`) does Steps 1
> and 3 for you and opens the browser. You still must edit `.env` and set a
> real `POSTGRES_PASSWORD`.

### Step 4 — Download the vision model (one time, ~6 GB)

```bash
docker compose exec ollama ollama pull qwen2.5vl:7b
```

### Step 5 — Create the admin account

Open **http://localhost:8080** (or your `LOCALOCR_PORT`). Click **Create an
account** and sign up — **the first account becomes the administrator.** The
engine status at the top right should read **"✓ qwen2.5vl:7b ready"**.

Setup is done. Add more users from the **⚙ Admin** tab (or let people
self-register if you left registration open).

---

## 3. Day-to-day operation

### Start / stop

```bash
docker compose up -d        # start (or .\run.ps1 / run.bat on Windows)
docker compose down         # stop — all data is preserved
```

Containers restart automatically after a reboot or crash (`restart:
unless-stopped`), so normally you start the stack once and forget it.

> ⚠️ `docker compose down -v` **deletes everything** — database, documents,
> and the downloaded model. Only use it to wipe the installation.

### Check health

```bash
docker compose ps           # all four services should be "running" / "healthy"
```

| Service | Role |
|---------|------|
| `frontend` | Web UI + reverse proxy (the only published port) |
| `backend` | API, extraction job queue, Excel export |
| `db` | PostgreSQL (accounts, templates, metadata, jobs) |
| `ollama` | The local vision model |

### Read logs

```bash
docker compose logs -f              # everything, follow mode
docker compose logs -f backend     # API + extraction jobs (login events, job progress, errors)
docker compose logs --tail 100 ollama
```

Logs are rotated automatically (10 MB × 3 files per service).

### Back up

Run while the stack is up; output lands in `./backups/`:

```bash
# Windows
.\scripts\backup.ps1

# Linux / macOS
sh scripts/backup.sh
```

This produces a PostgreSQL dump (`db_<timestamp>.dump`) and an archive of all
user files (`files_<timestamp>.tgz`). Schedule it with Task Scheduler / cron
for regular backups. Restore commands are documented at the top of
`scripts/backup.sh`.

### Update to a new version

```bash
git pull
docker compose up -d --build       # rebuilds changed images; migrations apply on start
```

---

## 4. Serving other machines (LAN / team use)

The app is already reachable at `http://<host-ip>:8080` from other machines.
Before you invite a team:

1. **Use HTTPS.** On plain HTTP, passwords travel unencrypted. Put a
   TLS-terminating reverse proxy (Caddy, Traefik, nginx, …) in front of the
   `frontend` service and set `LOCALOCR_COOKIE_SECURE=true` in `.env`.
2. **Decide who can join.** Set `LOCALOCR_ALLOW_REGISTRATION=false` to make
   the instance invite-only; add accounts from the Admin tab.
3. **Capacity.** The defaults (4 backend workers, background extraction jobs)
   comfortably serve 10+ concurrent users. Extraction speed is bound by the
   GPU — jobs queue up fairly and the UI stays responsive while they run.

After changing `.env`, apply with:

```bash
docker compose up -d
```

---

## 5. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Stack won't start: `set POSTGRES_PASSWORD in .env` | You skipped Step 1 — create `.env` and set a password. |
| Status shows **⚠ Ollama not running** | `docker compose ps` — if `ollama` is restarting and you have no NVIDIA GPU, comment out the GPU `deploy:` block (Section 2, Step 2). |
| Status shows **⏳ model not ready** | The model isn't downloaded: `docker compose exec ollama ollama pull qwen2.5vl:7b` |
| **⚠ backend offline** in the UI | `docker compose logs backend` — most often the database password in `.env` was changed after the DB volume was created (see next row). |
| Backend can't connect to the DB after you changed `POSTGRES_PASSWORD` | The DB keeps the *original* password from its first start. Either change `.env` back, or reset the DB user: `docker compose exec db psql -U localocr -c "ALTER USER localocr PASSWORD 'new-password';"` then update `.env` and `docker compose up -d`. |
| Login says **Too many failed attempts** | Brute-force lockout — wait 5 minutes and try again. |
| Upload rejected: file type / size / quota | Allowed types: PDF, PNG, JPG, TIFF, BMP, WEBP. Per-file and per-user limits are set in `.env` (`LOCALOCR_MAX_UPLOAD_MB`, `LOCALOCR_USER_QUOTA_MB`). |
| Extraction job ended with *"Interrupted by a server restart"* | The server restarted mid-job. Just run the extraction again. |
| Extraction is very slow | CPU-only mode is expected to be slow. Use an NVIDIA GPU (Section 2, Step 2), or lower `LOCALOCR_DPI` (e.g. 150) at some accuracy cost. |
| Forgot the admin password | Any other admin can reset it from the Admin tab. If there is no other admin: `docker compose exec db psql -U localocr -d localocr -c "UPDATE users SET is_admin=true WHERE username_key='<some username, lowercase>';"` then restart the backend and have that user reset passwords. |
| Port 8080 already in use | Change `LOCALOCR_PORT` in `.env`, then `docker compose up -d`. |

### Full reset (wipe everything)

```bash
docker compose down -v     # removes DB, all documents, and the model
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5vl:7b
```

---
---

# LocalOCR — คู่มือการรันแอป (ภาษาไทย)

คู่มือทีละขั้นตอนสำหรับการติดตั้ง เริ่มใช้งาน ดูแลระบบ และแก้ปัญหา LocalOCR
ส่วน *วิธีใช้งาน* ตัวแอป (อัปโหลดเอกสาร สร้างเทมเพลต ดึงข้อมูล) ดูได้ที่หัวข้อ
[วิธีใช้งานแอปพลิเคชัน (ภาษาไทย)](README.md#วิธีใช้งานแอปพลิเคชัน-ภาษาไทย) ใน README

> 🇬🇧 English: see the [English manual](#localocr--how-to-run-the-app) above.

---

## 1. สิ่งที่ต้องมี

| สิ่งที่ต้องมี | หมายเหตุ |
|-------------|---------|
| **Docker Desktop** (Windows/macOS) หรือ **Docker Engine + Compose v2** (Linux) | ข้อกำหนดเดียวที่จำเป็น — บน Windows ให้ใช้ WSL2 backend (ค่าเริ่มต้น) |
| **พื้นที่ดิสก์ว่าง ~12 GB** | ~6 GB สำหรับโมเดล ที่เหลือสำหรับรูปภาพ ฐานข้อมูล และเอกสารของคุณ |
| **การ์ดจอ NVIDIA** *(ไม่บังคับ)* | VRAM ≥6 GB ทำให้ดึงข้อมูลเร็วขึ้นมาก — ใช้ CPU อย่างเดียวก็ได้แต่ช้า |
| **อินเทอร์เน็ต** *(ครั้งแรกเท่านั้น)* | ใช้ดาวน์โหลด image และโมเดล หลังจากนั้นทำงานออฟไลน์ได้ทั้งหมด |

**ไม่ต้อง**ติดตั้ง Python, Node.js หรือ Ollama บนเครื่อง — ทุกอย่างรันในคอนเทนเนอร์

---

## 2. การติดตั้งครั้งแรก

คำสั่งทั้งหมดรันจากโฟลเดอร์โปรเจกต์ (โฟลเดอร์ที่มีไฟล์ `docker-compose.yml`)

### ขั้นที่ 1 — สร้างไฟล์ค่าตั้งค่า

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

เปิดไฟล์ `.env` ด้วยโปรแกรมแก้ไขข้อความใดก็ได้ แล้วตั้งค่า**อย่างน้อย**:

| ค่าตั้งค่า | สิ่งที่ต้องใส่ |
|-----------|--------------|
| `POSTGRES_PASSWORD` | รหัสผ่านแบบสุ่มที่ยาว **จำเป็นต้องตั้ง — ระบบจะไม่ยอมเริ่มทำงานถ้าไม่ตั้งค่านี้** |
| `LOCALOCR_SECRET_KEY` | ค่าสุ่มที่ยาว สร้างได้ด้วย: `python -c "import secrets; print(secrets.token_hex(32))"` (หรือสตริง hex สุ่มยาว 64 ตัวอักษร) |

ค่าที่ควรตัดสินใจตั้งแต่ตอนนี้:

| ค่าตั้งค่า | ค่าเริ่มต้น | พิจารณา |
|-----------|-----------|---------|
| `LOCALOCR_ALLOW_REGISTRATION` | `true` | ตั้งเป็น `false` ถ้าต้องการระบบแบบเชิญเท่านั้น — เฉพาะแอดมินเพิ่มบัญชีได้ |
| `LOCALOCR_PORT` | `8080` | พอร์ตที่เปิดให้เข้าใช้งานแอป |
| `LOCALOCR_USER_QUOTA_MB` | `2048` | โควตาพื้นที่จัดเก็บต่อผู้ใช้หนึ่งคน |

### ขั้นที่ 2 — (ไม่บังคับ) การ์ดจอ GPU

ไฟล์ compose ที่ให้มา**เปิดใช้** NVIDIA GPU passthrough สำหรับเซอร์วิสโมเดลไว้แล้ว
ถ้าเครื่องของคุณ**ไม่มี**การ์ดจอ NVIDIA ให้เปิด `docker-compose.yml` แล้ว
คอมเมนต์บล็อก `deploy:` ใต้เซอร์วิส `ollama` ออก ไม่เช่นนั้นระบบอาจเริ่มทำงานไม่ได้:

```yaml
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

(บน Linux ที่มี GPU ให้ติดตั้ง
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
ก่อน ส่วนบน Windows Docker Desktop ที่ใช้ WSL2 backend จัดการให้อยู่แล้ว)

### ขั้นที่ 3 — Build และเริ่มระบบทั้งหมด

```bash
docker compose up -d --build
```

การ build ครั้งแรกใช้เวลาสองสามนาที ระบบจะรัน database migration
ให้อัตโนมัติตอนเริ่มทำงาน — ไม่ต้องจัดการ schema เองทั้งตอนนี้และหลังอัปเดต

> **ทางลัด (Windows):** `.\run.ps1` (หรือดับเบิลคลิก `run.bat`) ทำขั้นที่ 1 และ 3
> ให้และเปิดเบราว์เซอร์อัตโนมัติ แต่คุณยังต้องแก้ `.env` และตั้ง
> `POSTGRES_PASSWORD` จริง ๆ เอง

### ขั้นที่ 4 — ดาวน์โหลดโมเดล (ครั้งเดียว ~6 GB)

```bash
docker compose exec ollama ollama pull qwen2.5vl:7b
```

### ขั้นที่ 5 — สร้างบัญชีแอดมิน

เปิด **http://localhost:8080** (หรือพอร์ตตาม `LOCALOCR_PORT` ที่ตั้งไว้) คลิก
**Create an account** แล้วสมัคร — **บัญชีแรกจะเป็นผู้ดูแลระบบ (แอดมิน) โดยอัตโนมัติ**
สถานะเครื่องมือมุมขวาบนควรขึ้นว่า **"✓ qwen2.5vl:7b ready"**

เสร็จแล้ว! เพิ่มผู้ใช้คนอื่นได้จากแท็บ **⚙ Admin** (หรือเปิดให้สมัครเองถ้าไม่ได้ปิด
registration ไว้)

---

## 3. การใช้งานประจำวัน

### เริ่ม / หยุด

```bash
docker compose up -d        # เริ่ม (หรือใช้ .\run.ps1 / run.bat บน Windows)
docker compose down         # หยุด — ข้อมูลทั้งหมดยังอยู่ครบ
```

คอนเทนเนอร์จะรีสตาร์ตเองหลังรีบูตเครื่องหรือเมื่อล่ม (`restart: unless-stopped`)
ดังนั้นปกติแค่เริ่มระบบครั้งเดียวแล้วปล่อยทิ้งไว้ได้เลย

> ⚠️ `docker compose down -v` **ลบทุกอย่าง** — ฐานข้อมูล เอกสาร และโมเดลที่ดาวน์โหลดไว้
> ใช้เฉพาะเมื่อต้องการล้างระบบทิ้งทั้งหมดเท่านั้น

### ตรวจสุขภาพระบบ

```bash
docker compose ps           # ทั้งสี่เซอร์วิสควรเป็น "running" / "healthy"
```

| เซอร์วิส | หน้าที่ |
|---------|--------|
| `frontend` | หน้าเว็บ + reverse proxy (พอร์ตเดียวที่เปิดสู่ภายนอก) |
| `backend` | API, คิวงานดึงข้อมูล, ส่งออก Excel |
| `db` | PostgreSQL (บัญชี เทมเพลต ข้อมูลไฟล์ งานในคิว) |
| `ollama` | โมเดล vision ที่รันในเครื่อง |

### ดู log

```bash
docker compose logs -f              # ทั้งหมด แบบติดตามต่อเนื่อง
docker compose logs -f backend     # API + งานดึงข้อมูล (เหตุการณ์ล็อกอิน ความคืบหน้างาน ข้อผิดพลาด)
docker compose logs --tail 100 ollama
```

Log ถูกหมุนเวียน (rotate) อัตโนมัติ (10 MB × 3 ไฟล์ต่อเซอร์วิส)

### สำรองข้อมูล (Backup)

รันขณะที่ระบบเปิดอยู่ ผลลัพธ์จะอยู่ใน `./backups/`:

```bash
# Windows
.\scripts\backup.ps1

# Linux / macOS
sh scripts/backup.sh
```

จะได้ไฟล์ dump ของ PostgreSQL (`db_<timestamp>.dump`) และไฟล์บีบอัดของไฟล์ผู้ใช้
ทั้งหมด (`files_<timestamp>.tgz`) ตั้งเวลารันอัตโนมัติได้ด้วย Task Scheduler / cron
คำสั่งสำหรับกู้คืน (restore) อยู่ที่หัวไฟล์ `scripts/backup.sh`

### อัปเดตเป็นเวอร์ชันใหม่

```bash
git pull
docker compose up -d --build       # build ใหม่เฉพาะ image ที่เปลี่ยน migration รันให้เองตอนเริ่ม
```

---

## 4. เปิดให้เครื่องอื่นใช้งาน (LAN / ใช้เป็นทีม)

แอปเข้าถึงได้จากเครื่องอื่นที่ `http://<ip-เครื่องโฮสต์>:8080` อยู่แล้ว
ก่อนชวนทีมมาใช้ ควรทำสิ่งเหล่านี้:

1. **ใช้ HTTPS** — บน HTTP ธรรมดา รหัสผ่านวิ่งบนเครือข่ายแบบไม่เข้ารหัส
   ให้ตั้ง reverse proxy ที่ทำ TLS (Caddy, Traefik, nginx ฯลฯ) ไว้หน้าเซอร์วิส
   `frontend` แล้วตั้ง `LOCALOCR_COOKIE_SECURE=true` ใน `.env`
2. **กำหนดว่าใครเข้าร่วมได้** — ตั้ง `LOCALOCR_ALLOW_REGISTRATION=false`
   เพื่อให้เป็นระบบเชิญเท่านั้น แล้วเพิ่มบัญชีจากแท็บ Admin
3. **ความจุ** — ค่าเริ่มต้น (backend 4 workers + งานดึงข้อมูลแบบเบื้องหลัง)
   รองรับผู้ใช้พร้อมกัน 10+ คนได้สบาย ความเร็วการดึงข้อมูลขึ้นกับ GPU —
   งานจะเข้าคิวตามลำดับอย่างยุติธรรม และหน้าเว็บยังตอบสนองตามปกติระหว่างนั้น

หลังแก้ `.env` ให้สั่ง:

```bash
docker compose up -d
```

---

## 5. การแก้ปัญหา

| อาการ | วิธีแก้ |
|-------|--------|
| ระบบไม่เริ่ม: `set POSTGRES_PASSWORD in .env` | ข้ามขั้นที่ 1 ไป — สร้าง `.env` แล้วตั้งรหัสผ่าน |
| สถานะขึ้น **⚠ Ollama not running** | ดู `docker compose ps` — ถ้า `ollama` รีสตาร์ตวนและเครื่องไม่มีการ์ดจอ NVIDIA ให้คอมเมนต์บล็อก GPU `deploy:` ออก (หัวข้อ 2 ขั้นที่ 2) |
| สถานะขึ้น **⏳ model not ready** | ยังไม่ได้ดาวน์โหลดโมเดล: `docker compose exec ollama ollama pull qwen2.5vl:7b` |
| หน้าเว็บขึ้น **⚠ backend offline** | ดู `docker compose logs backend` — สาเหตุที่พบบ่อยที่สุดคือแก้รหัสผ่านฐานข้อมูลใน `.env` หลังจากที่สร้าง DB volume ไปแล้ว (ดูแถวถัดไป) |
| Backend ต่อฐานข้อมูลไม่ได้หลังเปลี่ยน `POSTGRES_PASSWORD` | ฐานข้อมูลยังจำรหัสผ่าน*เดิม*จากการเริ่มครั้งแรกอยู่ — แก้ `.env` กลับเป็นค่าเดิม หรือเปลี่ยนรหัสในฐานข้อมูล: `docker compose exec db psql -U localocr -c "ALTER USER localocr PASSWORD 'new-password';"` แล้วอัปเดต `.env` และสั่ง `docker compose up -d` |
| ล็อกอินขึ้น **Too many failed attempts** | ระบบป้องกันการเดารหัสผ่าน — รอ 5 นาทีแล้วลองใหม่ |
| อัปโหลดถูกปฏิเสธ: ชนิดไฟล์ / ขนาด / โควตา | ชนิดไฟล์ที่รองรับ: PDF, PNG, JPG, TIFF, BMP, WEBP — ขีดจำกัดต่อไฟล์และต่อผู้ใช้ตั้งได้ใน `.env` (`LOCALOCR_MAX_UPLOAD_MB`, `LOCALOCR_USER_QUOTA_MB`) |
| งานดึงข้อมูลจบด้วยข้อความ *"Interrupted by a server restart"* | เซิร์ฟเวอร์รีสตาร์ตระหว่างทำงาน — สั่งรันดึงข้อมูลใหม่อีกครั้งได้เลย |
| ดึงข้อมูลช้ามาก | โหมด CPU อย่างเดียวช้าเป็นปกติ — ใช้การ์ดจอ NVIDIA (หัวข้อ 2 ขั้นที่ 2) หรือลด `LOCALOCR_DPI` (เช่น 150) แลกกับความแม่นยำที่ลดลงเล็กน้อย |
| ลืมรหัสผ่านแอดมิน | แอดมินคนอื่นรีเซ็ตให้ได้จากแท็บ Admin — ถ้าไม่มีแอดมินคนอื่น: `docker compose exec db psql -U localocr -d localocr -c "UPDATE users SET is_admin=true WHERE username_key='<ชื่อผู้ใช้ ตัวพิมพ์เล็ก>';"` แล้วรีสตาร์ต backend จากนั้นให้ผู้ใช้คนนั้นไปรีเซ็ตรหัสผ่าน |
| พอร์ต 8080 ถูกใช้อยู่แล้ว | เปลี่ยน `LOCALOCR_PORT` ใน `.env` แล้วสั่ง `docker compose up -d` |

### ล้างระบบทั้งหมด (ลบทุกอย่าง)

```bash
docker compose down -v     # ลบฐานข้อมูล เอกสารทั้งหมด และโมเดล
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5vl:7b
```
