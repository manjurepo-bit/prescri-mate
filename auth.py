import bcrypt
from database import get_user_by_username, create_user

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def authenticate_user(username, password):
    """Authenticate user and return user info or None."""
    if not username or not password:
        return None
    user = get_user_by_username(username)
    if user and verify_password(password, user['password_hash']):
        return user
    return None

def register_user(username, password):
    """Register a new user if username doesn't already exist."""
    if not username or not password:
        return False, "Username and password cannot be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
        
    existing = get_user_by_username(username)
    if existing:
        return False, "Username already exists."
    
    hashed = hash_password(password)
    try:
        user_id = create_user(username, hashed)
        return True, user_id
    except Exception as e:
        return False, f"Failed to create user record: {str(e)}"
