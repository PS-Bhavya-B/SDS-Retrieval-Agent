# api.py — FastAPI backend for SDS Retrieval Agent

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from agent_orchestrator import run_for_all, run_for_product

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SDS Retrieval Agent API",
    description="Upload Excel products → AI agent retrieves Safety Data Sheets from supplier websites.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent / "frontend"
DOWNLOADS_DIR = Path(__file__).parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Serve static frontend
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# Serve downloaded SDS files
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

# ---------------------------------------------------------------------------
# In-memory progress store (product_id → last status message)
# ---------------------------------------------------------------------------
_progress: dict[int, str] = {}
_running: set = set()


def _progress_cb(product_id: int, message: str):
    _progress[product_id] = message


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    product_id: int | None = None   # None = run all
    force: bool = False                 # re-run even if result exists


class ProductUpdate(BaseModel):
    supplier: str | None = None
    product_name: str | None = None
    part_number: str | None = None
    cas_number: str | None = None
    language: str | None = None
    jurisdiction: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "message": "SDS Retrieval Agent API is running"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes — Products
# ---------------------------------------------------------------------------

def _parse_file_to_df(contents: bytes, filename: str) -> pd.DataFrame:
    """
    Ultra-robust file parser for uploaded Excel (.xlsx, .xls) and CSV/TSV files.
    Gracefully handles extra unquoted commas, tokenization errors, bad lines,
    delimiter sniffing, and encoding mismatches.
    """
    suffix = Path(filename).suffix.lower()
    is_excel = suffix in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls") or contents.startswith(b"PK\x03\x04")

    # 1. Try Excel engines
    if is_excel:
        for engine in ("openpyxl", "calamine", None):
            try:
                kwargs = {"dtype": str}
                if engine:
                    kwargs["engine"] = engine
                return pd.read_excel(io.BytesIO(contents), **kwargs)
            except Exception:
                continue

    # 2. Try CSV parsing with on_bad_lines='skip' across encodings
    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252", "iso-8859-1"]
    
    for enc in encodings:
        try:
            return pd.read_csv(
                io.BytesIO(contents),
                dtype=str,
                encoding=enc,
                on_bad_lines="skip",
            )
        except Exception:
            pass

    # 3. Python engine with automatic delimiter sniffing (handles , ; \t |)
    for enc in encodings:
        try:
            return pd.read_csv(
                io.BytesIO(contents),
                dtype=str,
                encoding=enc,
                sep=None,
                engine="python",
                on_bad_lines="skip",
            )
        except Exception:
            pass

    # 4. Explicit separators with on_bad_lines='skip'
    for enc in encodings:
        for sep in [",", ";", "\t", "|"]:
            try:
                return pd.read_csv(
                    io.BytesIO(contents),
                    dtype=str,
                    encoding=enc,
                    sep=sep,
                    on_bad_lines="skip",
                )
            except Exception:
                pass

    # 5. Fallback to openpyxl if file was actually an excel file with wrong extension
    try:
        return pd.read_excel(io.BytesIO(contents), dtype=str, engine="openpyxl")
    except Exception:
        pass

    raise ValueError("Unable to parse file format. Please ensure it is a valid CSV or Excel document.")


