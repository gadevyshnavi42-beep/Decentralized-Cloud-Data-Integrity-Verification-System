"""Decentralized Cloud Data Integrity Verification System (Flask + SQLite).

The "decentralized" part is a SIMULATION: three local folders act as verification
nodes, each holding its own replica of every uploaded file. No real blockchain
or distributed cloud infrastructure is used.
"""
import hashlib
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "database.db")
UPLOADS = os.path.join(BASE, "uploads")
NODES = {"Node A": "node_a", "Node B": "node_b", "Node C": "node_c"}  # simulated
ALLOWED = {"txt", "pdf", "png", "jpg", "jpeg", "gif", "doc", "docx", "xls",
           "xlsx", "ppt", "pptx", "csv", "zip", "json", "md"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB upload limit
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    original_hash TEXT NOT NULL,
    calculated_hash TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    verified_at TEXT NOT NULL
);
"""


# ---------- helpers ----------
def init_db():
    os.makedirs(UPLOADS, exist_ok=True)
    for folder in NODES.values():
        os.makedirs(os.path.join(UPLOADS, folder), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def sha256_path(path):
    """SHA-256 of a file on disk, or None if it does not exist."""
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_stream(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(65536), b""):
        h.update(chunk)
    return h.hexdigest()


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return jsonify(error="Please log in first."), 401
        return fn(*a, **kw)
    return wrapper


def page_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


def get_file(fid):
    return db().execute("SELECT * FROM files WHERE id=? AND user_id=?",
                        (fid, session["user_id"])).fetchone()


def log_verification(fid, original, calculated, status):
    ts = now()
    db().execute(
        "INSERT INTO verification_history (user_id,file_id,original_hash,"
        "calculated_hash,verification_status,verified_at) VALUES (?,?,?,?,?,?)",
        (session["user_id"], fid, original, calculated, status, ts))
    db().commit()
    return ts


# ---------- pages ----------
@app.route("/")
def index():
    return render_template("index.html", page="index")


@app.route("/login")
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html", page="login")


@app.route("/register")
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("register.html", page="register")


for _name in ("dashboard", "upload", "files", "verify", "history"):
    app.add_url_rule(
        f"/{_name}", _name,
        page_required(lambda n=_name: render_template(f"{n}.html", page=n, sidebar=True)))


# ---------- auth API ----------
@app.post("/api/register")
def api_register():
    d = request.get_json(silent=True) or {}
    username = str(d.get("username", "")).strip()
    email = str(d.get("email", "")).strip().lower()
    password = str(d.get("password", ""))
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return jsonify(error="Username must be 3-30 letters, numbers or underscores."), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(error="Enter a valid email address."), 400
    if len(password) < 8:
        return jsonify(error="Password must be at least 8 characters."), 400
    if password != d.get("confirm_password"):
        return jsonify(error="Passwords do not match."), 400
    try:
        db().execute("INSERT INTO users (username,email,password_hash,created_at) VALUES (?,?,?,?)",
                     (username, email, generate_password_hash(password), now()))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Username or email already registered."), 409
    return jsonify(message="Registration successful. Please log in."), 201


@app.post("/api/login")
def api_login():
    d = request.get_json(silent=True) or {}
    user = db().execute("SELECT * FROM users WHERE email=?",
                        (str(d.get("email", "")).strip().lower(),)).fetchone()
    if not user or not check_password_hash(user["password_hash"], str(d.get("password", ""))):
        return jsonify(error="Invalid email or password."), 401
    session.clear()
    session["user_id"], session["username"] = user["id"], user["username"]
    return jsonify(message="Login successful.", username=user["username"])


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(message="Logged out.")


# ---------- dashboard / history ----------
@app.get("/api/dashboard")
@login_required
def api_dashboard():
    uid = session["user_id"]
    one = lambda q: db().execute(q, (uid,)).fetchone()[0]
    recent = db().execute(
        "SELECT h.*, COALESCE(f.filename,'(deleted file)') AS filename FROM verification_history h "
        "LEFT JOIN files f ON f.id=h.file_id WHERE h.user_id=? ORDER BY h.id DESC LIMIT 5", (uid,)).fetchall()
    return jsonify(
        username=session["username"],
        total_files=one("SELECT COUNT(*) FROM files WHERE user_id=?"),
        total_verifications=one("SELECT COUNT(*) FROM verification_history WHERE user_id=?"),
        verified=one("SELECT COUNT(*) FROM verification_history WHERE user_id=? AND verification_status='Verified'"),
        failed=one("SELECT COUNT(*) FROM verification_history WHERE user_id=? AND verification_status='Failed'"),
        recent=[dict(r) for r in recent])


@app.get("/api/history")
@login_required
def api_history():
    rows = db().execute(
        "SELECT h.*, COALESCE(f.filename,'(deleted file)') AS filename FROM verification_history h "
        "LEFT JOIN files f ON f.id=h.file_id WHERE h.user_id=? ORDER BY h.id DESC",
        (session["user_id"],)).fetchall()
    return jsonify(history=[dict(r) for r in rows])


# ---------- files API ----------
@app.post("/api/upload")
@login_required
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="No file selected."), 400
    original = secure_filename(f.filename) or "file"
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED:
        return jsonify(error="File type not allowed. Allowed: " + ", ".join(sorted(ALLOWED))), 400
    stored = uuid.uuid4().hex + "." + ext
    path = os.path.join(UPLOADS, stored)
    f.save(path)
    digest = sha256_path(path)
    for folder in NODES.values():  # simulated nodes each keep a replica
        shutil.copyfile(path, os.path.join(UPLOADS, folder, stored))
    cur = db().execute(
        "INSERT INTO files (user_id,filename,stored_filename,file_size,sha256_hash,uploaded_at) "
        "VALUES (?,?,?,?,?,?)",
        (session["user_id"], original, stored, os.path.getsize(path), digest, now()))
    db().commit()
    return jsonify(message="File uploaded successfully.", id=cur.lastrowid,
                   filename=original, sha256_hash=digest), 201


@app.get("/api/files")
@login_required
def api_files():
    rows = db().execute(
        "SELECT id,filename,file_size,sha256_hash,uploaded_at FROM files WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)).fetchall()
    return jsonify(files=[dict(r) for r in rows])


@app.get("/api/files/<int:fid>/download")
@login_required
def api_download(fid):
    row = get_file(fid)
    if not row or not os.path.isfile(os.path.join(UPLOADS, row["stored_filename"])):
        return jsonify(error="File not found."), 404
    return send_from_directory(UPLOADS, row["stored_filename"], as_attachment=True,
                               download_name=row["filename"])


@app.delete("/api/files/<int:fid>")
@login_required
def api_delete(fid):
    row = get_file(fid)
    if not row:
        return jsonify(error="File not found."), 404
    for folder in ("", *NODES.values()):
        p = os.path.join(UPLOADS, folder, row["stored_filename"])
        if os.path.isfile(p):
            os.remove(p)
    db().execute("DELETE FROM files WHERE id=?", (fid,))
    db().commit()
    return jsonify(message="File deleted.")


# ---------- verification API ----------
@app.post("/api/verify/<int:fid>")
@login_required
def api_verify(fid):
    """Compare the stored hash with a hash calculated now.

    If a comparison file is uploaded (form field 'file') its hash is used;
    otherwise the stored server copy is re-hashed.
    """
    row = get_file(fid)
    if not row:
        return jsonify(error="File not found."), 404
    upload = request.files.get("file")
    if upload and upload.filename:
        calculated = sha256_stream(upload.stream)
        source = "uploaded comparison file"
    else:
        calculated = sha256_path(os.path.join(UPLOADS, row["stored_filename"])) or "FILE MISSING"
        source = "stored server copy"
    status = "Verified" if calculated == row["sha256_hash"] else "Failed"
    ts = log_verification(fid, row["sha256_hash"], calculated, status)
    return jsonify(status=status, filename=row["filename"], original_hash=row["sha256_hash"],
                   calculated_hash=calculated, verified_at=ts, source=source)


@app.post("/api/decentralized-verify/<int:fid>")
@login_required
def api_decentralized(fid):
    """SIMULATED 3-node verification: each node hashes its own replica."""
    row = get_file(fid)
    if not row:
        return jsonify(error="File not found."), 404
    nodes, agree = [], 0
    for name, folder in NODES.items():
        h = sha256_path(os.path.join(UPLOADS, folder, row["stored_filename"]))
        ok = h == row["sha256_hash"]
        agree += ok
        nodes.append({"node": name, "hash": h or "REPLICA MISSING", "agrees": ok})
    total = len(nodes)
    status = "Verified" if agree == total else "Failed"
    if agree == total:
        message = "Consensus reached: all nodes confirm the file is intact."
    elif agree * 2 > total:
        message = (f"Majority consensus ({agree}/{total}) matches the stored hash, but a node "
                   "disagrees. WARNING: the file may have been modified or corrupted.")
    else:
        message = "WARNING: no consensus. The file may have been modified or corrupted."
    bad = next((n["hash"] for n in nodes if not n["agrees"]), row["sha256_hash"])
    ts = log_verification(fid, row["sha256_hash"], bad, status)
    return jsonify(simulated=True, status=status, filename=row["filename"], nodes=nodes,
                   agreeing=agree, total=total, consensus=agree == total, message=message,
                   original_hash=row["sha256_hash"], verified_at=ts)


# ---------- errors ----------
@app.errorhandler(413)
def too_large(_e):
    return jsonify(error="File too large (max 16 MB)."), 413


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found."), 404
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
