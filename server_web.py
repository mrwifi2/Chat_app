import asyncio
import os
import json
import secrets
import websockets

from database import (
    init_db,
    verify_user,
    save_message,
    get_chat_history,
    delete_chat_history,
    add_membership,
    remove_membership,
    get_room_members,
    get_user_rooms,
    remove_room_completely
)

from rooms import (
    generate_room_id,
    room_exists,
    remove_room
)


init_db()


# ============================================================
# SERVER STATE
# ============================================================

# room_id -> set(websocket)  (sockets *currently* connected & viewing/using that room)
ROOM_SOCKETS = {}

# room_id -> asyncio.Task (idle-expiry countdown, active only while a room has 0 connected sockets)
ROOM_EXPIRY_TASKS = {}

# session_token -> { "username": str, "websocket": websocket or None }
SESSIONS = {}

# websocket -> username   (fast reverse lookup for presence calculations)
SOCKET_USER = {}


# Maximum 2 people per room (based on persistent membership, not just who's online right now)
MAX_ROOM_USERS = 2

# 12 minutes idle timeout before an empty room's history is wiped
ROOM_IDLE_TIMEOUT = 12 * 60


# ============================================================
# ROOM EXPIRY
# ============================================================

async def expire_room(room_id):
    try:
        await asyncio.sleep(ROOM_IDLE_TIMEOUT)

        if room_id in ROOM_SOCKETS and not ROOM_SOCKETS[room_id]:
            remove_room_completely(room_id)
            remove_room(room_id)
            ROOM_SOCKETS.pop(room_id, None)

            print(f"[-] Room {room_id} expired after 12 idle minutes.")

    except asyncio.CancelledError:
        pass

    finally:
        ROOM_EXPIRY_TASKS.pop(room_id, None)


def start_room_expiry(room_id):
    old_task = ROOM_EXPIRY_TASKS.get(room_id)

    if old_task and not old_task.done():
        old_task.cancel()

    ROOM_EXPIRY_TASKS[room_id] = asyncio.create_task(expire_room(room_id))


def cancel_room_expiry(room_id):
    task = ROOM_EXPIRY_TASKS.pop(room_id, None)

    if task and not task.done():
        task.cancel()


# ============================================================
# PRESENCE HELPERS
# ============================================================

def room_connected_usernames(room_id):
    sockets = ROOM_SOCKETS.get(room_id, set())
    return {SOCKET_USER[s] for s in sockets if s in SOCKET_USER}


def room_is_online(room_id):
    # With a 2-person cap, "partner online" simply means both members
    # currently have a live connection attached to this room.
    return len(room_connected_usernames(room_id)) >= 2


async def broadcast_presence(room_id):
    online = room_is_online(room_id)
    payload = json.dumps({
        "type": "PRESENCE_UPDATE",
        "room_id": room_id,
        "online": online
    })

    for conn in list(ROOM_SOCKETS.get(room_id, set())):
        try:
            await conn.send(payload)
        except Exception:
            pass


# ============================================================
# SERVER START (with a lightweight HTTP health-check response so
# hosting platforms like Render can ping "/" without the socket
# handshake failing and triggering unnecessary restarts)
# ============================================================

async def health_check(path, request_headers):
    if request_headers.get("Upgrade", "").lower() == "websocket":
        return None
    return (200, [("Content-Type", "text/plain")], b"OK")


async def main():
    port = int(os.environ.get("PORT", 8000))

    async with websockets.serve(
        handler,
        "0.0.0.0",
        port,
        process_request=health_check
    ):
        print(f"[+] WEB SOCKET SERVER RUNNING ON PORT {port}!")
        await asyncio.Future()


# ============================================================
# PER-CONNECTION HELPERS
# ============================================================

async def attach_socket_to_room(websocket, room_id):
    """Add this socket to a room's live connection set, cancel any pending
    expiry, and let both members know presence may have changed."""
    if room_id not in ROOM_SOCKETS:
        ROOM_SOCKETS[room_id] = set()

    ROOM_SOCKETS[room_id].add(websocket)
    cancel_room_expiry(room_id)
    await broadcast_presence(room_id)


