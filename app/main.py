"""DocuFlow: invoices and forms to Excel."""
from __future__ import annotations

import io
import json
import logging
import re
import secrets
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, exporter, pipeline
from .config import (APP_NAME, BRAND_DIR, CONTACT_EMAIL, CONTACT_WHATSAPP, DEMO_EMAIL, MANUAL_MINUTES_PER_DOC, MAX_FILE_MB, MAX_FILES_PER_BATCH,
                     PAGES_DIR, SAMPLE_DIR, STATIC_DIR, UPLOAD_DIR, ai_enabled)
from .presets import DOC_TYPE_LABELS, FIELDS, default_config, get_preset, list_presets
from .reader import IMAGE_EXT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)
COOKIE = "df_session"
ALLOWED = IMAGE_EXT | {".pdf"}


# --------------------------------------------------------------------------- startup
@app.on_event("startup")
def startup():
    db.init_db()
    # documents interrupted by a restart are re-queued
    for b in db.query("SELECT id FROM batches WHERE status IN ('queued','processing')"):
        db.execute("UPDATE documents SET status='queued', stage=NULL WHERE batch_id=? AND status IN ('queued','processing')", (b["id"],))
        pipeline.start_batch(b["id"])
    if not db.one("SELECT id FROM batches WHERE is_sample=1"):
        create_sample_batch(name="Sample batch: September suppliers", user_id=None)
    pipeline.apply_retention()


