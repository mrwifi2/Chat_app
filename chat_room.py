import threading
import sys

def receive_messages(sock):
    while True:
        try:
            msg = sock.recv(1024).decode('utf-8')
            if not msg:
                break
            print(msg, end="")
        except Exception:
            break

def start_chat_session(sock, user, room_id):
    print("\n" + "="*35)
    print(f"      CHAT ROOM: {room_id}")
    print("="*35)
    print("Type message below (/exit to leave room):\n")

    # Background thread to receive messages in real-time
    threading.Thread(target=receive_messages, args=(sock,), daemon=True).start()

    while True:
        try:
            msg = input("[You]: ")
            if msg == "/exit":
                print("\n[+] Exiting chat room...")
                sock.close()
                sys.exit()
            sock.send(f"MSG:{msg}".encode('utf-8'))
        except KeyboardInterrupt:
            sock.close()
            sys.exit()