async def build_room_payloads(username, websocket):
    """Called right after LOGIN / RESTORE_SESSION succeeds: reconnects this
    socket to every room the user is a member of and returns each room's
    history + presence so the frontend can rebuild the whole sidebar."""
    payloads = []

    for room_id in get_user_rooms(username):
        if not room_exists(room_id):
            # This room fully expired while the user was away — drop the
            # stale membership so it stops showing up in their sidebar.
            remove_membership(username, room_id)
            continue

        if room_id not in ROOM_SOCKETS:
            ROOM_SOCKETS[room_id] = set()

        ROOM_SOCKETS[room_id].add(websocket)
        cancel_room_expiry(room_id)

        payloads.append({
            "room_id": room_id,
            "history": get_chat_history(room_id),
            "online": room_is_online(room_id)
        })

    for p in payloads:
        await broadcast_presence(p["room_id"])

    return payloads


async def detach_socket_from_all_rooms(websocket):
    """Called on disconnect: remove this socket from every room it was
    attached to (membership in the database is untouched, so the rooms
    remain in the user's sidebar for next time)."""
    affected = []

    for room_id, sockets in list(ROOM_SOCKETS.items()):
        if websocket in sockets:
            sockets.discard(websocket)
            affected.append(room_id)

            if not sockets:
                start_room_expiry(room_id)

    SOCKET_USER.pop(websocket, None)

    for room_id in affected:
        await broadcast_presence(room_id)


# ============================================================
# HANDLER
# ============================================================

