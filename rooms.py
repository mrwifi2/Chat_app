import random
import string

# Active rooms list (temporary in-memory store)
active_rooms = []

def generate_room_id():
    chars = string.ascii_uppercase + string.digits
    room_id = ''.join(random.choice(chars) for _ in range(6))
    active_rooms.append(room_id)
    return room_id

def room_exists(room_id):
    return room_id in active_rooms

if __name__ == "__main__":
    new_id = generate_room_id()
    print(f"[+] Generated Room ID: {new_id}")
    print(f"[+] Room Exists Check: {room_exists(new_id)}")