# --------------------------------------------------------------------------- auth
def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    user = db.one("SELECT u.id, u.email, u.name, u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,)) if token else None
    if not user:
        raise HTTPException(401, "Please sign in")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only admins can change this")
    return user


def _login(response: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", (token, user_id, db.now()))
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/login")
def login(body: LoginIn, response: Response):
    u = db.one("SELECT * FROM users WHERE lower(email)=lower(?)", (body.email.strip(),))
    if not u or not db.check_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Email or password is not correct")
    _login(response, u["id"])
    return {"ok": True}


@app.post("/api/demo-login")
def demo_login(response: Response):
    u = db.one("SELECT id FROM users WHERE email=?", (DEMO_EMAIL,))
    _login(response, u["id"])
    sample = db.one("SELECT id FROM batches WHERE is_sample=1 ORDER BY created_at LIMIT 1")
    return {"ok": True, "sample_batch": sample["id"] if sample else None}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    db.execute("DELETE FROM sessions WHERE token=?", (request.cookies.get(COOKIE, ""),))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/app-info")
def app_info():
    s = db.get_settings()
    return {"app_name": APP_NAME, "company_name": s["company_name"], "accent_color": s["accent_color"],
            "logo_url": s["logo_url"], "language": s["language"], "ai_enabled": ai_enabled(),
            "doc_types": DOC_TYPE_LABELS, "max_files": MAX_FILES_PER_BATCH, "max_mb": MAX_FILE_MB,
            "contact_email": CONTACT_EMAIL, "contact_whatsapp": CONTACT_WHATSAPP}


# --------------------------------------------------------------------------- batches
def _new_id(prefix):
    return prefix + secrets.token_hex(5)


def _batch_name(n):
    return f"Upload {datetime.now().strftime('%d %b, %H:%M')} ({n} file{'s' if n != 1 else ''})"


def _create_batch(files: list[tuple[str, bytes | Path]], doc_type, preset_id, output_format, name, user_id, is_sample=0):
    batch_id = _new_id("b_")
    db.execute("INSERT INTO batches(id, name, doc_type, preset_id, output_format, status, total_files, is_sample, user_id, created_at) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)", (batch_id, name or _batch_name(len(files)), doc_type, preset_id, output_format,
                                               "queued", len(files), is_sample, user_id, db.now()))
    for pos, (fname, content) in enumerate(files):
        doc_id = _new_id("d_")
        safe = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(fname).name)[:120] or "file"
        dest = UPLOAD_DIR / f"{doc_id}{Path(safe).suffix.lower()}"
        if isinstance(content, Path):
            shutil.copy(content, dest)
        else:
            dest.write_bytes(content)
        db.execute("INSERT INTO documents(id, batch_id, position, filename, stored_path, status, created_at) VALUES(?,?,?,?,?,?,?)",
                   (doc_id, batch_id, pos, safe, str(dest), "queued", db.now()))
    pipeline.start_batch(batch_id)
    return batch_id


def create_sample_batch(name=None, user_id=None, is_sample=1):
    files = [(p.name, p) for p in sorted(SAMPLE_DIR.iterdir()) if p.suffix.lower() in ALLOWED]
    preset = db.one("SELECT id FROM presets WHERE name='Supplier invoices'")
    return _create_batch(files, "invoice", preset["id"] if preset else None, "xlsx", name or "Sample invoices", user_id, is_sample)


@app.post("/api/batches")
async def upload_batch(files: list[UploadFile] = File(...), doc_type: str = Form("invoice"), preset_id: int | None = Form(None),
                       output_format: str = Form("xlsx"), name: str = Form(""), user=Depends(current_user)):
    if doc_type not in DOC_TYPE_LABELS:
        raise HTTPException(400, "Unknown document type")
    collected, skipped = [], []
    for f in files:
        data = await f.read()
        ext = Path(f.filename or "").suffix.lower()
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            skipped.append(f"{f.filename} is larger than {MAX_FILE_MB} MB")
            continue
        if ext == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for info in z.infolist():
                        inner = Path(info.filename)
                        if info.is_dir() or inner.name.startswith((".", "__")) or inner.suffix.lower() not in ALLOWED:
                            continue
                        if info.file_size > MAX_FILE_MB * 1024 * 1024:
                            skipped.append(f"{inner.name} is larger than {MAX_FILE_MB} MB")
                            continue
                        collected.append((inner.name, z.read(info)))
            except zipfile.BadZipFile:
                skipped.append(f"{f.filename} is not a valid zip file")
        elif ext in ALLOWED:
            collected.append((f.filename, data))
        else:
            skipped.append(f"{f.filename}: only PDF, JPG, PNG or ZIP files are accepted")
    if not collected:
        raise HTTPException(400, skipped[0] if skipped else "No supported files found")
    if len(collected) > MAX_FILES_PER_BATCH:
        raise HTTPException(400, f"Please upload up to {MAX_FILES_PER_BATCH} files at once")
    batch_id = _create_batch(collected, doc_type, preset_id, output_format, name.strip(), user["id"])
    return {"id": batch_id, "skipped": skipped}


@app.post("/api/batches/sample")
def sample_batch(user=Depends(current_user)):
    return {"id": create_sample_batch(name=f"Sample invoices ({datetime.now().strftime('%d %b, %H:%M')})", user_id=user["id"], is_sample=2)}


def _doc_summary(d):
    f = json.loads(d["fields_json"] or "{}")
    warnings = json.loads(d["warnings_json"] or "[]")
    checks = json.loads(d["checks_json"] or "{}")
    attention = sum(1 for k, c in checks.items() if isinstance(c, dict) and c.get("status") in ("warn", "error"))
    return {"id": d["id"], "filename": d["filename"], "status": d["status"], "stage": d["stage"], "kind": d["kind"],
            "engine": d["engine"], "error": d["error"], "vendor": f.get("vendor"), "invoice_no": f.get("invoice_no"),
            "date": f.get("date"), "total": f.get("total"), "currency": f.get("currency"), "warnings": warnings,
            "attention": attention, "has_preview": bool(d["pages_json"] and d["pages_json"] != "[]")}


def _batch_stats(batch, docs):
    done = [d for d in docs if d["status"] not in ("queued", "processing")]
    fields = 0
    for d in done:
        fields += sum(1 for v in json.loads(d["fields_json"] or "{}").values() if v not in (None, ""))
        fields += 4 * len(json.loads(d["items_json"] or "[]"))
    attention = [d for d in docs if d["status"] in ("needs_review", "failed", "flagged")]
    warn_counts = {"duplicate": 0, "mismatch": 0, "quality": 0}
    for d in docs:
        types = {w["type"] for w in json.loads(d["warnings_json"] or "[]")}
        for t in warn_counts:
            warn_counts[t] += t in types
    ms = batch["processing_ms"] or sum(d["processing_ms"] or 0 for d in docs)
    manual_min = len(done) * MANUAL_MINUTES_PER_DOC
    return {"files": len(docs), "processed": len(done), "fields": fields, "attention": len(attention),
            "approved": sum(d["status"] == "approved" for d in docs), "warnings": warn_counts,
            "processing_seconds": round(ms / 1000, 1), "manual_minutes_estimate": manual_min,
            "time_saved_minutes": max(0, round(manual_min - ms / 60000)), "manual_minutes_per_doc": MANUAL_MINUTES_PER_DOC}


@app.get("/api/batches")
def list_batches(q: str = "", status: str = "", date_from: str = "", date_to: str = "", user=Depends(current_user)):
    batches = db.query("SELECT * FROM batches ORDER BY created_at DESC")
    out = []
    for b in batches:
        if date_from and b["created_at"][:10] < date_from:
            continue
        if date_to and b["created_at"][:10] > date_to:
            continue
        docs = db.query("SELECT id, filename, status, fields_json, warnings_json, items_json, processing_ms FROM documents WHERE batch_id=?", (b["id"],))
        vendors = sorted({json.loads(d["fields_json"] or "{}").get("vendor") or "" for d in docs} - {""})
        if q:
            ql = q.lower()
            hay = " ".join([b["name"]] + vendors + [d["filename"] for d in docs] +
                           [str(json.loads(d["fields_json"] or "{}").get("invoice_no", "")) for d in docs]).lower()
            if ql not in hay:
                continue
        attention = sum(d["status"] in ("needs_review", "failed", "flagged") for d in docs)
        bstatus = "processing" if b["status"] != "done" else ("needs_review" if attention else "done")
        if status and status != bstatus:
            continue
        out.append({**{k: b[k] for k in ("id", "name", "doc_type", "created_at", "finished_at", "is_sample")},
                    "status": bstatus, "files": len(docs), "attention": attention, "vendors": vendors[:4], "vendor_count": len(vendors)})
    return out


def _get_batch(batch_id):
    b = db.one("SELECT * FROM batches WHERE id=?", (batch_id,))
    if not b:
        raise HTTPException(404, "This batch no longer exists")
    return b


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: str, user=Depends(current_user)):
    b = _get_batch(batch_id)
    docs = db.query("SELECT * FROM documents WHERE batch_id=? ORDER BY position", (batch_id,))
    preset = get_preset(b["preset_id"])
    return {"batch": {**b, "doc_type_label": DOC_TYPE_LABELS.get(b["doc_type"]), "preset_name": preset["name"] if preset else None},
            "documents": [_doc_summary(d) for d in docs], "stats": _batch_stats(b, docs)}


