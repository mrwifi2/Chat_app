from login import run_login
from new_chat import handle_new_chat

def main():
    sock, user = run_login()
    if not sock:
        return

    while True:
        print(f"\n=== HOME SCREEN ({user}) ===")
        print("1. New Chat (Join/Create Room)")
        print("2. Logout / Exit")
        ch = input("Select option (1/2): ").strip()

        if ch == "1":
            handle_new_chat(sock, user)
            break
        elif ch == "2":
            print("[+] Logging out...")
            sock.close()
            break
        else:
            print("[-] Invalid Choice")

if __name__ == "__main__":
    main()
