from database import verify_user, register_user

def handle_auth(data):
    try:
        parts = data.split(":")
        action = parts[0]
        
        if action == "LOGIN" and len(parts) == 3:
            username, password = parts[1], parts[2]
            return "SUCCESS" if verify_user(username, password) else "FAILED"
            
        elif action == "REGISTER" and len(parts) == 3:
            username, password = parts[1], parts[2]
            return "REG_SUCCESS" if register_user(username, password) else "REG_EXISTS"
            
        return "INVALID_FORMAT"
    except Exception:
        return "ERROR"
