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
    delete_chat_history
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

# { room_id: set(websocket_connections) }
ROOMS = {}

# { room_id: asyncio.Task }
ROOM_EXPIRY_TASKS = {}

# { session_token: session_data }
#
# session_data:
# {
#     "username": username,
#     "room_id": room_id,
#     "websocket": websocket or None
# }
SESSIONS = {}


# 12 minutes
ROOM_IDLE_TIMEOUT = 12 * 60


# ============================================================
# ROOM EXPIRY
# ============================================================

async def expire_room(room_id):

    try:
        await asyncio.sleep(ROOM_IDLE_TIMEOUT)

        # Room abhi bhi empty hai?
        if room_id in ROOMS and not ROOMS[room_id]:

            # Chat history delete
            delete_chat_history(room_id)

            # Room active list se remove
            remove_room(room_id)

            # Server memory se remove
            del ROOMS[room_id]

            # Expired room se associated sessions ka room clear
            for session in SESSIONS.values():
                if session["room_id"] == room_id:
                    session["room_id"] = None

            print(f"[-] Room {room_id} expired after 12 minutes.")

    except asyncio.CancelledError:
        pass

    finally:
        ROOM_EXPIRY_TASKS.pop(room_id, None)


def start_room_expiry(room_id):

    old_task = ROOM_EXPIRY_TASKS.get(room_id)

    if old_task and not old_task.done():
        old_task.cancel()

    ROOM_EXPIRY_TASKS[room_id] = asyncio.create_task(
        expire_room(room_id)
    )


def cancel_room_expiry(room_id):

    task = ROOM_EXPIRY_TASKS.pop(room_id, None)

    if task and not task.done():
        task.cancel()


# ============================================================
# ROOM CONNECTION MANAGEMENT
# ============================================================

def remove_connection_from_room(websocket, room_id):

    if room_id not in ROOMS:
        return

    ROOMS[room_id].discard(websocket)

    # Room empty ho gaya
    if not ROOMS[room_id]:
        start_room_expiry(room_id)


# ============================================================
# HANDLER
# ============================================================

