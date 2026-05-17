import json
import os
import re
from html import escape
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PROJECT_DATA_DIR", str(BASE_DIR / "data"))).resolve()
PROJECTS_FILE = Path(os.environ.get("PROJECTS_FILE", str(DATA_DIR / "projects.json"))).resolve()
UPLOAD_DIR = Path(os.environ.get("PROJECT_UPLOAD_DIR", str(BASE_DIR / "assets" / "project-previews" / "uploads"))).resolve()
MAX_IMAGE_BYTES = 8 * 1024 * 1024
CURRENT_SEED_VERSION = 2

ADMIN_PASSWORD = os.environ.get("PROJECT_ADMIN_PASSWORD", "wilski2026")

SUBJECTS = {
    "biologie": {"label": "Biologie", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "chemie": {"label": "Chemie", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "physik": {"label": "Physik", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "mathematik": {"label": "Mathematik", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "informatik": {"label": "Informatik", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "deutsch": {"label": "Deutsch", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "englisch": {"label": "Englisch", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "wirtschaft": {"label": "Wirtschaft", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "erdkunde": {"label": "Erdkunde", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "gesellschaft": {"label": "Gesellschaftslehre", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "geschichte": {"label": "Geschichte", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
    "allgemein": {"label": "Allgemein", "stages": {"sek1": ["5", "6", "7", "8", "9", "10"], "sek2": ["EF", "Q1", "Q2"]}},
}

SUBJECT_CATS = {
    "biologie": "bio",
    "chemie": "chemie",
    "physik": "allg",
    "mathematik": "mathe",
    "informatik": "informatik",
    "deutsch": "deutsch",
    "englisch": "englisch",
    "wirtschaft": "allg",
    "erdkunde": "geo",
    "gesellschaft": "gesellschaft",
    "geschichte": "geschichte",
    "allgemein": "allg",
}

ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PUBLIC_ROOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".css", ".js"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES + 1024 * 1024


def load_seed_projects() -> dict:
    seed_file = BASE_DIR / "data" / "projects.json"
    if not seed_file.exists():
        return {"items": [], "_seed_version": CURRENT_SEED_VERSION}
    try:
        data = json.loads(seed_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": [], "_seed_version": CURRENT_SEED_VERSION}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    data["_seed_version"] = data.get("_seed_version", CURRENT_SEED_VERSION)
    return data


def write_projects_file(data: dict) -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = PROJECTS_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_file.replace(PROJECTS_FILE)


def ensure_storage() -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_FILE.exists():
        seed_data = load_seed_projects()
        seed_data["_seed_version"] = CURRENT_SEED_VERSION
        write_projects_file(seed_data)
        return

    try:
        stored_data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        stored_data = {"items": []}
    if not isinstance(stored_data.get("items"), list):
        stored_data["items"] = []

    if stored_data.get("_seed_version") == CURRENT_SEED_VERSION:
        return

    seed_data = load_seed_projects()
    existing_ids = {
        item.get("project", {}).get("id")
        for item in stored_data["items"]
        if isinstance(item, dict)
    }
    for item in seed_data.get("items", []):
        project_id = item.get("project", {}).get("id")
        if project_id and project_id not in existing_ids:
            stored_data["items"].append(item)
    stored_data["_seed_version"] = CURRENT_SEED_VERSION
    write_projects_file(stored_data)


def read_projects() -> dict:
    ensure_storage()
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"items": []}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def write_projects(data: dict) -> None:
    ensure_storage()
    write_projects_file(data)


def require_password() -> tuple[bool, str]:
    if request.is_json:
        supplied = (request.get_json(silent=True) or {}).get("password")
    else:
        supplied = request.form.get("password")
    if supplied != ADMIN_PASSWORD:
        return False, "Passwort stimmt nicht."
    return True, ""


def find_project(data: dict, project_id: str):
    for index, item in enumerate(data.get("items", [])):
        if item.get("project", {}).get("id") == project_id:
            return index, item
    return -1, None


def clean_text(value: str, max_length: int = 3000) -> str:
    return escape((value or "").strip()[:max_length])


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug or "projekt"


def make_project_id(title: str, existing_ids: set[str]) -> str:
    base = slugify(title)
    project_id = base
    counter = 2
    while project_id in existing_ids:
        project_id = f"{base}_{counter}"
        counter += 1
    return project_id


def validate_placement(subject_id: str, stage_id: str, grade_id: str) -> tuple[bool, str]:
    subject = SUBJECTS.get(subject_id)
    if not subject:
        return False, "Unbekanntes Fach."
    grades = subject["stages"].get(stage_id)
    if not grades:
        return False, "Unbekannte Stufe."
    if grade_id not in grades:
        return False, "Dieser Jahrgang passt nicht zur gewählten Stufe."
    return True, ""


def save_preview(project_id: str):
    image = request.files.get("image")
    if not image or not image.filename:
        return ""

    filename = secure_filename(image.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Bitte ein Bild im Format JPG, PNG, WEBP oder GIF hochladen.")

    target = UPLOAD_DIR / f"{project_id}_{uuid4().hex[:8]}{ext}"
    image.save(target)
    return f"uploads/{target.name}"


@app.get("/")
def index():
    return send_file(BASE_DIR / "index.html")


@app.get("/api/projects")
def get_projects():
    return jsonify(read_projects())


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.post("/api/auth")
def check_password():
    data = request.get_json(silent=True) or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Passwort stimmt nicht."}), 403
    return jsonify({"ok": True})


@app.post("/api/projects")
def create_project():
    ok, message = require_password()
    if not ok:
        return jsonify({"error": message}), 403

    title = (request.form.get("title") or "").strip()
    tagline = (request.form.get("tagline") or "").strip()
    desc = (request.form.get("desc") or "").strip()
    url = (request.form.get("url") or "").strip()
    subject_id = (request.form.get("subjectId") or "").strip()
    stage_id = (request.form.get("stageId") or "").strip()
    grade_id = (request.form.get("gradeId") or "").strip()
    raw_features = request.form.get("features") or ""
    features = [clean_text(line, 240) for line in raw_features.splitlines() if line.strip()]

    if not title or not tagline or not desc or not url or not features:
        return jsonify({"error": "Bitte alle Pflichtfelder ausfüllen."}), 400
    if not (url.startswith("https://") or url.startswith("http://")):
        return jsonify({"error": "Bitte einen gültigen http- oder https-Link eintragen."}), 400

    valid, message = validate_placement(subject_id, stage_id, grade_id)
    if not valid:
        return jsonify({"error": message}), 400

    data = read_projects()
    existing_ids = {
        item.get("project", {}).get("id")
        for item in data["items"]
        if isinstance(item, dict)
    }
    project_id = make_project_id(title, existing_ids)

    try:
        preview = save_preview(project_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    subject_label = SUBJECTS[subject_id]["label"]
    grade_label = f"Klasse {grade_id}" if stage_id == "sek1" else grade_id
    item = {
        "project": {
            "id": project_id,
            "cat": SUBJECT_CATS.get(subject_id, "allg"),
            "icon": clean_text(request.form.get("icon") or "📚", 80),
            "online": request.form.get("online", "true").lower() == "true",
            "fach": f"{clean_text(subject_label, 80)} &middot; {clean_text(grade_label, 80)}",
            "title": clean_text(title, 160),
            "tagline": clean_text(tagline, 240),
            "desc": clean_text(desc, 1800),
            "features": features[:8],
            "url": url,
        },
        "placement": {
            "subjectId": subject_id,
            "stageId": stage_id,
            "gradeId": grade_id,
        },
        "preview": preview,
    }

    data["items"].append(item)
    write_projects(data)
    return jsonify({"item": item}), 201


@app.patch("/api/projects/<project_id>")
def update_project(project_id):
    ok, message = require_password()
    if not ok:
        return jsonify({"error": message}), 403

    body = request.get_json(silent=True) or {}
    data = read_projects()
    index, item = find_project(data, project_id)
    if index < 0:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    if "online" in body:
        item["project"]["online"] = bool(body["online"])
    data["items"][index] = item
    write_projects(data)
    return jsonify({"item": item})


@app.delete("/api/projects/<project_id>")
def delete_project(project_id):
    ok, message = require_password()
    if not ok:
        return jsonify({"error": message}), 403

    data = read_projects()
    index, item = find_project(data, project_id)
    if index < 0:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    preview = item.get("preview", "")
    if preview.startswith("uploads/"):
        upload_path = (UPLOAD_DIR / Path(preview).name).resolve()
        try:
            if upload_path.relative_to(UPLOAD_DIR.resolve()) and upload_path.exists():
                upload_path.unlink()
        except (OSError, ValueError):
            pass

    del data["items"][index]
    write_projects(data)
    return jsonify({"ok": True, "id": project_id})


@app.get("/<path:filename>")
def public_files(filename):
    path = (BASE_DIR / filename).resolve()
    try:
        relative_path = path.relative_to(BASE_DIR)
    except ValueError:
        return "Not found", 404
    if "data" in relative_path.parts:
        return "Not found", 404
    if filename.startswith("assets/") or path.suffix.lower() in PUBLIC_ROOT_EXTENSIONS:
        return send_from_directory(BASE_DIR, filename)
    return "Not found", 404


if __name__ == "__main__":
    ensure_storage()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
