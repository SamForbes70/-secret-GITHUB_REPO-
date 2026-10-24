# Complete Beginner's Guide to Running Maps4U (`v1.0.2`)

Welcome! If you have just downloaded or cloned the **Maps4U Street Map System** from GitHub and have never run a Python or Docker project before, this guide was written specifically for you. It assumes **zero prior knowledge** of command lines, servers, or cartography.

---

## What Does This Program Actually Do?

**Maps4U** turns any neighborhood or suburb box you draw on a map into a **print-ready, high-resolution PDF street map** (for **A3**, **A4**, or **A5** paper in **Landscape** or **Portrait**). Automatically, it:
1. Checks that every street name will print at **`1.5 mm` or taller** so nobody needs a magnifying glass.
2. Fetches roads, waterways, parks, coastlines, and landmarks from **OpenStreetMap**.
3. Applies the **Maroochydore (`MCY`)** street-map colour and road-casing style.
4. Places street names so **zero labels overlap**.
5. Adds a border grid (`A1..H6`), an alphabetical **Street Index**, a **Scale Bar**, a **North Arrow**, a **Legend**, and copyright attribution.
6. Runs a **7-point automated Quality Assurance (QA) check** and gives you your finished `proof.pdf`!

---

## Step 1: Download the Files onto Your Computer

### Method A: Download a ZIP File (Easiest — No Git Needed)
1. On the main GitHub repository page, click the green **`<> Code`** button near the top right.
2. Click **Download ZIP**.
3. Once downloaded, double-click (or right-click → **Extract All**) to unzip the folder onto your **Desktop**.

### Method B: Clone with Git
If you already have Git installed, open your terminal and run:
```bash
git clone https://github.com/SamForbes70/maps4u-street-map-system.git
cd maps4u-street-map-system
```

---

## Step 2: Open Your Computer's Terminal Inside the Folder

To start the program, you need a terminal window pointing at the Maps4U folder:

- **On Windows:**
  1. Open the unzipped Maps4U folder in **File Explorer**.
  2. Click once in the address bar at the top (where the folder path is shown).
  3. Type `powershell` and press **Enter**. A blue/black PowerShell window will open right inside the folder.
- **On macOS:**
  1. Open **Finder** and locate the Maps4U folder.
  2. Right-click (or two-finger tap) on the folder and click **New Terminal at Folder**.
- **On Linux:**
  1. Open your file manager, right-click inside the Maps4U folder, and click **Open in Terminal**.

> **Quick Check:** Type `ls` and press **Enter**. If you see `README.md`, `Dockerfile`, `docker-compose.yml`, and `pyproject.toml` listed, you are in the exact right spot!

---

## Step 3: Choose How You Want to Start Maps4U

You have **two ways** to run Maps4U. Pick **Path 1 (Docker)** if you want a one-command setup that handles all software dependencies automatically, or **Path 2 (Python)** if you prefer running Python directly on your machine.

### Path 1: Run with Docker Desktop (Recommended for Beginners)

1. Download and install **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (free for personal use on Windows, Mac, and Linux).
2. Open **Docker Desktop** and wait about 15 seconds until the bottom-left status bar says **Engine running**.
3. In your terminal window (from Step 2), type:
   ```bash
   export MAPS4U_OPERATOR_TOKEN="local-operator-secret-token-2026"
export MAPS4U_REVIEWER_TOKEN="local-reviewer-secret-token-2026"
docker compose up --build
   ```
4. **Wait 1–3 minutes** the first time while Docker downloads Python and the mapping tools. When you see:
   ```text
   Uvicorn running on http://0.0.0.0:8000
   ```
   the program is live!
5. Open your web browser (Chrome, Safari, Edge, or Firefox) and go to:
   👉 **`http://localhost:8000`**

---

### Path 2: Run Directly with Python (No Docker Needed)

1. Make sure **Python 3.12 or 3.13** is installed ([Download Python here](https://www.python.org/downloads/)).
   *(Tip for Windows users: During installation, check the box that says **"Add python.exe to PATH"**.)*
2. In your terminal window (from Step 2), run these commands one line at a time:

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ".[dev]"
   cp .env.example .env
   MAPS4U_QUEUE=inline uvicorn maps4u.api.main:create_app --factory --host 127.0.0.1 --port 8080
   ```

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -e ".[dev]"
   Copy-Item .env.example .env
   $env:MAPS4U_QUEUE="inline"
   uvicorn maps4u.api.main:app --host 127.0.0.1 --port 8080
   ```
3. When you see `Uvicorn running on http://127.0.0.1:8080`, open your web browser and go to:
   👉 **`http://127.0.0.1:8080`**

---

## Step 4: Walkthrough — Making Your First Map in the Browser

Once the **Maps4U Operator Console** is open in your browser:

1. **Choose an Area:**
   - Click the **Load Maroochydore Preset** button (or use the polygon drawing icon on the left side of the map to click points around any suburb you like).
2. **Select Paper & Orientation:**
   - Select **`A4`** and **`landscape`** from the dropdown menus.
3. **Click "Check Viability":**
   - A green badge (`VIABLE`) will appear showing the calculated print scale (e.g., `1:12,500`) and confirming that the smallest street label is `>= 1.5 mm`.
   - *(Try selecting `A5` on a huge area to see how the system protects you from printing unreadable text!)*
4. **Create & Run the Job:**
   - Click **Create & Run Job**.
   - Watch the status progress through `validating` → `acquiring` → `styling` → `labelling` → `composing` → `rendering` → `verifying` → **`proof_ready`**.
5. **Download Your Map Files:**
   - **`proof.pdf`** — Click to open or save your vector street map PDF!
   - **`thumb.png`** — View the quick preview image.
   - **`qa-report.md`** — View the automated quality report showing `0` blockers and `0` overlapping labels.
   - **`manifest.json`** — View the cryptographic SHA-256 fingerprint of your map.
6. **Approve or Edit:**
   - Click **Approve** to lock your map as `finalized`, or paste a short YAML snippet in the **Corrections** box to rename a street or add a custom landmark.

---

## Step 5: Beginner Troubleshooting & FAQ

| Problem | Why It Happens | Easy Fix |
| :--- | :--- | :--- |
| **`Cannot connect to the Docker daemon`** | Docker Desktop isn't open yet. | Open the **Docker Desktop** app and wait until it says *Engine running*, then run `export MAPS4U_OPERATOR_TOKEN="local-operator-secret-token-2026"
export MAPS4U_REVIEWER_TOKEN="local-reviewer-secret-token-2026"
docker compose up --build` again. |
| **`Port 8000 (or 8080) is already in use`** | Another window is already running Maps4U. | Check if `http://localhost:8000` is already open in your browser, or change `--port 8080` to `--port 8081`. |
| **`Viability Blocked (MIN_FONT_MM)`** | The area you drew on the map is too large to fit on the selected paper size with readable street names (`>= 1.5 mm`). | Either choose a larger paper size (**`A3`** instead of `A4`/`A5`) or draw a tighter polygon around a smaller neighborhood. |
| **How do I stop the program?** | You finished making maps. | Click inside the terminal window and press **`Ctrl + C`** (or run `docker compose down`). |

---

## Special Note from Winston the Cat 🐾

**Winston the Cat** reminds you that if a step ever takes a moment to build, the best engineering practice is to stretch, blink slowly, and let the deterministic pipeline do the heavy lifting. Thank you, Winston, for your legendary patience!
