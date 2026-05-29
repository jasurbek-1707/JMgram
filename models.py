import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

DB_PATH = 'gmgram.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            bio TEXT DEFAULT '',
            avatar_url TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            cover_url TEXT DEFAULT '',
            audio_url TEXT NOT NULL,
            duration INTEGER DEFAULT 180,
            genre TEXT NOT NULL DEFAULT 'Pop',
            owner_id INTEGER,
            play_count INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS listen_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS playlist_songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
            UNIQUE(playlist_id, song_id)
        );
        CREATE TABLE IF NOT EXISTS user_interests (
            user_id INTEGER NOT NULL,
            genre TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, genre)
        );
    ''')
    
    # Seed Demo Ma'lumotlar
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username,email,password_hash,bio,avatar_url) VALUES (?,?,?,?,?)",
                  ("jmuser", "demo@gmgram.uz", generate_password_hash("demo1234"), "GMgram asoschisi", "https://picsum.photos/seed/avatar1/200/200"))
        
        songs = [
            ("Uzbek Vibes","DJ Pulse","Bass","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"),
            ("Summer Remix","TrackStar","Remix","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3"),
            ("Popstar","Lila Moon","Pop","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"),
            ("Istanbul Nights","Tarkan B","Turkcha","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3"),
            ("Deep Bass","DJ Pulse","Bass","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3"),
            ("Retro Wave","TrackStar","Remix","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3"),
            ("Love Pop","Lila Moon","Pop","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3"),
            ("Ankara Sabahi","Tarkan B","Turkcha","https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3"),
        ]
        for s in songs:
            c.execute("INSERT INTO songs (title,artist,genre,audio_url,duration,owner_id) VALUES (?,?,?,?,180,1)", s)
        
        c.execute("INSERT INTO playlists (name,owner_id) VALUES (?,?)", ("Sevimlilarim",1))
        c.execute("INSERT INTO playlist_songs (playlist_id,song_id,position) VALUES (1,1,1)")
        c.execute("INSERT INTO playlist_songs (playlist_id,song_id,position) VALUES (1,2,2)")
        
    conn.commit()
    conn.close()
