# LocalOCR

A fully local document data-extraction tool. Upload PDFs/images, **draw boxes**
over the fields you care about, save that layout as a reusable **template**, then
batch-extract those fields from any number of documents and **export to Excel** —
all running on your own machine via a local vision LLM.

- **Engine:** [Ollama](https://ollama.com) + `qwen2.5vl:7b` (vision LLM), on your GPU.
- **Backend:** Python + FastAPI (renders pages, calls the model, writes xlsx).
- **Frontend:** a single-page browser UI with a canvas box editor. No build step.
- **Nothing leaves your computer.**

## How it works

For each page, LocalOCR sends the **whole page** to the vision model and asks for
all the template's fields at once as structured JSON. The boxes you draw define
*which* fields exist, their type (text / number / date / **table**), table
columns, and a location hint that tells the model where to look. Full-page
context is far more accurate than tiny per-field crops.

## Setup (one time)

Already done if Claude set this up, but to reproduce:

```powershell
# 1. Python deps
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Vision model (~6 GB, one time)
ollama pull qwen2.5vl:7b
```

## Run

```powershell
.\run.ps1        # or double-click run.bat
```

This starts Ollama (if needed), launches the server, and opens
<http://127.0.0.1:8000>.

## How to use the application

The app has three tabs across the top — work through them left to right.

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

## Configuration

Environment variables (optional):

| Var | Default | Meaning |
|-----|---------|---------|
| `LOCALOCR_MODEL` | `qwen2.5vl:7b` | Ollama vision model to use |
| `LOCALOCR_DPI` | `200` | Page render resolution |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |

## Layout

```
backend/    FastAPI app, rendering, Ollama client, extraction, Excel export
frontend/   index.html + app.js + styles.css (the box editor UI)
data/       uploads, rendered pages, templates (json), exports (xlsx)
samples/    a generated sample invoice to try
```

## Try it now

Upload `samples/sample_invoice.png`, draw boxes over the invoice number, date,
total, and the line-item table, save the template, and run extraction.
