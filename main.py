import socket
import threading
from auth import handle_auth
from rooms import generate_room_id, room_exists
from database import init_db, save_message, get_chat_history

HOST = '127.0.0.1'
PORT = 8000

active_rooms_clients = {}

def handle_client(conn, addr):
    current_room = None
    current_user = None

    while True:
        try:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                break

            # 1. Login & Register
            if data.startswith("LOGIN:") or data.startswith("REGISTER:"):
                res = handle_auth(data)
                if res == "SUCCESS":
                    current_user = data.split(":")[1]
                conn.send(res.encode('utf-8'))

            # 2. Create Room
            elif data == "CREATE_ROOM":
                room_id = generate_room_id()
                active_rooms_clients[room_id] = [conn]
                current_room = room_id
                conn.send(f"ROOM_CREATED:{room_id}".encode('utf-8'))

            # 3. Join Room + Send History
            elif data.startswith("JOIN_ROOM:"):
                room_id = data.split(":")[1]
                if room_exists(room_id):
                    if room_id not in active_rooms_clients:
                        active_rooms_clients[room_id] = []
                    active_rooms_clients[room_id].append(conn)
                    current_room = room_id
                    conn.send("JOIN_SUCCESS".encode('utf-8'))
                    
                    # Fetch and Send Previous Messages History
                    history = get_chat_history(room_id)
                    history_str = "\n".join([f"{s}: {m}" for s, m in history])
                    if history_str:
                        conn.send(f"\n--- HISTORY ---\n{history_str}\n---------------\n".encode('utf-8'))
                else:
                    conn.send("ROOM_NOT_FOUND".encode('utf-8'))

            # 4. Save & Broadcast Message
            elif data.startswith("MSG:"):
                msg = data[4:]
                save_message(current_room, current_user, msg)
                for client in active_rooms_clients.get(current_room, []):
                    if client != conn:
                        client.send(f"\n{current_user}: {msg}\n[You]: ".encode('utf-8'))

        except Exception:
            break

    # Cleanup
    if current_room and current_room in active_rooms_clients:
        if conn in active_rooms_clients[current_room]:
            active_rooms_clients[current_room].remove(conn)
    conn.close()

def start_server():
    init_db()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[+] ENHANCED SERVER RUNNING on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()
