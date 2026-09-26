import sys
from database import register_user

if len(sys.argv) != 3:
    print("Usage: python adduser.py <username> <password>")
    sys.exit(1)

username = sys.argv[1]
password = sys.argv[2]

if not username:
    print("[-] Username cannot be empty.")
    sys.exit(1)

if any(char.isspace() for char in username):
    print("[-] Username cannot contain spaces.")
    sys.exit(1)

if not password:
    print("[-] Password cannot be empty.")
    sys.exit(1)

if register_user(username, password):
    print(f"[+] User '{username}' added successfully.")
else:
    print(f"[-] Username '{username}' already exists.")
