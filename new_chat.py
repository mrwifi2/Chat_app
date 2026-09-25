from chat_room import start_chat_session

def handle_new_chat(sock, user):
    print("\n--- NEW CHAT OPTIONS ---")
    print("1. Join Room (Enter Room ID)")
    print("2. Create New Room")
    choice = input("Select option (1/2): ").strip()

    if choice == "1":
        room_id = input("Enter 6-character Room ID: ").strip().upper()
        sock.send(f"JOIN_ROOM:{room_id}".encode('utf-8'))
        res = sock.recv(1024).decode('utf-8')
        
        if res == "JOIN_SUCCESS":
            print(f"[+] Successfully joined Room: {room_id}")
            start_chat_session(sock, user, room_id)
        else:
            print("[-] Room not found or invalid ID.")

    elif choice == "2":
        sock.send("CREATE_ROOM".encode('utf-8'))
        res = sock.recv(1024).decode('utf-8')
        
        if res.startswith("ROOM_CREATED:"):
            room_id = res.split(":")[1]
            print(f"[+] Room Created! Share Room ID with friend: {room_id}")
            start_chat_session(sock, user, room_id)
    else:
        print("[-] Invalid option selected.")
