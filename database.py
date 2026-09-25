import sqlite3

DB_NAME = "chat_app.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
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
                        
    # Default Users
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('ajju', '1234')")
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('rahul', '1234')")
    
    conn.commit()
    conn.close()

def register_user(username, password):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users VALUES (?, ?)", (username, password))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False  # Username already exists

def verify_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def save_message(room_id, sender, message):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (room_id, sender, message) VALUES (?, ?, ?)", 
                   (room_id, sender, message))
    conn.commit()
    conn.close()

def get_chat_history(room_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, message FROM messages WHERE room_id=? ORDER BY id ASC", (room_id,))
    logs = cursor.fetchall()
    conn.close()
    return logs

if __name__ == "__main__":
    init_db()
    print("[+] Database Updated with Chat History & Registration!")