class RenameIn(BaseModel):
    name: str


@app.patch("/api/batches/{batch_id}")
def rename_batch(batch_id: str, body: RenameIn, user=Depends(current_user)):
    _get_batch(batch_id)
    db.execute("UPDATE batches SET name=? WHERE id=?", (body.name.strip()[:120] or "Untitled batch", batch_id))
    return {"ok": True}


@app.delete("/api/batches/{batch_id}")
def delete_batch(batch_id: str, user=Depends(current_user)):
    b = _get_batch(batch_id)
    if b["is_sample"] == 1:
        raise HTTPException(400, "The sample batch is kept for demos")
    pipeline.delete_batch_files(batch_id)
    db.execute("DELETE FROM documents WHERE batch_id=?", (batch_id,))
    db.execute("DELETE FROM batches WHERE id=?", (batch_id,))
    return {"ok": True}


@app.get("/api/batches/{batch_id}/export")
def export_batch(batch_id: str, format: str = "xlsx", sheet: str = "invoices", user=Depends(current_user)):
    b = _get_batch(batch_id)
    docs = db.query("SELECT * FROM documents WHERE batch_id=? ORDER BY position", (batch_id,))
    preset = get_preset(b["preset_id"])
    config = preset["config"] if preset else default_config(b["doc_type"])
    config.setdefault("date_format", db.get_settings().get("date_format", "DD/MM/YYYY"))
    base = re.sub(r"[^A-Za-z0-9]+", "_", b["name"]).strip("_")[:60] or "batch"
    if format == "csv":
        data = exporter.build_csv(b, docs, config, sheet)
        fname, mime = f"{APP_NAME}_{base}{'_line_items' if sheet == 'line_items' else ''}.csv", "text/csv; charset=utf-8"
    else:
        data = exporter.build_xlsx(b, docs, config)
        fname, mime = f"{APP_NAME}_{base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if db.get_settings().get("retention") == "immediate" and b["is_sample"] != 1:
        pipeline.delete_batch_files(batch_id)
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --------------------------------------------------------------------------- documents
def _get_doc(doc_id):
    d = db.one("SELECT d.*, b.doc_type, b.name AS batch_name, b.preset_id FROM documents d JOIN batches b ON b.id=d.batch_id WHERE d.id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "This document no longer exists")
    return d


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user=Depends(current_user)):
    d = _get_doc(doc_id)
    siblings = db.query("SELECT id, status FROM documents WHERE batch_id=? ORDER BY position", (d["batch_id"],))
    preset = get_preset(d["preset_id"])
    config = preset["config"] if preset else default_config(d["doc_type"])
    kinds = {k: kind for k, _, kind in FIELDS.get(d["doc_type"], [])}
    field_defs = [{"key": f["key"], "label": f["label"], "kind": kinds.get(f["key"], "text")} for f in config["fields"] if f.get("enabled", True)]
    fields = json.loads(d["fields_json"] or "{}")
    if d["doc_type"] == "form":
        field_defs = [{"key": k, "label": k, "kind": "text"} for k in fields]
    pages = json.loads(d["pages_json"] or "[]")
    files_kept = bool(d["stored_path"])
    for p in pages:
        p["url"] = f"/api/documents/{doc_id}/pages/{p['n']}" if files_kept else None
    return {"id": d["id"], "batch_id": d["batch_id"], "batch_name": d["batch_name"], "doc_type": d["doc_type"],
            "filename": d["filename"], "status": d["status"], "kind": d["kind"], "engine": d["engine"], "error": d["error"],
            "pages": pages, "fields": fields, "field_defs": field_defs, "items": json.loads(d["items_json"] or "[]"),
            "checks": json.loads(d["checks_json"] or "{}"), "warnings": json.loads(d["warnings_json"] or "[]"),
            "include_line_items": config.get("include_line_items", True) and d["doc_type"] != "form",
            "position": next(i for i, s in enumerate(siblings) if s["id"] == doc_id), "siblings": siblings,
            "files_deleted": not files_kept, "reviewed_by": d["reviewed_by"]}


