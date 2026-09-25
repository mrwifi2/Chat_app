import asyncio
import os
import json
import websockets
from database import init_db, verify_user, register_user, save_message, get_chat_history
from rooms import generate_room_id, room_exists, remove_room

init_db()

# Connected clients map: { room_id: set(websocket_connections) }
ROOMS = {}

async def handler(websocket):
    current_room = None
    current_user = None

    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("type")

            # 1. LOGIN
            if action == "LOGIN":
                user, pwd = data["username"], data["password"]
                if verify_user(user, pwd):
                    current_user = user
                    await websocket.send(json.dumps({"status": "SUCCESS", "type": "LOGIN_RES", "user": user}))
                else:
                    await websocket.send(json.dumps({"status": "FAILED", "type": "LOGIN_RES"}))

            # 2. REGISTER
            elif action == "REGISTER":
                user, pwd = data["username"], data["password"]
                if register_user(user, pwd):
                    await websocket.send(json.dumps({"status": "REG_SUCCESS", "type": "REG_RES"}))
                else:
                    await websocket.send(json.dumps({"status": "REG_EXISTS", "type": "REG_RES"}))

            # 3. CREATE ROOM
            elif action == "CREATE_ROOM":
                room_id = generate_room_id()
                ROOMS[room_id] = {websocket}
                current_room = room_id
                await websocket.send(json.dumps({"type": "ROOM_CREATED", "room_id": room_id}))

            # 4. JOIN ROOM
            elif action == "JOIN_ROOM":
                room_id = data["room_id"]
                if room_exists(room_id):
                    if room_id not in ROOMS:
                        ROOMS[room_id] = set()
                    ROOMS[room_id].add(websocket)
                    current_room = room_id
                    
                    # Send Previous Chat History
                    history = get_chat_history(room_id)
                    await websocket.send(json.dumps({
                        "type": "JOIN_SUCCESS", 
                        "room_id": room_id,
                        "history": history
                    }))
                else:
                    await websocket.send(json.dumps({"type": "ROOM_NOT_FOUND"}))

            # 5. MESSAGE BROADCAST
            elif action == "SEND_MSG":
                msg = data["message"]
                save_message(current_room, current_user, msg)
                
                # Broadcast to all users in this room
                broadcast_data = json.dumps({"type": "NEW_MSG", "sender": current_user, "message": msg})
                if current_room in ROOMS:
                    for conn in ROOMS[current_room]:
                        await conn.send(broadcast_data)

    except Exception:
        pass
    finally:
        if current_room and current_room in ROOMS:
            ROOMS[current_room].discard(websocket)

            # Room ko tab delete karo jab koi user connected na ho
            if not ROOMS[current_room]:
                remove_room(current_room)
                del ROOMS[current_room]

async def main():
    port = int(os.environ.get("PORT", 8000))

    async with websockets.serve(handler, "0.0.0.0", port):
        print(f"[+] WEB SOCKET SERVER RUNNING ON PORT {port}!")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
