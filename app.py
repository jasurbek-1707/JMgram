import os
import uuid
from functools import wraps

from flask import (Flask, render_template, jsonify, request,
                   session, redirect, url_for, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from mutagen.mp3 import MP3          
from models import init_db, seed_demo_data, get_db

# ── Sozlamalar ────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
COVER_FOLDER  = os.path.join(UPLOAD_FOLDER, "covers")
AUDIO_FOLDER  = os.path.join(UPLOAD_FOLDER, "audio")
ALLOWED_IMG   = {"png", "jpg", "jpeg", "webp"}
ALLOWED_AUD   = {"mp3"}

# Kerakli statik papkalarni avtomatik yaratish
os.makedirs(COVER_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "jmgramm-secret-key-fayozbek-matematik"

# Dasturni ilk bor yurgizganda bazani tayyorlash
with app.app_context():
    init_db()
    seed_demo_data()


# ── Yordamchi funksiyalar ─────────────────────────────────────────────────────
def allowed(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def save_file(file, folder, sub_url):
    """Faylni xavfsiz UUID nomi bilan saqlaydi va andoza tushunadigan URL yo'lini qaytaradi."""
    ext  = file.filename.rsplit(".", 1)[1].lower()
    name = uuid.uuid4().hex + "." + ext
    path = os.path.join(folder, name)
    file.save(path)
    return f"/static/uploads/{sub_url}/{name}"


# ═══════════════════════════════════════════════════════════════════════════════
# 1-QISM & AQLLI ALGORITM: LENTA (Instagram Recommendation Engine)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    db = get_db()
    user_id = session.get("user_id")
    
    # 🧠 INSTAGRAM TAVSIYA TIZIMI:
    # Foydalanuvchining eng yuqori balli bo'lgan TOP 3 ta janrini aniqlaymiz
    favorite_genres = []
    if user_id:
        rows = db.execute("""
            SELECT genre FROM user_interests 
            WHERE user_id = ? AND score > 0 
            ORDER BY score DESC LIMIT 3
        """, (user_id,)).fetchall()
        favorite_genres = [r["genre"] for r in rows]

    # Musiqalarni saralash (Agar foydalanuvchining sevimli janrlari bo'lsa, o'shalar birinchi chiqadi)
    if favorite_genres:
        placeholders = ",".join(["?"] * len(favorite_genres))
        query = f"""
            SELECT s.*, 
                   (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count,
                   (SELECT 1 FROM likes WHERE song_id = s.id AND user_id = ?) AS is_liked,
                   CASE WHEN s.genre IN ({placeholders}) THEN 1 ELSE 0 END AS is_recommended
            FROM songs s 
            ORDER BY is_recommended DESC, s.created_at DESC LIMIT 30
        """
        # SQL xavfsizligi uchun parametrlarni birlashtiramiz
        params = [user_id] + favorite_genres
        songs = db.execute(query, params).fetchall()
    else:
        # Foydalanuvchi kirmagan bo'lsa yoki hali qiziqishi aniqlanmagan bo'lsa oddiy yangi musiqalar
        songs = db.execute("""
            SELECT s.*, 
                   (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count,
                   (SELECT 1 FROM likes WHERE song_id = s.id AND user_id = ?) AS is_liked
            FROM songs s ORDER BY s.created_at DESC LIMIT 30
        """, (user_id or 0,)).fetchall()

    db.close()
    return render_template("index.html",
                           songs=[dict(r) for r in songs],
                           current_user=session.get("username"))


@app.route("/api/feed")
def api_feed():
    page   = max(1, request.args.get("page",  1,  type=int))
    limit  = min(50, request.args.get("limit", 10, type=int))
    offset = (page - 1) * limit
    db     = get_db()
    songs  = db.execute("""
        SELECT s.*, (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count
        FROM songs s ORDER BY s.created_at DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    db.close()
    return jsonify([dict(r) for r in songs])


@app.route("/api/songs/<int:song_id>/play", methods=["POST"])
def increment_play(song_id):
    db = get_db()
    user_id = session.get("user_id")
    song = db.execute("SELECT genre FROM songs WHERE id = ?", (song_id,)).fetchone()
    
    # Musiqa har safar tinglanganda qiziqish jadvaliga +1 ball yoziladi
    if song and user_id:
        db.execute("""
            INSERT INTO user_interests (user_id, genre, score) 
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, genre) DO UPDATE SET score = score + 1
        """, (user_id, song["genre"]))
        
    db.execute("UPDATE songs SET play_count = play_count + 1 WHERE id = ?", (song_id,))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════════════════════
# 2-QISM: AVTORIZATSIYA (LOGIN & REGISTER)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            error = "Barcha maydonlarni to'ldiring."
        elif len(password) < 6:
            error = "Parol kamida 6 belgidan iborat bo'lishi kerak."
        else:
            db = get_db()
            exists = db.execute("SELECT id FROM users WHERE username=? OR email=?", (username, email)).fetchone()

            if exists:
                error = "Bu username yoki email allaqachon mavjud."
            else:
                pw_hash = generate_password_hash(password)
                db.execute("INSERT INTO users (username, email, password_hash) VALUES (?,?,?)", (username, email, pw_hash))
                db.commit()
                user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                db.close()
                session["user_id"]  = user["id"]
                session["username"] = username
                return redirect(url_for("index"))
            db.close()

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? OR email=?", (identifier, identifier.lower())).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        else:
            error = "Username/email yoki parol noto'g'ri."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/profile/<username>")
def profile(username):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        db.close()
        return "Foydalanuvchi topilmadi jigar", 404

    songs = db.execute("""
        SELECT id, title, artist, cover_url, audio_url, duration, genre, play_count,
        (SELECT COUNT(*) FROM likes WHERE song_id = songs.id) AS like_count
        FROM songs WHERE uploader_id=? ORDER BY created_at DESC
    """, (user["id"],)).fetchall()

    followers_count = db.execute("SELECT COUNT(*) FROM follows WHERE following_id=?", (user["id"],)).fetchone()[0]
    following_count = db.execute("SELECT COUNT(*) FROM follows WHERE follower_id=?", (user["id"],)).fetchone()[0]
    
    # Pleylistlarni yuklash va profil sahifasiga uzatish
    playlists = db.execute("SELECT * FROM playlists WHERE owner_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()
    db.close()

    is_owner = session.get("user_id") == user["id"]
    return render_template("profile.html",
                           user=dict(user),
                           songs=[dict(s) for s in songs],
                           playlists=[dict(p) for p in playlists],
                           followers=followers_count,
                           following=following_count,
                           is_owner=is_owner,
                           current_user=session.get("username"))


@app.route("/profile/<username>/upload", methods=["POST"])
@login_required
def upload_song(username):
    if session.get("username") != username:
        return "Ruxsat yo'q", 403

    title  = request.form.get("title", "").strip()
    artist = request.form.get("artist", "").strip() or username
    genre  = request.form.get("genre", "Unknown").strip()
    cover  = request.files.get("cover")
    audio  = request.files.get("audio")

    if not title or not audio:
        flash("Sarlavha va audio fayl tanlanishi shart.")
        return redirect(url_for("profile", username=username))

    if not allowed(audio.filename, ALLOWED_AUD):
        flash("Faqat .mp3 formatdagi musiqalarni yuklash mumkin.")
        return redirect(url_for("profile", username=username))

    # To'g'rilangan fayl saqlash logikasi (Nisbiy veb URL qaytadi)
    audio_url = save_file(audio, AUDIO_FOLDER, "audio")
    audio_full_path = os.path.join(BASE_DIR, audio_url.lstrip('/'))

    duration = 0
    try:
        duration = int(MP3(audio_full_path).info.length)
    except Exception:
        pass

    if cover and cover.filename and allowed(cover.filename, ALLOWED_IMG):
        cover_url = save_file(cover, COVER_FOLDER, "covers")
    else:
        cover_url = "https://picsum.photos/seed/" + uuid.uuid4().hex[:8] + "/400/400"

    db = get_db()
    db.execute("""
        INSERT INTO songs (title, artist, cover_url, audio_url, duration, genre, uploader_id)
        VALUES (?,?,?,?,?,?,?)
    """, (title, artist, cover_url, audio_url, duration, genre, session["user_id"]))
    db.commit()
    db.close()

    return redirect(url_for("profile", username=username))


# ═══════════════════════════════════════════════════════════════════════════════
# 3-QISM: REAL-TIME AJAX LAYKLAR & SOSIAL TIZIM
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    db = get_db()
    if query:
        songs = db.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count 
            FROM songs s 
            WHERE s.title LIKE ? OR s.artist LIKE ? OR s.genre LIKE ?
            ORDER BY s.created_at DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
    else:
        songs = []
    db.close()
    return render_template("search.html", songs=[dict(s) for s in songs], query=query, current_user=session.get("username"))


@app.route("/api/songs/<int:song_id>/like", methods=["POST"])
@login_required
def like_song(song_id):
    """Sahifani yangilamasdan, bir zumda layk bosish va algoritm ballini hisoblash."""
    db = get_db()
    user_id = session["user_id"]
    
    song = db.execute("SELECT genre FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not song:
        db.close()
        return jsonify({"error": "Musiqa topilmadi"}), 404
        
    like = db.execute("SELECT id FROM likes WHERE user_id = ? AND song_id = ?", (user_id, song_id)).fetchone()
    
    if like:
        db.execute("DELETE FROM likes WHERE user_id = ? AND song_id = ?", (user_id, song_id))
        action = "unliked"
        score_change = -2  # Layk olib tashlansa qiziqish pasayadi
    else:
        db.execute("INSERT INTO likes (user_id, song_id) VALUES (?, ?)", (user_id, song_id))
        action = "liked"
        score_change = 3   # Layk bosganda algoritm juda kuchli ishlaydi (+3 ball)
        
    # Algoritm jadvalini yangilash
    db.execute("""
        INSERT INTO user_interests (user_id, genre, score) VALUES (?, ?, ?)
        ON CONFLICT(user_id, genre) DO UPDATE SET score = MAX(0, score + ?)
    """, (user_id, song["genre"], max(0, score_change), score_change))
    
    db.commit()
    total_likes = db.execute("SELECT COUNT(*) FROM likes WHERE song_id = ?", (song_id,)).fetchone()[0]
    db.close()
    
    return jsonify({"status": "ok", "action": action, "like_count": total_likes})


# ═══════════════════════════════════════════════════════════════════════════════
# 4-QISM: PLEYLISTLAR VA ALBOM TIZIMI
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/playlists")
@login_required
def playlists_page():
    db    = get_db()
    rows  = db.execute("""
        SELECT p.*, (SELECT COUNT(*) FROM playlist_songs ps WHERE ps.playlist_id = p.id) AS song_count
        FROM playlists p WHERE p.owner_id = ? ORDER BY p.created_at DESC
    """, (session["user_id"],)).fetchall()
    db.close()
    return render_template("playlists.html", playlists=[dict(r) for r in rows], detail=None, current_user=session.get("username"))


@app.route("/playlists/create", methods=["POST"])
@login_required
def playlist_create():
    name      = request.form.get("name", "").strip()
    is_public = 1 if request.form.get("is_public") else 0

    if not name:
        flash("Pleylist nomi bo'sh bo'lishi mumkin emas.")
        return redirect(url_for("profile", username=session["username"]))

    db = get_db()
    db.execute("INSERT INTO playlists (name, owner_id, is_public) VALUES (?,?,?)", (name, session["user_id"], is_public))
    db.commit()
    db.close()
    return redirect(url_for("profile", username=session["username"]))


@app.route("/playlists/<int:playlist_id>")
@login_required
def playlist_detail(playlist_id):
    db = get_db()
    pl = db.execute("SELECT * FROM playlists WHERE id=? AND owner_id=?", (playlist_id, session["user_id"])).fetchone()
    if not pl:
        db.close()
        return "Pleylist topilmadi yoki ruxsat berilmagan", 403

    songs = db.execute("""
        SELECT s.*, ps.position FROM playlist_songs ps
        JOIN songs s ON s.id = ps.song_id
        WHERE ps.playlist_id = ? ORDER BY ps.position ASC
    """, (playlist_id,)).fetchall()
    db.close()
    return render_template("playlists.html", playlists=None, detail=dict(pl), songs=[dict(r) for r in songs], current_user=session.get("username"))


@app.route("/playlists/<int:playlist_id>/add/<int:song_id>", methods=["POST"])
@login_required
def playlist_add_song(playlist_id, song_id):
    db = get_db()
    pl = db.execute("SELECT id FROM playlists WHERE id=? AND owner_id=?", (playlist_id, session["user_id"])).fetchone()
    if not pl:
        db.close()
        return jsonify({"error": "Ruxsat yo'q"}), 403

    last = db.execute("SELECT COALESCE(MAX(position),0) FROM playlist_songs WHERE playlist_id=?", (playlist_id,)).fetchone()[0]

    try:
        db.execute("INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?,?,?)", (playlist_id, song_id, last + 1))
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception:
        db.close()
        return jsonify({"status": "already_added"})


@app.route("/playlists/<int:playlist_id>/remove/<int:song_id>", methods=["POST"])
@login_required
def playlist_remove_song(playlist_id, song_id):
    db = get_db()
    pl = db.execute("SELECT id FROM playlists WHERE id=? AND owner_id=?", (playlist_id, session["user_id"])).fetchone()
    if not pl:
        db.close()
        return jsonify({"error": "Ruxsat yo'q"}), 403

    db.execute("DELETE FROM playlist_songs WHERE playlist_id=? AND song_id=?", (playlist_id, song_id))
    db.commit()
    db.close()
    return jsonify({"status": "removed"})


@app.route("/api/playlists")
@login_required
def api_my_playlists():
    db   = get_db()
    rows = db.execute("SELECT id, name FROM playlists WHERE owner_id=? ORDER BY created_at DESC", (session["user_id"],)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
import os
import uuid
from functools import wraps

from flask import (Flask, render_template, jsonify, request,
                   session, redirect, url_for, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from mutagen.mp3 import MP3          # pip install mutagen
from models import init_db, seed_demo_data, get_db

# ── Sozlamalar ────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
COVER_FOLDER  = os.path.join(UPLOAD_FOLDER, "covers")
AUDIO_FOLDER  = os.path.join(UPLOAD_FOLDER, "audio")
ALLOWED_IMG   = {"png", "jpg", "jpeg", "webp"}
ALLOWED_AUD   = {"mp3"}

os.makedirs(COVER_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "jmgramm-secret-2025-change-in-prod"

with app.app_context():
    init_db()
    seed_demo_data()


# ── Yordamchi funksiyalar ─────────────────────────────────────────────────────
def allowed(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def save_file(file, folder):
    """Faylni UUID nomi bilan saqlaydi, URL qaytaradi."""
    ext  = file.filename.rsplit(".", 1)[1].lower()
    name = uuid.uuid4().hex + "." + ext
    path = os.path.join(folder, name)
    file.save(path)
    return path  # to'liq disk yo'li


# ═══════════════════════════════════════════════════════════════════════════════
# 1-QISM: LENTA
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    db    = get_db()
    songs = db.execute("""
        SELECT s.id, s.title, s.artist, s.cover_url, s.audio_url,
               s.duration, s.genre, s.play_count,
               (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count
        FROM songs s ORDER BY s.created_at DESC LIMIT 20
    """).fetchall()
    db.close()
    return render_template("index.html",
                           songs=[dict(r) for r in songs],
                           current_user=session.get("username"))


@app.route("/api/feed")
def api_feed():
    page   = max(1, request.args.get("page",  1,  type=int))
    limit  = min(50, request.args.get("limit", 10, type=int))
    offset = (page - 1) * limit
    db     = get_db()
    songs  = db.execute("""
        SELECT s.id, s.title, s.artist, s.cover_url, s.audio_url,
               s.duration, s.genre, s.play_count,
               (SELECT COUNT(*) FROM likes WHERE song_id = s.id) AS like_count
        FROM songs s ORDER BY s.created_at DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    db.close()
    return jsonify([dict(r) for r in songs])


@app.route("/api/songs/<int:song_id>/play", methods=["POST"])
def increment_play(song_id):
    db = get_db()
    db.execute("UPDATE songs SET play_count = play_count + 1 WHERE id = ?", (song_id,))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════════════════════
# 2-QISM: AUTH (Register / Login / Logout)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            error = "Barcha maydonlarni to'ldiring."
        elif len(password) < 6:
            error = "Parol kamida 6 belgidan iborat bo'lishi kerak."
        else:
            db = get_db()
            exists = db.execute(
                "SELECT id FROM users WHERE username=? OR email=?", (username, email)
            ).fetchone()

            if exists:
                error = "Bu username yoki email allaqachon ro'yxatdan o'tgan."
            else:
                pw_hash = generate_password_hash(password)
                db.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
                    (username, email, pw_hash)
                )
                db.commit()
                user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                db.close()
                session["user_id"]  = user["id"]
                session["username"] = username
                return redirect(url_for("profile", username=username))
            db.close()

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        db   = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (identifier, identifier.lower())
        ).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        else:
            error = "Username/email yoki parol noto'g'ri."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ═══════════════════════════════════════════════════════════════════════════════
# 2-QISM: PROFIL va MUSIQA YUKLASH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/profile/<username>")
def profile(username):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        db.close()
        return "Foydalanuvchi topilmadi", 404

    songs = db.execute("""
        SELECT id, title, artist, cover_url, audio_url, duration, genre, play_count
        FROM songs WHERE uploader_id=? ORDER BY created_at DESC
    """, (user["id"],)).fetchall()

    followers_count = db.execute(
        "SELECT COUNT(*) FROM follows WHERE following_id=?", (user["id"],)
    ).fetchone()[0]
    following_count = db.execute(
        "SELECT COUNT(*) FROM follows WHERE follower_id=?", (user["id"],)
    ).fetchone()[0]
    db.close()

    is_owner = session.get("user_id") == user["id"]
    return render_template("profile.html",
                           user=dict(user),
                           songs=[dict(s) for s in songs],
                           followers=followers_count,
                           following=following_count,
                           is_owner=is_owner,
                           current_user=session.get("username"))


@app.route("/profile/<username>/upload", methods=["POST"])
@login_required
def upload_song(username):
    if session.get("username") != username:
        return "Ruxsat yo'q", 403

    title  = request.form.get("title", "").strip()
    artist = request.form.get("artist", "").strip() or username
    genre  = request.form.get("genre", "Unknown").strip()
    cover  = request.files.get("cover")
    audio  = request.files.get("audio")

    if not title or not audio:
        flash("Sarlavha va audio fayl majburiy.")
        return redirect(url_for("profile", username=username))

    if not allowed(audio.filename, ALLOWED_AUD):
        flash("Faqat .mp3 format qabul qilinadi.")
        return redirect(url_for("profile", username=username))

    # Audio saqlash
    audio_path = save_file(audio, AUDIO_FOLDER)
    audio_url  = "/" + audio_path.replace(BASE_DIR + os.sep, "").replace(os.sep, "/")

    # Davomiylikni mutagen bilan aniqlaymiz
    duration = 0
    try:
        duration = int(MP3(audio_path).info.length)
    except Exception:
        pass

    # Muqova saqlash
    if cover and cover.filename and allowed(cover.filename, ALLOWED_IMG):
        cover_path = save_file(cover, COVER_FOLDER)
        cover_url  = "/" + cover_path.replace(BASE_DIR + os.sep, "").replace(os.sep, "/")
    else:
        cover_url = "https://picsum.photos/seed/" + uuid.uuid4().hex[:8] + "/400/400"

    db = get_db()
    db.execute("""
        INSERT INTO songs (title, artist, cover_url, audio_url, duration, genre, uploader_id)
        VALUES (?,?,?,?,?,?,?)
    """, (title, artist, cover_url, audio_url, duration, genre, session["user_id"]))
    db.commit()
    db.close()

    return redirect(url_for("profile", username=username))


# ═══════════════════════════════════════════════════════════════════════════════
# 3-QISM POYDEVORI
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/search")
def search():
    return "<h2>3-qismda: Qidiruv sahifasi</h2>", 200

@app.route("/api/songs/<int:song_id>/like", methods=["POST"])
def like_song(song_id):
    return jsonify({"status": "3-qismda implement qilinadi"}), 200


# ═══════════════════════════════════════════════════════════════════════════════
# 4-QISM: PLEYLISTLAR
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/playlists")
@login_required
def playlists_page():
    """Joriy foydalanuvchining barcha pleylistlari."""
    db    = get_db()
    rows  = db.execute("""
        SELECT p.id, p.name, p.cover_url, p.is_public,
               (SELECT COUNT(*) FROM playlist_songs ps WHERE ps.playlist_id = p.id) AS song_count
        FROM playlists p
        WHERE p.owner_id = ?
        ORDER BY p.created_at DESC
    """, (session["user_id"],)).fetchall()
    db.close()
    return render_template("playlists.html",
                           playlists=[dict(r) for r in rows],
                           current_user=session.get("username"))


@app.route("/playlists/create", methods=["POST"])
@login_required
def playlist_create():
    """Yangi pleylist yaratish."""
    name      = request.form.get("name", "").strip()
    is_public = 1 if request.form.get("is_public") else 0

    if not name:
        return jsonify({"error": "Pleylist nomi kerak"}), 400

    db = get_db()
    db.execute(
        "INSERT INTO playlists (name, owner_id, is_public) VALUES (?,?,?)",
        (name, session["user_id"], is_public)
    )
    db.commit()
    db.close()
    return redirect(url_for("playlists_page"))


@app.route("/playlists/<int:playlist_id>")
@login_required
def playlist_detail(playlist_id):
    """Pleylist ichidagi musiqalar."""
    db = get_db()
    pl = db.execute(
        "SELECT * FROM playlists WHERE id=? AND owner_id=?",
        (playlist_id, session["user_id"])
    ).fetchone()
    if not pl:
        db.close()
        return "Pleylist topilmadi yoki ruxsat yo'q", 404

    songs = db.execute("""
        SELECT s.id, s.title, s.artist, s.cover_url, s.audio_url,
               s.duration, s.genre, s.play_count,
               ps.position
        FROM playlist_songs ps
        JOIN songs s ON s.id = ps.song_id
        WHERE ps.playlist_id = ?
        ORDER BY ps.position ASC
    """, (playlist_id,)).fetchall()
    db.close()
    return render_template("playlists.html",
                           playlists=None,
                           detail=dict(pl),
                           songs=[dict(r) for r in songs],
                           current_user=session.get("username"))


@app.route("/playlists/<int:playlist_id>/add/<int:song_id>", methods=["POST"])
@login_required
def playlist_add_song(playlist_id, song_id):
    """Musiqani pleylistga qo'shish."""
    db = get_db()
    # Pleylist egasi tekshiruvi
    pl = db.execute(
        "SELECT id FROM playlists WHERE id=? AND owner_id=?",
        (playlist_id, session["user_id"])
    ).fetchone()
    if not pl:
        db.close()
        return jsonify({"error": "Ruxsat yo'q"}), 403

    # Oxirgi pozitsiya
    last = db.execute(
        "SELECT COALESCE(MAX(position),0) FROM playlist_songs WHERE playlist_id=?",
        (playlist_id,)
    ).fetchone()[0]

    try:
        db.execute(
            "INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?,?,?)",
            (playlist_id, song_id, last + 1)
        )
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception:
        db.close()
        return jsonify({"status": "already_added"})


@app.route("/playlists/<int:playlist_id>/remove/<int:song_id>", methods=["POST"])
@login_required
def playlist_remove_song(playlist_id, song_id):
    """Musiqani pleylistdan o'chirish."""
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE id=? AND owner_id=?",
        (playlist_id, session["user_id"])
    ).fetchone()
    if not pl:
        db.close()
        return jsonify({"error": "Ruxsat yo'q"}), 403

    db.execute(
        "DELETE FROM playlist_songs WHERE playlist_id=? AND song_id=?",
        (playlist_id, song_id)
    )
    db.commit()
    db.close()
    return jsonify({"status": "removed"})


@app.route("/api/playlists")
@login_required
def api_my_playlists():
    """Foydalanuvchi pleylistlari (JSON) — pleylistga qo'shish modal uchun."""
    db   = get_db()
    rows = db.execute(
        "SELECT id, name FROM playlists WHERE owner_id=? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