class DocUpdate(BaseModel):
    fields: dict | None = None
    items: list | None = None
    edited_keys: list[str] = []
    action: str | None = None  # approve | skip | flag | reopen


@app.patch("/api/documents/{doc_id}")
def update_document(doc_id: str, body: DocUpdate, user=Depends(current_user)):
    d = _get_doc(doc_id)
    if body.fields is not None or body.items is not None:
        fields = json.loads(d["fields_json"] or "{}")
        if body.fields is not None:
            from .extract_rules import parse_date, to_number
            for k, v in body.fields.items():
                if k in ("subtotal", "discount", "tax", "total"):
                    fields[k] = to_number(v) if v not in (None, "") else None
                elif k == "date" and v:
                    fields[k] = parse_date(str(v)) or str(v)
                else:
                    fields[k] = (str(v).strip() if v is not None else None) or None
            fields = {k: v for k, v in fields.items() if v is not None}
        checks = json.loads(d["checks_json"] or "{}")
        edited = set(checks.get("_edited", {}).get("keys", [])) | set(body.edited_keys)
        checks["_edited"] = {"keys": sorted(edited)}
        items = body.items if body.items is not None else json.loads(d["items_json"] or "[]")
        from .extract_rules import to_number
        for it in items:
            for k in ("quantity", "unit_price", "amount"):
                it[k] = to_number(it.get(k)) if it.get(k) not in (None, "") else None
        db.execute("UPDATE documents SET fields_json=?, items_json=?, checks_json=? WHERE id=?",
                   (json.dumps(fields), json.dumps(items), json.dumps(checks), doc_id))
        fields, items, checks, warnings = pipeline.recheck_document(doc_id)
        status = pipeline.doc_status(checks, [it["check"] for it in items], warnings) if d["status"] in ("done", "needs_review") else d["status"]
        db.execute("UPDATE documents SET fields_json=?, items_json=?, checks_json=?, warnings_json=?, status=? WHERE id=?",
                   (json.dumps(fields), json.dumps(items), json.dumps(checks), json.dumps(warnings), status, doc_id))
    if body.action:
        new = {"approve": "approved", "skip": "skipped", "flag": "flagged"}.get(body.action)
        if body.action == "reopen":
            fields, items, checks, warnings = pipeline.recheck_document(doc_id)
            new = pipeline.doc_status(checks, [it["check"] for it in items], warnings)
        if not new:
            raise HTTPException(400, "Unknown action")
        db.execute("UPDATE documents SET status=?, reviewed_at=?, reviewed_by=? WHERE id=?", (new, db.now(), user["name"], doc_id))
    return get_document(doc_id, user)


@app.get("/api/documents/{doc_id}/pages/{n}")
def page_image(doc_id: str, n: int, user=Depends(current_user)):
    path = PAGES_DIR / f"{doc_id}_{n}.jpg"
    if not path.exists():
        raise HTTPException(404, "Preview deleted by the privacy setting")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/documents/{doc_id}/original")
def original(doc_id: str, user=Depends(current_user)):
    d = _get_doc(doc_id)
    if not d["stored_path"] or not Path(d["stored_path"]).exists():
        raise HTTPException(404, "The original file was deleted by the privacy setting")
    return FileResponse(d["stored_path"], filename=d["filename"])


# --------------------------------------------------------------------------- presets / templates
class PresetIn(BaseModel):
    name: str
    doc_type: str
    config: dict