@app.post("/upload", tags=["products"])
async def upload_excel(file: UploadFile = File(...)):
    """
    Accept an Excel (.xlsx / .xls) or CSV file, parse it, store rows in SQLite.
    Returns { inserted: N, products: [...] }
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    contents = await file.read()

    try:
        df = _parse_file_to_df(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    # Drop all completely empty rows and columns
    df = df.dropna(how="all").dropna(axis=1, how="all")

    if df.empty:
        raise HTTPException(400, "The uploaded sheet is empty or contains no readable rows.")

    try:
        ids = db.insert_products_from_df(df)
    except Exception as e:
        raise HTTPException(500, f"Database error processing sheet: {e}")

    products = [db.get_product(pid) for pid in ids]
    return {"inserted": len(ids), "products": products}


@app.get("/products", tags=["products"])
def list_products():
    """Return all products in the database."""
    return db.get_products()


@app.get("/products/{product_id}", tags=["products"])
def get_product(product_id: int):
    p = db.get_product(product_id)
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    return p


@app.patch("/products/{product_id}", tags=["products"])
def update_product(product_id: int, body: ProductUpdate):
    """Edit product metadata (e.g. fix the language or jurisdiction before re-running)."""
    session = db.get_session()
    try:
        p = session.get(db.Product, product_id)
        if not p:
            raise HTTPException(404, f"Product {product_id} not found")
        for field, val in body.model_dump(exclude_none=True).items():
            setattr(p, field, val)
        session.commit()
        session.refresh(p)
        return p.to_dict()
    finally:
        session.close()


@app.delete("/products/{product_id}", tags=["products"])
def delete_product(product_id: int):
    session = db.get_session()
    try:
        p = session.get(db.Product, product_id)
        if not p:
            raise HTTPException(404, f"Product {product_id} not found")
        session.delete(p)
        session.commit()
        return {"deleted": product_id}
    finally:
        session.close()


@app.delete("/products", tags=["products"])
def clear_products():
    """Delete ALL products and results from the database."""
    session = db.get_session()
    try:
        session.query(db.SdsResult).delete()
        session.query(db.Product).delete()
        session.commit()
        return {"cleared": True}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Routes — SDS Search (triggers agents)
# ---------------------------------------------------------------------------

@app.post("/search", tags=["sds"])
async def search_sds(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Trigger SDS retrieval for one product (product_id) or all products.
    Runs as a background task. Poll /progress or /results to see updates.
    """
    if request.product_id is not None:
        pid = request.product_id
        if pid in _running and not request.force:
            return {"queued": False, "message": f"Product {pid} is already being processed"}
        _running.add(pid)

        async def _run_one():
            try:
                await run_for_product(pid, progress_cb=_progress_cb)
            finally:
                _running.discard(pid)

        background_tasks.add_task(asyncio.ensure_future, _run_one())
        return {"queued": True, "product_id": pid}

    else:
        if "all" in _running:
            return {"queued": False, "message": "Batch run already in progress"}
        _running.add("all")

        async def _run_batch():
            try:
                await run_for_all(progress_cb=_progress_cb)
            finally:
                _running.discard("all")

        background_tasks.add_task(asyncio.ensure_future, _run_batch())
        return {"queued": True, "message": "Batch SDS retrieval started"}


@app.post("/search/sync/{product_id}", tags=["sds"])
async def search_sds_sync(product_id: int):
    """
    Synchronous (blocking) SDS retrieval for one product.
    Returns the result immediately. Useful for small batches or testing.
    """
    p = db.get_product(product_id)
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    result = await run_for_product(product_id, progress_cb=_progress_cb)
    return result


# ---------------------------------------------------------------------------
# Routes — Results
# ---------------------------------------------------------------------------

@app.get("/results", tags=["sds"])
def list_results(product_id: int | None = None):
    """Return all SDS results, optionally filtered by product_id."""
    return db.get_results(product_id=product_id)


@app.get("/progress", tags=["sds"])
def get_progress():
    """Return the last progress message for each product being processed."""
    return {"progress": _progress, "running": list(_running)}


@app.get("/progress/{product_id}", tags=["sds"])
def get_product_progress(product_id: int):
    return {
        "product_id": product_id,
        "message":    _progress.get(product_id, "idle"),
        "running":    product_id in _running,
    }


# ---------------------------------------------------------------------------
# Routes — Download
# ---------------------------------------------------------------------------

@app.get("/download/{result_id}", tags=["download"])
def download_sds(result_id: int):
    """
    Stream the downloaded SDS PDF for the given result.
    If the file has not been downloaded yet, triggers download first.
    """
    result = db.get_result_by_id(result_id)
    if not result:
        raise HTTPException(404, f"Result {result_id} not found")

    local_path = None
    if result.filename:
        candidate = DOWNLOADS_DIR / result.filename
        if candidate.exists():
            local_path = candidate

    if local_path is None and result.url:
        # Trigger download on the fly
        import requests
        HEADERS = {"User-Agent": "Mozilla/5.0 SDS-Agent/1.0"}
        try:
            resp = requests.get(result.url, headers=HEADERS, timeout=60, stream=True)
            resp.raise_for_status()
            fname = result.filename or f"sds_{result_id}.pdf"
            local_path = DOWNLOADS_DIR / fname
            with open(local_path, "wb") as f:
                f.writelines(resp.iter_content(65536))
            # Update filename in DB
            session = db.get_session()
            try:
                r = session.get(db.SdsResult, result_id)
                if r:
                    r.filename = fname
                    session.commit()
            finally:
                session.close()
        except Exception as e:
            raise HTTPException(502, f"Failed to download SDS from source: {e}")

    if local_path is None or not local_path.exists():
        raise HTTPException(404, "SDS file not available. Run retrieval first.")

    return FileResponse(
        path=str(local_path),
        media_type="application/pdf",
        filename=local_path.name,
    )


