import sqlite3

DB_NAME = "chat_app.db"


def _connect():
    conn = sqlite3.connect(DB_NAME)
    return conn


def init_db():
    conn = _connect()
    cursor = conn.cursor()

    # 1. User Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT NOT NULL)''')

    # 2. Chat History Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_id TEXT NOT NULL,
                        sender TEXT NOT NULL,
                        message TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 3. Room membership table (who belongs to which room -> powers the
    #    multi-room sidebar and lets a user come back to old chats)
    cursor.execute('''CREATE TABLE IF NOT EXISTS memberships (
                        username TEXT NOT NULL,
                        room_id TEXT NOT NULL,
                        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (username, room_id))''')

    # Default users (kept for compatibility with the existing app)
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('ajju', '1234')")
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('rahul', '1234')")

    # Rooms are an in-memory concept (see rooms.py) that resets whenever the
    # server process restarts. Any messages/memberships left over from a
    # previous run can never become reachable again (their room_id will
    # never be re-issued), so we clear them on startup to stop the database
    # file from growing forever. User accounts are NOT touched.
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM memberships")

    conn.commit()
    conn.close()


def register_user(username, password):
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users VALUES (?, ?)",
            (username, password)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username, password):
    if not username or not password:
        return False

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM users WHERE username=? AND password=?",
        (username, password)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def save_message(room_id, sender, message):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (room_id, sender, message) VALUES (?, ?, ?)",
        (room_id, sender, message)
    )
    conn.commit()
    msg_id = cursor.lastrowid
    cursor.execute("SELECT timestamp FROM messages WHERE id=?", (msg_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_chat_history(room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sender, message, timestamp FROM messages WHERE room_id=? ORDER BY id ASC",
        (room_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"sender": r[0], "message": r[1], "timestamp": r[2]}
        for r in rows
    ]


def delete_chat_history(room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
    conn.commit()
    conn.close()


def add_membership(username, room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO memberships (username, room_id) VALUES (?, ?)",
        (username, room_id)
    )
    conn.commit()
    conn.close()


def remove_membership(username, room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM memberships WHERE username=? AND room_id=?",
        (username, room_id)
    )
    conn.commit()
    conn.close()


def get_room_members(room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username FROM memberships WHERE room_id=?",
        (room_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_user_rooms(username):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT room_id FROM memberships WHERE username=? ORDER BY joined_at ASC",
        (username,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def remove_room_completely(room_id):
    """Wipe a room's chat history and every membership row for it."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
    cursor.execute("DELETE FROM memberships WHERE room_id=?", (room_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("[+] Database initialised (users kept, room data cleared).")
