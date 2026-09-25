import asyncio
import os
import json
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


# Connected clients map:
# { room_id: set(websocket_connections) }
ROOMS = {}


# Room expiry tasks:
# { room_id: asyncio.Task }
ROOM_EXPIRY_TASKS = {}


# 12 minutes = 720 seconds
ROOM_IDLE_TIMEOUT = 12 * 60


async def expire_room(room_id):
    """
    Room empty hone ke baad 12 minutes wait karega.
    Agar is duration mein koi user wapas nahi aaya,
    to room aur uski chat history delete ho jayegi.
    """

    try:
        await asyncio.sleep(ROOM_IDLE_TIMEOUT)

        # Check karo ki room abhi bhi empty hai
        if room_id in ROOMS and not ROOMS[room_id]:

            # Room ki chat history delete
            delete_chat_history(room_id)

            # Room active list se remove
            remove_room(room_id)

            # Server memory se room remove
            del ROOMS[room_id]

            print(f"[-] Room {room_id} expired after 12 minutes.")

    except asyncio.CancelledError:
        # User room mein wapas aa gaya
        pass

    finally:
        ROOM_EXPIRY_TASKS.pop(room_id, None)


def start_room_expiry(room_id):
    """
    Empty room ke liye 12-minute expiry timer start karta hai.
    """

    # Agar pehle se timer hai to cancel karo
    old_task = ROOM_EXPIRY_TASKS.get(room_id)

    if old_task and not old_task.done():
        old_task.cancel()

    ROOM_EXPIRY_TASKS[room_id] = asyncio.create_task(
        expire_room(room_id)
    )


def cancel_room_expiry(room_id):
    """
    User room mein wapas aane par expiry timer cancel karta hai.
    """

    task = ROOM_EXPIRY_TASKS.pop(room_id, None)

    if task and not task.done():
        task.cancel()


def remove_connection_from_room(websocket, room_id):
    """
    WebSocket ko room se safely remove karta hai.
    """

    if room_id not in ROOMS:
        return

    ROOMS[room_id].discard(websocket)

    # Agar room completely empty ho gaya
    if not ROOMS[room_id]:
        start_room_expiry(room_id)


async def handler(websocket):

    current_room = None
    current_user = None

    try:

        async for message in websocket:

            data = json.loads(message)
            action = data.get("type")


            # ==================================================
            # 1. LOGIN
            # ==================================================

            if action == "LOGIN":

                user = data.get("username")
                pwd = data.get("password")

                if verify_user(user, pwd):

                    current_user = user

                    await websocket.send(
                        json.dumps({
                            "status": "SUCCESS",
                            "type": "LOGIN_RES",
                            "user": user
                        })
                    )

                else:

                    await websocket.send(
                        json.dumps({
                            "status": "FAILED",
                            "type": "LOGIN_RES"
                        })
                    )


            # ==================================================
            # 2. CREATE ROOM
            # ==================================================

            elif action == "CREATE_ROOM":

                # Login required
                if not current_user:

                    await websocket.send(
                        json.dumps({
                            "type": "AUTH_REQUIRED"
                        })
                    )

                    continue


                # Agar user already kisi room mein hai,
                # pehle us room se remove karo
                if current_room:

                    remove_connection_from_room(
                        websocket,
                        current_room
                    )

                    current_room = None


                # New unique 6-digit numeric room
                room_id = generate_room_id()


                # Room create
                ROOMS[room_id] = {websocket}


                # Current user ko room assign
                current_room = room_id


                # Safety: agar expiry task tha to cancel
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
            # 3. JOIN ROOM
            # ==================================================

            elif action == "JOIN_ROOM":

                # Login required
                if not current_user:

                    await websocket.send(
                        json.dumps({
                            "type": "AUTH_REQUIRED"
                        })
                    )

                    continue


                room_id = str(data.get("room_id", "")).strip()


                # Room check
                if room_exists(room_id):


                    # Agar user kisi doosre room mein hai,
                    # pehle usse leave karo
                    if current_room and current_room != room_id:

                        remove_connection_from_room(
                            websocket,
                            current_room
                        )

                        current_room = None


                    # Agar room server memory mein nahi hai
                    # to empty room set create karo
                    if room_id not in ROOMS:

                        ROOMS[room_id] = set()


                    # Expiry timer cancel
                    cancel_room_expiry(room_id)


                    # User ko room mein add
                    ROOMS[room_id].add(websocket)


                    # Current room update
                    current_room = room_id


                    # Previous chat history
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
            # 4. EXIT ROOM
            # ==================================================

            elif action == "EXIT_ROOM":

                if current_room:

                    room_id = current_room


                    remove_connection_from_room(
                        websocket,
                        room_id
                    )


                    current_room = None


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
            # 5. SEND MESSAGE
            # ==================================================

            elif action == "SEND_MSG":

                # Login + room required
                if not current_user or not current_room:

                    await websocket.send(
                        json.dumps({
                            "type": "MESSAGE_FAILED"
                        })
                    )

                    continue


                msg = str(data.get("message", "")).strip()


                # Empty message ignore
                if not msg:
                    continue


                # Save message
                save_message(
                    current_room,
                    current_user,
                    msg
                )


                # Broadcast message
                broadcast_data = json.dumps({
                    "type": "NEW_MSG",
                    "sender": current_user,
                    "message": msg
                })


                if current_room in ROOMS:

                    # list() use kar rahe hain taaki
                    # set change hone par error na aaye
                    for conn in list(ROOMS[current_room]):

                        try:

                            await conn.send(
                                broadcast_data
                            )

                        except Exception:

                            pass


    except Exception as e:

        print(
            f"[!] Connection error: {e}"
        )


    finally:

        # Disconnect hone par user ko room se remove karo
        if current_room:

            remove_connection_from_room(
                websocket,
                current_room
            )


            print(
                f"[-] {current_user} disconnected from room {current_room}"
            )


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
