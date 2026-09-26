import sqlite3
import getpass

username = input("Username: ").strip()

if not username:
    print("[-] Username cannot be empty.")
    exit()

conn = sqlite3.connect("chat_app.db")
cursor = conn.cursor()

cursor.execute(
    "SELECT username FROM users WHERE username=?",
    (username,)
)

if not cursor.fetchone():
    print(f"[-] User '{username}' not found.")
    conn.close()
    exit()

new_password = getpass.getpass("New password: ")

if not new_password:
    print("[-] Password cannot be empty.")
    conn.close()
    exit()

cursor.execute(
    "UPDATE users SET password=? WHERE username=?",
    (new_password, username)
)

conn.commit()
conn.close()

print(f"[+] Password changed successfully for '{username}'.")
