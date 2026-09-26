import sqlite3

conn = sqlite3.connect("chat_app.db")
cursor = conn.cursor()

cursor.execute("SELECT username FROM users ORDER BY username ASC")
users = cursor.fetchall()

if users:
    print("\n=== USERS ===")
    for i, (username,) in enumerate(users, 1):
        print(f"{i}. {username}")
else:
    print("[-] No users found.")

conn.close()