async def handler(websocket):

    current_user = None
    current_session_token = None

    try:

        async for message in websocket:

            try:
                data = json.loads(message)
            except Exception:
                continue

            action = data.get("type")


            # ==================================================
            # 1. LOGIN
            # ==================================================

            if action == "LOGIN":

                user = str(data.get("username", "")).strip()
                pwd = str(data.get("password", ""))

                if verify_user(user, pwd):

                    session_token = secrets.token_urlsafe(32)

                    SESSIONS[session_token] = {
                        "username": user,
                        "websocket": websocket
                    }

                    current_user = user
                    current_session_token = session_token
                    SOCKET_USER[websocket] = user

                    rooms_payload = await build_room_payloads(user, websocket)

                    await websocket.send(
                        json.dumps({
                            "status": "SUCCESS",
                            "type": "LOGIN_RES",
                            "user": user,
                            "session_token": session_token,
                            "rooms": rooms_payload
                        })
                    )

                    print(f"[+] {user} logged in.")

                else:

                    await websocket.send(
                        json.dumps({
                            "status": "FAILED",
                            "type": "LOGIN_RES"
                        })
                    )


            # ==================================================
            # 2. RESTORE SESSION
            # ==================================================

            elif action == "RESTORE_SESSION":

                session_token = data.get("session_token")
                session = SESSIONS.get(session_token)

                if session:

                    user = session["username"]
                    current_user = user
                    current_session_token = session_token

                    old_websocket = session.get("websocket")

                    if old_websocket and old_websocket != websocket:
                        # A newer connection is taking over this session;
                        # detach the stale one from every room it was in.
                        await detach_socket_from_all_rooms(old_websocket)

                    session["websocket"] = websocket
                    SOCKET_USER[websocket] = user

                    rooms_payload = await build_room_payloads(user, websocket)

                    await websocket.send(
                        json.dumps({
                            "type": "SESSION_RESTORED",
                            "status": "SUCCESS",
                            "user": user,
                            "rooms": rooms_payload
                        })
                    )

                    print(f"[+] Session restored: {current_user}")

                else:

                    await websocket.send(
                        json.dumps({
                            "type": "SESSION_RESTORED",
                            "status": "FAILED"
                        })
                    )


            # ==================================================
            # 3. CREATE ROOM
            # ==================================================

            elif action == "CREATE_ROOM":

                if not current_user:
                    await websocket.send(json.dumps({"type": "AUTH_REQUIRED"}))
                    continue

                room_id = generate_room_id()
                add_membership(current_user, room_id)
                await attach_socket_to_room(websocket, room_id)

                await websocket.send(
                    json.dumps({
                        "type": "ROOM_CREATED",
                        "room_id": room_id,
                        "history": []
                    })
                )

                print(f"[+] Room {room_id} created by {current_user}")


            # ==================================================
            # 4. JOIN ROOM
            # ==================================================

            elif action == "JOIN_ROOM":

                if not current_user:
                    await websocket.send(json.dumps({"type": "AUTH_REQUIRED"}))
                    continue

                room_id = str(data.get("room_id", "")).strip()

                if not room_id or not room_exists(room_id):
                    await websocket.send(json.dumps({"type": "ROOM_NOT_FOUND"}))
                    continue

                members = get_room_members(room_id)
                already_member = current_user in members

                if not already_member and len(members) >= MAX_ROOM_USERS:
                    await websocket.send(json.dumps({"type": "ROOM_FULL"}))
                    print(f"[!] {current_user} could not join {room_id}: room full.")
                    continue

                if not already_member:
                    add_membership(current_user, room_id)

                await attach_socket_to_room(websocket, room_id)

                await websocket.send(
                    json.dumps({
                        "type": "JOIN_SUCCESS",
                        "room_id": room_id,
                        "history": get_chat_history(room_id),
                        "online": room_is_online(room_id)
                    })
                )

                print(f"[+] {current_user} joined room {room_id}")


            # ==================================================
            # 5. EXIT ROOM  (leaves the room entirely — frees the slot)
            # ==================================================

            elif action == "EXIT_ROOM":

                if not current_user:
                    await websocket.send(json.dumps({"type": "AUTH_REQUIRED"}))
                    continue

                room_id = str(data.get("room_id", "")).strip()
                members = get_room_members(room_id)

                if current_user not in members:
                    await websocket.send(json.dumps({
                        "type": "NOT_IN_ROOM",
                        "room_id": room_id
                    }))
                    continue

                remove_membership(current_user, room_id)

                if room_id in ROOM_SOCKETS:
                    ROOM_SOCKETS[room_id].discard(websocket)

                remaining_members = get_room_members(room_id)

                if not remaining_members:
                    cancel_room_expiry(room_id)
                    remove_room_completely(room_id)
                    remove_room(room_id)
                    ROOM_SOCKETS.pop(room_id, None)
                else:
                    if not ROOM_SOCKETS.get(room_id):
                        start_room_expiry(room_id)
                    await broadcast_presence(room_id)

                await websocket.send(json.dumps({
                    "type": "ROOM_EXITED",
                    "room_id": room_id
                }))

                print(f"[-] {current_user} exited room {room_id}")


            # ==================================================
            # 6. SEND MESSAGE
            # ==================================================

            elif action == "SEND_MSG":

                room_id = str(data.get("room_id", "")).strip()

                if not current_user or not room_id:
                    await websocket.send(json.dumps({
                        "type": "MESSAGE_FAILED",
                        "room_id": room_id
                    }))
                    continue

                msg = str(data.get("message", "")).strip()

                if not msg:
                    continue

                members = get_room_members(room_id)

                if current_user not in members:
                    await websocket.send(json.dumps({
                        "type": "MESSAGE_FAILED",
                        "room_id": room_id
                    }))
                    continue

                timestamp = save_message(room_id, current_user, msg)

                broadcast_data = json.dumps({
                    "type": "NEW_MSG",
                    "room_id": room_id,
                    "sender": current_user,
                    "message": msg,
                    "timestamp": timestamp
                })

                for conn in list(ROOM_SOCKETS.get(room_id, set())):
                    try:
                        await conn.send(broadcast_data)
                    except Exception:
                        pass


            # ==================================================
            # 7. LOGOUT
            # ==================================================

            elif action == "LOGOUT":

                if current_session_token:
                    SESSIONS.pop(current_session_token, None)

                await detach_socket_from_all_rooms(websocket)

                current_user = None
                current_session_token = None

                await websocket.send(json.dumps({"type": "LOGOUT_SUCCESS"}))


    except Exception as e:

        print(f"[!] Connection error: {e}")


    finally:

        await detach_socket_from_all_rooms(websocket)

        if current_session_token in SESSIONS:
            SESSIONS[current_session_token]["websocket"] = None

        print(f"[-] {current_user} WebSocket disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
