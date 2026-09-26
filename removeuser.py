import sys
import sqlite3

if len(sys.argv) != 2:
    print("Usage: python removeuser.py <username>")
    sys.exit(1)

username = sys.argv[1]

conn = sqlite3.connect("chat_app.db")
cursor = conn.cursor()

cursor.execute(
    "DELETE FROM users WHERE username=?",
    (username,)
)

if cursor.rowcount > 0:
    print(f"[+] User '{username}' removed successfully.")
else:
    print(f"[-] User '{username}' not found.")

conn.commit()
conn.close()