async def handler(websocket):

    current_room = None
    current_user = None
    current_session_token = None

    try:

        async for message in websocket:

            data = json.loads(message)
            action = data.get("type")


            # ==================================================
            # 1. LOGIN
            # ==================================================

            if action == "LOGIN":

                user = data.get("username", "").strip()
                pwd = data.get("password", "")

                if verify_user(user, pwd):

                    # New secure session token
                    session_token = secrets.token_urlsafe(32)

                    SESSIONS[session_token] = {
                        "username": user,
                        "room_id": None,
                        "websocket": websocket
                    }

                    current_user = user
                    current_session_token = session_token

                    await websocket.send(
                        json.dumps({
                            "status": "SUCCESS",
                            "type": "LOGIN_RES",
                            "user": user,
                            "session_token": session_token
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

                    # Same session ko new WebSocket se bind karo
                    current_user = session["username"]
                    current_session_token = session_token

                    old_websocket = session.get("websocket")

                    session["websocket"] = websocket

                    # Agar old socket alag tha, usse room se remove
                    if old_websocket and old_websocket != websocket:

                        old_room = session.get("room_id")

                        if old_room:
                            remove_connection_from_room(
                                old_websocket,
                                old_room
                            )


                    current_room = session.get("room_id")

                    # Agar room abhi bhi valid hai
                    if current_room and room_exists(current_room):

                        cancel_room_expiry(current_room)

                        if current_room not in ROOMS:
                            ROOMS[current_room] = set()

                        ROOMS[current_room].add(websocket)

                        history = get_chat_history(current_room)

                        await websocket.send(
                            json.dumps({
                                "type": "SESSION_RESTORED",
                                "status": "SUCCESS",
                                "user": current_user,
                                "room_id": current_room,
                                "history": history
                            })
                        )

                        print(
                            f"[+] Session restored: "
                            f"{current_user} -> room {current_room}"
                        )

                    else:

                        current_room = None
                        session["room_id"] = None

                        await websocket.send(
                            json.dumps({
                                "type": "SESSION_RESTORED",
                                "status": "SUCCESS",
                                "user": current_user,
                                "room_id": None
                            })
                        )

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

                    await websocket.send(
                        json.dumps({
                            "type": "AUTH_REQUIRED"
                        })
                    )

                    continue


                # Existing room se remove
                if current_room:

                    remove_connection_from_room(
                        websocket,
                        current_room
                    )

                    current_room = None


                # New 6-digit room
                room_id = generate_room_id()

                ROOMS[room_id] = {websocket}

                current_room = room_id

                # Session mein room save
                if current_session_token in SESSIONS:
                    SESSIONS[current_session_token]["room_id"] = room_id

                cancel_room_expiry(room_id)

                await websocket.send(
                    json.dumps({
                        "type": "ROOM_CREATED",
                        "room_id": room_id
                    })
                )

                print(
                    f"[+] Room {room_id} created by {current_user}"
                )


            # ==================================================
            # 4. JOIN ROOM
            # ==================================================

            elif action == "JOIN_ROOM":

                if not current_user:

                    await websocket.send(
                        json.dumps({
                            "type": "AUTH_REQUIRED"
                        })
                    )

                    continue


                room_id = str(
                    data.get("room_id", "")
                ).strip()


                if room_exists(room_id):

                    # Previous room se remove
                    if current_room and current_room != room_id:

                        remove_connection_from_room(
                            websocket,
                            current_room
                        )


                    if room_id not in ROOMS:
                        ROOMS[room_id] = set()


                    # Expiry cancel
                    cancel_room_expiry(room_id)

                    # Add user
                    ROOMS[room_id].add(websocket)

                    current_room = room_id

                    # Session mein room save
                    if current_session_token in SESSIONS:
                        SESSIONS[current_session_token]["room_id"] = room_id

                    history = get_chat_history(room_id)

                    await websocket.send(
                        json.dumps({
                            "type": "JOIN_SUCCESS",
                            "room_id": room_id,
                            "history": history
                        })
                    )

                    print(
                        f"[+] {current_user} joined room {room_id}"
                    )

                else:

                    await websocket.send(
                        json.dumps({
                            "type": "ROOM_NOT_FOUND"
                        })
                    )


            # ==================================================
            # 5. EXIT ROOM
            # ==================================================

            elif action == "EXIT_ROOM":

                if current_room:

                    room_id = current_room

                    remove_connection_from_room(
                        websocket,
                        room_id
                    )

                    current_room = None

                    if current_session_token in SESSIONS:
                        SESSIONS[current_session_token]["room_id"] = None

                    await websocket.send(
                        json.dumps({
                            "type": "ROOM_EXITED"
                        })
                    )

                    print(
                        f"[-] {current_user} exited room {room_id}"
                    )

                else:

                    await websocket.send(
                        json.dumps({
                            "type": "NOT_IN_ROOM"
                        })
                    )


            # ==================================================
            # 6. SEND MESSAGE
            # ==================================================

            elif action == "SEND_MSG":

                if not current_user or not current_room:

                    await websocket.send(
                        json.dumps({
                            "type": "MESSAGE_FAILED"
                        })
                    )

                    continue


                msg = str(
                    data.get("message", "")
                ).strip()


                if not msg:
                    continue


                save_message(
                    current_room,
                    current_user,
                    msg
                )


                broadcast_data = json.dumps({
                    "type": "NEW_MSG",
                    "sender": current_user,
                    "message": msg
                })


                if current_room in ROOMS:

                    for conn in list(ROOMS[current_room]):

                        try:
                            await conn.send(
                                broadcast_data
                            )

                        except Exception:
                            pass


            # ==================================================
            # 7. LOGOUT
            # ==================================================

            elif action == "LOGOUT":

                if current_session_token:

                    session = SESSIONS.get(
                        current_session_token
                    )

                    if session:

                        room_id = session.get("room_id")

                        if room_id:
                            remove_connection_from_room(
                                websocket,
                                room_id
                            )

                        del SESSIONS[
                            current_session_token
                        ]


                current_user = None
                current_room = None
                current_session_token = None

                await websocket.send(
                    json.dumps({
                        "type": "LOGOUT_SUCCESS"
                    })
                )


    except Exception as e:

        print(f"[!] Connection error: {e}")


    finally:

        # Disconnect par room se remove
        if current_room:

            remove_connection_from_room(
                websocket,
                current_room
            )

        # Session ko destroy nahi karna.
        # Refresh ke liye token valid rahega.
        if current_session_token in SESSIONS:

            SESSIONS[
                current_session_token
            ]["websocket"] = None

        print(
            f"[-] {current_user} WebSocket disconnected."
        )


# ============================================================
# SERVER START
# ============================================================

async def main():

    port = int(
        os.environ.get("PORT", 8000)
    )

    async with websockets.serve(
        handler,
        "0.0.0.0",
        port
    ):

        print(
            f"[+] WEB SOCKET SERVER RUNNING ON PORT {port}!"
        )

        await asyncio.Future()


if __name__ == "__main__":

    asyncio.run(main())
