import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path


class APIKeyManager:
    """Manage multiple API keys with rotation and usage tracking"""

    def __init__(self, usage_file="api_usage.json", threshold=9):
        self.usage_file = Path(usage_file)
        self.threshold = threshold  # Max requests before rotation
        self.keys = self.load_keys()
        self.usage_data = self.load_usage()
        self.current_index = self.usage_data.get("current_key_index", 0)

        # Thread safety for concurrent processing
        self.lock = threading.Lock()

    def load_keys(self):
        """Load all numbered API keys from environment"""
        keys = []
        i = 1

        while True:
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1

        if not keys:
            raise ValueError(
                "No API keys found! Please set GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc. in .env file"
            )

        print(f"📊 Loaded {len(keys)} API keys")
        return keys

    def load_usage(self):
        """Load usage data from JSON file"""
        if not self.usage_file.exists():
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "keys": {},
                "current_key_index": 0,
            }

        with open(self.usage_file, "r") as f:
            data = json.load(f)

        # Reset if new day
        today = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today:
            print(f"🔄 New day detected, resetting usage counters")
            data = {"date": today, "keys": {}, "current_key_index": 0}

        return data

    def save_usage(self):
        """Persist usage data to JSON file"""
        with open(self.usage_file, "w") as f:
            json.dump(self.usage_data, f, indent=2)

    def hash_key(self, key):
        """Generate short hash for key identification"""
        return hashlib.sha256(key.encode()).hexdigest()[:8]

    def get_active_key(self):
        """Return current active API key"""
        return self.keys[self.current_index]

    def get_key_usage(self, key):
        """Get usage count for a key"""
        key_hash = self.hash_key(key)
        return self.usage_data["keys"].get(key_hash, {}).get("requests", 0)

    def is_key_exhausted(self, key):
        """Check if key has reached threshold"""
        return self.get_key_usage(key) >= self.threshold

    def log_request(self, key, success=True, error=None):
        """log API request for a key (thread-safe)"""
        with self.lock:
            key_hash = self.hash_key(key)

            if key_hash not in self.usage_data["keys"]:
                self.usage_data["keys"][key_hash] = {
                    "requests": 0,
                    "last_error": None,
                    "last_used": None,
                }

            self.usage_data["keys"][key_hash]["requests"] += 1
            self.usage_data["keys"][key_hash]["last_used"] = datetime.now().isoformat()

            if error:
                self.usage_data["keys"][key_hash]["last_error"] = datetime.now().isoformat()

            self.save_usage()

    def rotate_key(self):
        """Switch to next available key (thread-safe)"""
        with self.lock:
            original_index = self.current_index
            attempts = 0

            while attempts < len(self.keys):
                self.current_index = (self.current_index + 1) % len(self.keys)
                current_key = self.keys[self.current_index]

                if not self.is_key_exhausted(current_key):
                    key_hash = self.hash_key(current_key)
                    usage = self.get_key_usage(current_key)
                    print(
                        f"🔄 Rotated to Key #{self.current_index + 1} ({key_hash}): {usage}/{self.threshold + 1} requests"
                    )

                    self.usage_data["current_key_index"] = self.current_index
                    self.save_usage()
                    return True

                attempts += 1

            # All keys exhausted
            print("❌ All API keys exhausted! Please wait for quota reset.")
            return False

    def get_key_for_chunk(self, chunk_id):
        """
        Round-robin key assignment for concurrent processing (thread-safe)
        Improved logic: Distributes load evenly among ALL available keys.

        Args:
            chunk_id: Chunk index (0-based)

        Returns:
            API key string

        Raises:
            Exception: If all keys are exhausted
        """
        with self.lock:
            # 1. Identify all available (non-exhausted) keys
            available_keys = []
            for i, key in enumerate(self.keys):
                if not self.is_key_exhausted(key):
                    available_keys.append((i, key))

            if not available_keys:
                raise Exception("All API keys exhausted!")

            # 2. Distribute chunks evenly among AVAILABLE keys
            # This prevents the "bottleneck effect" where all chunks flock to the single next available key
            target_index = chunk_id % len(available_keys)
            key_index, assigned_key = available_keys[target_index]
            
            key_hash = self.hash_key(assigned_key)
            usage = self.get_key_usage(assigned_key)
            
            # Only log if we are doing a re-assignment (i.e., the "natural" key was exhausted)
            # Or just always log for clarity in debug mode? Let's keep it clean but informative.
            # The caller prints the chunk start, but we can print a subtle info if it's a "smart" assignment.
            
            # Check if this was the "natural" assignment
            natural_index = chunk_id % len(self.keys)
            if key_index != natural_index:
                 print(
                    f"   twisted_rightwards_arrows Chunk {chunk_id + 1}: Re-routed to Key #{key_index + 1} ({key_hash}): {usage}/{self.threshold + 1} requests"
                )
            else:
                 print(
                    f"   🔑 Chunk {chunk_id + 1}: Using Key #{key_index + 1} ({key_hash}): {usage}/{self.threshold + 1} requests"
                )

            return assigned_key

    def print_usage_stats(self):
        """Display current usage statistics"""
        print(f"\n📊 API Key Usage Today ({self.usage_data['date']}):")

        for i, key in enumerate(self.keys):
            key_hash = self.hash_key(key)
            usage = self.get_key_usage(key)
            is_active = i == self.current_index
            active_marker = "← ACTIVE" if is_active else ""

            status = "✅" if usage < self.threshold else "⚠️"
            print(
                f"  {status} Key #{i + 1} ({key_hash}): {usage}/10 requests {active_marker}"
            )
