# backend/src/api_clients/key_manager.py

import os

class KeyManager:
    """
    Manages a pool of API keys for a specific service.
    It finds all keys matching a prefix (e.g., 'ALPHA_VANTAGE_API_KEY_')
    and allows rotating through them.
    """
    def __init__(self, key_prefix):
        self.keys = self._load_keys(key_prefix)
        self.current_key_index = 0
        if not self.keys:
            raise ValueError(f"No API keys found with prefix '{key_prefix}' in .env file.")

    def _load_keys(self, prefix):
        """Loads keys from environment variables that start with the given prefix."""
        found_keys = []
        for key, value in os.environ.items():
            if key.startswith(prefix):
                found_keys.append(value)
        print(f"Found {len(found_keys)} keys for prefix '{prefix}'.")
        return found_keys

    def get_current_key(self):
        """Returns the currently active API key."""
        return self.keys[self.current_key_index]

    def rotate_key(self):
        """
        Moves to the next key in the pool. Returns the new key.
        If it reaches the end, it circles back to the start.
        """
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        print(f"Rotated to new key (index {self.current_key_index}).")
        return self.get_current_key()