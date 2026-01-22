"""
key_rotation_manager.py - Queue-based API Key Rotation with Cooldown

Features:
- Queue-based key rotation
- Cooldown mechanism (30s)
- Thread-safe for concurrent processing
- Auto-refresh cooldown keys
- Remove quota-exhausted keys
"""

import time
from queue import Queue
from threading import Lock
from typing import List, Optional


class KeyRotationManager:
    """
    Quản lý rotation API keys với cooldown mechanism

    Workflow:
    1. Keys xếp hàng trong available_queue
    2. Khi key fail → cooldown_dict (30s)
    3. Keys hết cooldown tự động quay về available_queue
    4. Quota exhausted keys bị remove hẳn
    """

    def __init__(self, api_keys: List[str]):
        """
        Args:
            api_keys: List các API keys
        """
        self.available_queue = Queue()
        self.cooldown_dict = {}  # {key: cooldown_until_timestamp}
        self.removed_keys = set()  # Keys đã bị remove (quota exhausted)
        self.lock = Lock()

        # Initialize: All keys vào available queue
        for key in api_keys:
            self.available_queue.put(key)

    def get_next_key(self) -> Optional[str]:
        """
        Lấy key tiếp theo từ available queue

        Returns:
            API key string, hoặc None nếu tất cả keys đều cooldown
        """
        with self.lock:
            # Refresh cooldown keys trước
            self._refresh_cooldown_keys()

            # Lấy key từ queue
            if not self.available_queue.empty():
                return self.available_queue.get()

            # Edge case: Tất cả keys cooldown
            # → Tìm key có cooldown time ngắn nhất
            return self._wait_for_shortest_cooldown()

    def mark_key_failed(self, key: str, cooldown_seconds: int = 30):
        """
        Đánh dấu key failed, đưa vào cooldown

        Args:
            key: API key bị fail
            cooldown_seconds: Thời gian cooldown (default 30s)
        """
        with self.lock:
            if key in self.removed_keys:
                return  # Key đã bị remove, skip

            cooldown_until = time.time() + cooldown_seconds
            self.cooldown_dict[key] = cooldown_until

    def remove_key(self, key: str):
        """
        Remove key vĩnh viễn (quota exhausted)

        Args:
            key: API key cần remove
        """
        with self.lock:
            self.removed_keys.add(key)

            # Remove khỏi cooldown dict nếu có
            if key in self.cooldown_dict:
                del self.cooldown_dict[key]

    def return_key(self, key: str):
        """
        Trả key về available queue (khi success)

        Args:
            key: API key cần return
        """
        with self.lock:
            if key in self.removed_keys:
                return  # Key đã bị remove, không return

            self.available_queue.put(key)

    def _refresh_cooldown_keys(self):
        """
        Internal: Move keys hết cooldown về available queue
        """
        current_time = time.time()
        keys_to_restore = []

        # Tìm keys hết cooldown
        for key, cooldown_until in list(self.cooldown_dict.items()):
            if current_time >= cooldown_until:
                keys_to_restore.append(key)

        # Move về available
        for key in keys_to_restore:
            del self.cooldown_dict[key]
            self.available_queue.put(key)

    def _wait_for_shortest_cooldown(self) -> Optional[str]:
        """
        Internal: Wait cho key có cooldown ngắn nhất

        Returns:
            Key sau khi wait, hoặc None nếu không còn key nào
        """
        if not self.cooldown_dict:
            # Không còn key nào (tất cả bị remove)
            return None

        # Tìm key có cooldown time ngắn nhất
        current_time = time.time()
        shortest_key = min(
            self.cooldown_dict.items(), key=lambda x: x[1]  # Sort by cooldown_until
        )

        key, cooldown_until = shortest_key
        wait_time = max(0, cooldown_until - current_time)

        if wait_time > 0:
            print(
                f"⏳ All keys in cooldown, waiting {wait_time:.1f}s for next available key..."
            )
            time.sleep(wait_time)

        # Move key về available
        del self.cooldown_dict[key]
        return key

    def get_stats(self) -> dict:
        """
        Get statistics về key rotation

        Returns:
            Dict with stats
        """
        with self.lock:
            return {
                "available": self.available_queue.qsize(),
                "cooldown": len(self.cooldown_dict),
                "removed": len(self.removed_keys),
                "total": self.available_queue.qsize()
                + len(self.cooldown_dict)
                + len(self.removed_keys),
            }
