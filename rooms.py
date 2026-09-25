import random

# Active rooms list (temporary in-memory store)
active_rooms = set()

ROOM_ID_LENGTH = 6


def generate_room_id():
    while True:
        room_id = ''.join(
            random.choice("0123456789")
            for _ in range(ROOM_ID_LENGTH)
        )

        if room_id not in active_rooms:
            active_rooms.add(room_id)
            return room_id


def room_exists(room_id):
    return room_id in active_rooms


def remove_room(room_id):
    active_rooms.discard(room_id)


if __name__ == "__main__":
    new_id = generate_room_id()
    print(f"[+] Generated Room ID: {new_id}")
    print(f"[+] Room Exists Check: {room_exists(new_id)}")
