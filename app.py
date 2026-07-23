from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory
)
from flask_cors import CORS
import os
import sys
import json
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime

# ----------------------------------------------------
# PATH SETUP
# ----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# ----------------------------------------------------
# FLASK APP CONFIG
# ----------------------------------------------------
app = Flask(
    __name__,
    static_folder="static",   # ✅ CORRECT FOR RENDER
    static_url_path=""
)
CORS(app)

# ----------------------------------------------------
# FILE UPLOAD CONFIG (LOCAL / DEV ONLY)
# ----------------------------------------------------
UPLOAD_FOLDER = os.path.join(BASE_DIR, "movies")
ALLOWED_EXTENSIONS = {"mp4", "avi", "mkv", "mov", "webm"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------
# DATABASE HELPERS (SAFE IMPORTS)
# ----------------------------------------------------
def init_database():
    try:
        from database import init_database as db_init
        db_init()
        print("✅ Database initialized")
    except Exception as e:
        # Do NOT crash app on Render
        print("⚠️ Database init skipped:", e)

def get_movie_download_link(title, language, quality):
    try:
        from database import get_movie_download_link as db_search
        return db_search(title, language, quality)
    except Exception as e:
        print("Database search error:", e)
        return None

def add_movie_to_db(movie_data):
    from database import add_movie
    return add_movie(movie_data)

def get_all_movies_from_db():
    try:
        from database import get_all_movies
        return get_all_movies()
    except Exception as e:
        print("Database get all error:", e)
        return []

def delete_movie_from_db(movie_id):
    from database import delete_movie
    return delete_movie(movie_id)

# ----------------------------------------------------
# FRONTEND ROUTES (FIXED)
# ----------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/dashboard")
def dashboard():
    return send_from_directory(app.static_folder, "dashboard.html")

@app.route("/download")
def download():
    return send_from_directory(app.static_folder, "download.html")

@app.route("/admin")
def admin():
    return send_from_directory(app.static_folder, "admin.html")

# ----------------------------------------------------
# API: SEARCH
# ----------------------------------------------------
@app.route("/api/search")
def search_movie():
    title = request.args.get("title", "").strip()
    lang = request.args.get("lang", "tamil")
    quality = request.args.get("quality", "720p")

    print(f"🔍 Search: {title}, {lang}, {quality}")

    # Sample legal movies (demo)
    sample_movies = {
        "sample": {
            "available": True,
            "movie": {
                "title": "Sample Video",
                "year": 2023,
                "quality": quality.upper(),
                "size": "1.2GB",
                "language": lang
            },
            "download_link": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        }
    }

    for key, movie in sample_movies.items():
        if key in title.lower():
            return jsonify(movie)

    result = get_movie_download_link(title, lang, quality)

    if result:
        return jsonify(result)

    return jsonify({
        "available": False,
        "message": f'Movie "{title}" not found'
    })

# ----------------------------------------------------
# ADMIN APIs
# ----------------------------------------------------
@app.route("/api/admin/movies", methods=["GET"])
def admin_get_movies():
    return jsonify(get_all_movies_from_db())

@app.route("/api/admin/upload", methods=["POST"])
def admin_upload_movie():
    try:
        title = request.form.get("title", "").strip()
        file = request.files.get("file")

        if not title or not file or not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Invalid upload"}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        file.save(filepath)

        movie_data = {
            "title": title,
            "year": 2024,
            "description": request.form.get("description", ""),
            "poster_url": request.form.get("poster", ""),
            "language": request.form.get("language", "tamil"),
            "qualities": [{
                "code": "720p",
                "name": "720p HD",
                "size": "1GB",
                "file_path": unique_filename,
                "download_url": f"/api/movies/{unique_filename}"
            }]
        }

        movie_id = add_movie_to_db(movie_data)

        return jsonify({
            "success": True,
            "movie_id": movie_id,
            "download_url": f"/api/movies/{unique_filename}"
        })

    except Exception as e:
        print("Upload error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/movies/<int:movie_id>", methods=["DELETE"])
def admin_delete_movie(movie_id):
    try:
        file_paths = delete_movie_from_db(movie_id)
        for f in file_paths:
            path = os.path.join(app.config["UPLOAD_FOLDER"], f)
            if os.path.exists(path):
                os.remove(path)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ----------------------------------------------------
# FILE DOWNLOAD
# ----------------------------------------------------
@app.route("/api/movies/<filename>")
def serve_movie(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=True
    )

# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "time": datetime.now().isoformat()
    })

# ----------------------------------------------------
# ERROR HANDLERS
# ----------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ----------------------------------------------------
# STARTUP (SAFE FOR RENDER)
# ----------------------------------------------------
init_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
