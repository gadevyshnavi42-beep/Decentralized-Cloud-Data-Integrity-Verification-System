# Decentralized Cloud Data Integrity Verification System

A simple full-stack web app that lets users upload files, stores their **SHA-256** hashes, and later
verifies whether a file has been modified or corrupted.

> **Note:** the "decentralized" feature is a **simulation**. Three local folders act as verification
> nodes. The project does **not** use a real blockchain or physically distributed cloud infrastructure.

## Features
- User registration / login (hashed passwords, session-based auth)
- File upload (drag & drop, progress bar, 16 MB limit, allowed-extension check, safe filenames)
- SHA-256 hash generated on upload and saved in SQLite
- Integrity verification: stored hash vs. a newly calculated hash (of the stored copy or of a file you upload)
- Simulated 3-node verification with per-node results, agreement count and consensus / warning
- File management (list, download, delete, verify), verification history, dashboard statistics

## Technologies
Frontend: HTML5, CSS3, JavaScript, Bootstrap 5 (CDN) · Backend: Python, Flask, REST API · Database: SQLite

## Setup (VS Code terminal)
Requires Python 3.9+ and an internet connection for the Bootstrap CDN files.

```bash
cd decentralized-cloud-integrity

# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python app.py
```
Open **http://127.0.0.1:5000**. `database.db` is created automatically on first run.
Optional: set `SECRET_KEY` to your own random value before running for real use.

## Usage
1. Register, then log in.
2. **Upload** a file — the SHA-256 hash is displayed.
3. **Verify** — pick the stored file, optionally choose a file to compare, click *Verify Integrity*.
4. Click *Run Simulated 3-Node Verification* to see each node's result.
5. Check **My Files** and **History** for downloads, deletion and past results.

### Try a tampering demo
Upload a text file, then open `uploads/node_b/` and change the file there (or edit your local copy and upload it
as the comparison file). Run the verification again: you will see **Integrity Failed** / **2 of 3 nodes agree**
with a warning.

## API endpoints
`POST /api/register` · `POST /api/login` · `POST /api/logout` · `GET /api/dashboard` · `POST /api/upload` ·
`GET /api/files` · `GET /api/files/<id>/download` · `DELETE /api/files/<id>` · `POST /api/verify/<id>` ·
`GET /api/history` · `POST /api/decentralized-verify/<id>`

## Structure
```
decentralized-cloud-integrity/
├── app.py  requirements.txt  README.md  database.db (auto-created)
├── templates/   base, index, login, register, dashboard, upload, files, verify, history
├── static/      css/style.css  js/script.js  images/
└── uploads/     stored files (+ node_a, node_b, node_c replicas)
```
