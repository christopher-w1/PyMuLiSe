import os, json, hashlib, uuid, time, asyncio

class UserService:
    def __init__(self, users_file="data/users.json", registration_key="SUPER_SECRET_KEY"):
        self.users_file = users_file
        self.registration_key = registration_key
        self.lock = asyncio.Lock()
        self.sessions = {}
        self.users = {}
        self._load_users()

    def _load_users(self):
        if os.path.exists(self.users_file):
            with open(self.users_file, "r") as f:
                self.users = json.load(f)
        else:
            self.users = {}

    async def _save_users(self):
        async with self.lock:
            tmp_file = self.users_file + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(self.users, f, indent=2)
            os.replace(tmp_file, self.users_file)

    @staticmethod
    def _hash_password(password, salt=None):
        import os
        if salt is None:
            salt = os.urandom(16).hex()
        hashed = hashlib.sha256((salt + password).encode()).hexdigest()
        return hashed, salt

    async def register(self, registration_key, email, username, password, lastfm_user=None):
        if registration_key != self.registration_key:
            raise ValueError("Invalid registration key")
        if not email or not username or not password:
            raise ValueError("Missing required fields")

        async with self.lock:
            if email in self.users:
                raise ValueError("Email already registered")

            hashed_pw, salt = self._hash_password(password)
            self.users[email] = {
                "username": username,
                "password_hash": hashed_pw,
                "salt": salt,
                "lastfm_user": lastfm_user,
                "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            await self._save_users()

    async def login(self, email, password):
        user = self.users.get(email)
        if not user:
            raise ValueError("Invalid credentials")

        hashed_pw, _ = self._hash_password(password, user["salt"])
        if hashed_pw != user["password_hash"]:
            raise ValueError("Invalid credentials")

        session_key = uuid.uuid4().hex
        self.sessions[session_key] = {"email": email, "created": time.time()}
        return user["username"], session_key

    async def get_user_email_by_session(self, session_key):
        session = self.sessions.get(session_key)
        if not session:
            return None
        return self.users.get(session["email"])