@app.get("/download/url/{result_id}", tags=["download"])
def get_download_url(result_id: int):
    """Return the source URL for a result (open in browser)."""
    result = db.get_result_by_id(result_id)
    if not result:
        raise HTTPException(404, f"Result {result_id} not found")
    if not result.url:
        raise HTTPException(404, "No URL available for this result")
    return {"url": result.url, "filename": result.filename}


# ---------------------------------------------------------------------------
# Routes — Evaluation Metrics
# ---------------------------------------------------------------------------

@app.get("/metrics", tags=["metrics"])
def get_evaluation_metrics():
    """
    Compute real-time evaluation metrics for SDS retrieval performance:
    - Total Products, Total Processed
    - Retrieval Success Rate (%)
    - Precision / Supplier Breakdown
    - Jurisdiction & Language Match Accuracy
    """
    products = db.get_products()
    results = db.get_results()
    
    total_products = len(products)
    len(results)
    
    result_map = {r["product_id"]: r for r in results}
    
    found_count = 0
    not_found_count = 0
    error_count = 0
    pending_count = 0
    
    supplier_stats: dict[str, dict[str, int]] = {}
    jurisdiction_stats: dict[str, dict[str, int]] = {}
    language_stats: dict[str, dict[str, int]] = {}
    
    for p in products:
        sup = p.get("supplier") or "Unknown"
        juris = p.get("jurisdiction") or "US"
        lang = p.get("language") or "EN"
        
        if sup not in supplier_stats:
            supplier_stats[sup] = {"total": 0, "found": 0, "not_found": 0}
        supplier_stats[sup]["total"] += 1
        
        if juris not in jurisdiction_stats:
            jurisdiction_stats[juris] = {"total": 0, "found": 0}
        jurisdiction_stats[juris]["total"] += 1
        
        if lang not in language_stats:
            language_stats[lang] = {"total": 0, "found": 0}
        language_stats[lang]["total"] += 1
        
        res = result_map.get(p["id"])
        if not res or res.get("status") == "pending":
            pending_count += 1
        elif res.get("status") == "found":
            found_count += 1
            supplier_stats[sup]["found"] += 1
            jurisdiction_stats[juris]["found"] += 1
            language_stats[lang]["found"] += 1
        elif res.get("status") == "error":
            error_count += 1
            supplier_stats[sup]["not_found"] += 1
        else:
            not_found_count += 1
            supplier_stats[sup]["not_found"] += 1

    processed_count = found_count + not_found_count + error_count
    retrieval_rate = round((found_count / processed_count * 100), 1) if processed_count > 0 else 0.0

    return {
        "summary": {
            "total_products": total_products,
            "processed": processed_count,
            "found": found_count,
            "not_found": not_found_count,
            "error": error_count,
            "pending": pending_count,
            "success_rate_percent": retrieval_rate,
        },
        "supplier_breakdown": supplier_stats,
        "jurisdiction_breakdown": jurisdiction_stats,
        "language_breakdown": language_stats
    }


# ---------------------------------------------------------------------------
# Routes — Sample Excel template download
# ---------------------------------------------------------------------------

@app.get("/template", tags=["products"])
def download_template():
    """Download a sample Excel template with the expected column headers."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    headers = ["Supplier", "Product Name", "Part Number", "CAS Number", "Language", "Jurisdiction", "Notes"]
    ws.append(headers)
    sample_rows = [
        ["ThermoFisher", "Acetonitrile HPLC Grade", "A/0626/17", "75-05-8", "EN", "US", ""],
        ["Sigma Aldrich", "Ethanol 99.8%", "459836", "64-17-5", "EN", "US", ""],
        ["Enamine", "Methyl 4-bromobenzoate", "EN300-19035", "", "EN", "EU", ""],
        ["BLD Pharmatech", "4-Chlorobenzaldehyde", "BD10456", "104-88-1", "EN", "GHS", ""],
        ["Pharmablock", "Boc-L-Proline", "PB10001", "", "EN", "GHS", ""],
    ]
    for row in sample_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sds_template.xlsx"},
    )
