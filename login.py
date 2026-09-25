import socket

HOST = '127.0.0.1'
PORT = 8000

def run_login():
    print("\n====================")
    print("      CHAT APP      ")
    print("====================")
    print("1. Login")
    print("2. Register New User")
    
    choice = input("Select Option (1/2): ").strip()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except Exception:
        print("[-] Server se connect nahi ho paya. Check main.py!")
        return None, None

    if choice == "2":
        user = input("Choose New Login ID: ")
        pwd = input("Choose Password: ")
        sock.send(f"REGISTER:{user}:{pwd}".encode('utf-8'))
        res = sock.recv(1024).decode('utf-8')
        if res == "REG_SUCCESS":
            print("[+] Registration Successful! Restart and Login now.")
        else:
            print("[-] Username already exists.")
        sock.close()
        return None, None

    elif choice == "1":
        user = input("Login ID : ")
        pwd = input("Password : ")
        sock.send(f"LOGIN:{user}:{pwd}".encode('utf-8'))
        res = sock.recv(1024).decode('utf-8')

        if res == "SUCCESS":
            print(f"\n[+] Login Successful! Welcome {user}.")
            return sock, user
        else:
            print("\n[-] Invalid Credentials.")
            sock.close()
            return None, None

if __name__ == "__main__":
    run_login()
