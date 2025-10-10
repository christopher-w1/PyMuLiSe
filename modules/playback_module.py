class PlaybackModule:
    class PlaybackChannel:
        def __init__(self, channel_id: str, owner_id: str):
            self.channel_id = channel_id
            self.current_song = None
            self.is_playing = False
            self.position = 0  # in milliseconds
            self.listeners = {}  # user_id -> last_active_timestamp
            self.finished_listeners = set()
            self.owner_id = owner_id  # user_id of the owner

        def poll_by_user(self, user_id: str, playback_position: int):
            self.listeners[user_id] = time.time()
            self.remove_inactive_listeners

        def add_listener(self, user_id: str):
            self.listeners[user_id] = time.time()

        def remove_listener(self, user_id: str):
            self.listeners.pop(user_id, None)

        def remove_inactive_listeners(self):
            inactive_users = [
                user_id for user_id, last_active in self.listeners.items()
                if time.time() - last_active > 1  # 10 seconds timeout
            ]
            for user_id in inactive_users:
                self.remove_listener(user_id)