@app.get("/api/presets")
def presets(user=Depends(current_user)):
    return {"presets": list_presets(), "fields": {k: [{"key": a, "label": b, "kind": c} for a, b, c in v] for k, v in FIELDS.items()},
            "doc_types": DOC_TYPE_LABELS, "date_formats": list(exporter.DATE_FORMATS)}


@app.post("/api/presets")
def create_preset(body: PresetIn, user=Depends(current_user)):
    pid = db.execute("INSERT INTO presets(name, doc_type, config_json, created_at) VALUES(?,?,?,?)",
                     (body.name.strip() or "New preset", body.doc_type, json.dumps(body.config), db.now()))
    return get_preset(pid)


@app.put("/api/presets/{pid}")
def update_preset(pid: int, body: PresetIn, user=Depends(current_user)):
    db.execute("UPDATE presets SET name=?, doc_type=?, config_json=? WHERE id=?", (body.name.strip() or "Preset", body.doc_type, json.dumps(body.config), pid))
    return get_preset(pid)


@app.delete("/api/presets/{pid}")
def delete_preset(pid: int, user=Depends(current_user)):
    if len(list_presets()) <= 1:
        raise HTTPException(400, "Keep at least one preset")
    db.execute("DELETE FROM presets WHERE id=?", (pid,))
    return {"ok": True}


# --------------------------------------------------------------------------- settings / team / branding
@app.get("/api/settings")
def get_settings(user=Depends(current_user)):
    return db.get_settings()


@app.put("/api/settings")
def put_settings(body: dict, user=Depends(admin_user)):
    if "accent_color" in body and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(body["accent_color"])):
        raise HTTPException(400, "Colour must look like #1d4ed8")
    if "retention" in body and body["retention"] not in ("immediate", "7d", "30d"):
        raise HTTPException(400, "Unknown retention option")
    db.set_settings(body)
    pipeline.apply_retention()
    return db.get_settings()


@app.post("/api/settings/logo")
async def upload_logo(file: UploadFile = File(...), user=Depends(admin_user)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        raise HTTPException(400, "Please upload a PNG, JPG, SVG or WEBP logo")
    name = f"logo_{secrets.token_hex(4)}{ext}"
    (BRAND_DIR / name).write_bytes(await file.read())
    db.set_settings({"logo_url": f"/brand/{name}"})
    return db.get_settings()


class MemberIn(BaseModel):
    name: str
    email: str
    role: str = "reviewer"


@app.get("/api/team")
def team(user=Depends(current_user)):
    return db.query("SELECT id, name, email, role, created_at FROM users ORDER BY id")


@app.post("/api/team")
def add_member(body: MemberIn, user=Depends(admin_user)):
    if body.role not in ("admin", "reviewer"):
        raise HTTPException(400, "Role must be admin or reviewer")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", body.email.strip()):
        raise HTTPException(400, "Please enter a valid email")
    if db.one("SELECT id FROM users WHERE lower(email)=lower(?)", (body.email.strip(),)):
        raise HTTPException(400, "This person is already on the team")
    temp = secrets.token_urlsafe(6)
    db.execute("INSERT INTO users(email, name, role, password_hash, created_at) VALUES(?,?,?,?,?)",
               (body.email.strip(), body.name.strip() or body.email, body.role, db.hash_password(temp), db.now()))
    return {"ok": True, "temporary_password": temp}


@app.patch("/api/team/{uid}")
def change_role(uid: int, body: dict, user=Depends(admin_user)):
    if body.get("role") not in ("admin", "reviewer"):
        raise HTTPException(400, "Role must be admin or reviewer")
    if uid == user["id"]:
        raise HTTPException(400, "You can't change your own role")
    db.execute("UPDATE users SET role=? WHERE id=?", (body["role"], uid))
    return {"ok": True}


@app.delete("/api/team/{uid}")
def remove_member(uid: int, user=Depends(admin_user)):
    if uid == user["id"]:
        raise HTTPException(400, "You can't remove yourself")
    db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


# --------------------------------------------------------------------------- pages
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/brand", StaticFiles(directory=BRAND_DIR), name="brand")


@app.get("/sample-files/{name}")
def sample_file(name: str):
    path = SAMPLE_DIR / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/landing")
def landing():
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/privacy")
def privacy():
    return FileResponse(STATIC_DIR / "privacy.html")


@app.get("/health")
def health():
    return {"ok": True, "ai_enabled": ai_enabled()}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        detail = getattr(exc, "detail", "Not found")
        return JSONResponse({"detail": detail}, status_code=404)
    return RedirectResponse("/")
