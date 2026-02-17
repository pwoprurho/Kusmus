import os
import itertools
from dotenv import load_dotenv

# Ensure env vars are loaded
load_dotenv()

class KeyManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KeyManager, cls).__new__(cls)
            cls._instance.keys = cls._instance._load_keys()
            cls._instance.key_cycle = itertools.cycle(cls._instance.keys) if cls._instance.keys else None
            cls._instance.current_key = next(cls._instance.key_cycle) if cls._instance.key_cycle else None
        return cls._instance

    def _load_keys(self):
        """Loads all GEMINI_KEY_* from environment variables."""
        keys = []
        # Check standard GEMINI_API_KEY first
        main_key = os.getenv('GEMINI_API_KEY')
        if main_key:
            keys.append(main_key)
            
        # Check numbered keys
        for i in range(20): # Check up to 20 keys
            key = os.getenv(f'GEMINI_KEY_{i}')
            if key:
                keys.append(key)
        
        # Remove duplicates and empty strings
        unique_keys = list(set([k for k in keys if k and "placeholder" not in k]))
        print(f"KeyManager loaded {len(unique_keys)} unique API keys.")
        return unique_keys

    def get_current_key(self):
        """Returns the currently active key."""
        return self.current_key

    def rotate_key(self):
        """Switches to the next available key."""
        if self.key_cycle:
            self.current_key = next(self.key_cycle)
            print(f"KeyManager: Rotated to next API key (ending in ...{self.current_key[-4:]})")
            return self.current_key
        return None

# Global instance
key_manager = KeyManager()
