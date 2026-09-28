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
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        edited INTEGER NOT NULL DEFAULT 0,
                        unsent INTEGER NOT NULL DEFAULT 0)''')

    # Migration safety net: older deployments created "messages" before the
    # edited/unsent columns existed. ALTER TABLE ADD COLUMN is a no-op error
    # if the column is already there, so we just swallow that specific case.
    for col_def in ("edited INTEGER NOT NULL DEFAULT 0", "unsent INTEGER NOT NULL DEFAULT 0"):
        try:
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass

    # 3. Room membership table (who belongs to which room -> powers the
    #    multi-room sidebar and lets a user come back to old chats)
    cursor.execute('''CREATE TABLE IF NOT EXISTS memberships (
                        username TEXT NOT NULL,
                        room_id TEXT NOT NULL,
                        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (username, room_id))''')

    # 4. Reactions table (one reaction per user per message — picking a new
    #    emoji replaces the old one, matching the client's toggle behaviour)
    cursor.execute('''CREATE TABLE IF NOT EXISTS reactions (
                        message_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        emoji TEXT NOT NULL,
                        PRIMARY KEY (message_id, username))''')

    # Default users (kept for compatibility with the existing app)
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('ajju', '1234')")
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('rahul', '1234')")

    # Rooms are an in-memory concept (see rooms.py) that resets whenever the
    # server process restarts. Any messages/memberships left over from a
    # previous run can never become reachable again (their room_id will
    # never be re-issued), so we clear them on startup to stop the database
    # file from growing forever. User accounts are NOT touched.
    cursor.execute("DELETE FROM reactions")
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
    return {"id": msg_id, "timestamp": row[0] if row else None}


def get_chat_history(room_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sender, message, timestamp, edited, unsent FROM messages WHERE room_id=? ORDER BY id ASC",
        (room_id,)
    )
    rows = cursor.fetchall()

    cursor.execute(
        "SELECT message_id, username, emoji FROM reactions WHERE message_id IN "
        "(SELECT id FROM messages WHERE room_id=?)",
        (room_id,)
    )
    reaction_rows = cursor.fetchall()
    conn.close()

    reactions_by_msg = {}
    for message_id, username, emoji in reaction_rows:
        reactions_by_msg.setdefault(message_id, {})[username] = emoji

    return [
        {
            "id": r[0],
            "sender": r[1],
            "message": r[2],
            "timestamp": r[3],
            "edited": bool(r[4]),
            "unsent": bool(r[5]),
            "reactions": reactions_by_msg.get(r[0], {})
        }
        for r in rows
    ]


def get_message_info(message_id):
    """Returns (room_id, sender, unsent) for a message, or None if it doesn't exist."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT room_id, sender, unsent FROM messages WHERE id=?",
        (message_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"room_id": row[0], "sender": row[1], "unsent": bool(row[2])}


def edit_message(message_id, username, new_text):
    """Only the original sender can edit, and only while the message hasn't
    been unsent. Returns the affected room_id on success, else None."""
    info = get_message_info(message_id)
    if not info or info["sender"] != username or info["unsent"]:
        return None

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE messages SET message=?, edited=1 WHERE id=?",
        (new_text, message_id)
    )
    conn.commit()
    conn.close()
    return info["room_id"]


def unsend_message(message_id, username):
    """Only the original sender can unsend. Returns the affected room_id on
    success, else None."""
    info = get_message_info(message_id)
    if not info or info["sender"] != username or info["unsent"]:
        return None

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE messages SET unsent=1 WHERE id=?", (message_id,))
    cursor.execute("DELETE FROM reactions WHERE message_id=?", (message_id,))
    conn.commit()
    conn.close()
    return info["room_id"]


def set_reaction(message_id, username, emoji):
    """Toggle a user's reaction on a message: picking the same emoji again
    removes it, picking a different one replaces it. Returns
    (room_id, final_emoji_or_None) or None if the message doesn't exist /
    was unsent."""
    info = get_message_info(message_id)
    if not info or info["unsent"]:
        return None

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emoji FROM reactions WHERE message_id=? AND username=?",
        (message_id, username)
    )
    existing = cursor.fetchone()

    if existing and existing[0] == emoji:
        cursor.execute(
            "DELETE FROM reactions WHERE message_id=? AND username=?",
            (message_id, username)
        )
        final_emoji = None
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO reactions (message_id, username, emoji) VALUES (?, ?, ?)",
            (message_id, username, emoji)
        )
        final_emoji = emoji

    conn.commit()
    conn.close()
    return (info["room_id"], final_emoji)


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
    """Wipe a room's chat history, reactions and every membership row for it."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM reactions WHERE message_id IN (SELECT id FROM messages WHERE room_id=?)",
        (room_id,)
    )
    cursor.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
    cursor.execute("DELETE FROM memberships WHERE room_id=?", (room_id,))
    conn.commit()
    conn.close()
def admin_list_users():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users ORDER BY username")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def admin_create_user(username, password):
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def admin_change_password(username, password):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password=? WHERE username=?",
        (password, username)
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def admin_change_username(old_username, new_username):
    if not old_username or not new_username:
        return False

    conn = _connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE users SET username=? WHERE username=?",
            (new_username, old_username)
        )

        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return False

        cursor.execute(
            "UPDATE memberships SET username=? WHERE username=?",
            (new_username, old_username)
        )

        cursor.execute(
            "UPDATE messages SET sender=? WHERE sender=?",
            (new_username, old_username)
        )

        cursor.execute(
            "UPDATE reactions SET username=? WHERE username=?",
            (new_username, old_username)
        )

        conn.commit()
        conn.close()
        return True

    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return False


def admin_delete_user(username):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM users WHERE username=?",
        (username,)
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

if __name__ == "__main__":
    init_db()
    print("[+] Database initialised (users kept, room data cleared).")
