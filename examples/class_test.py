# class_test.py
from typing import List, Dict

class DataProcessor:
    """A class that uses C++ containers for processing."""
    
    # These annotations define the C-level attributes of the class
    _data: List[int]
    _cache: Dict[str, float]

    def __init__(self, initial_value: int):
        # The transpiler will use __cinit__ for C++ members.
        # This __init__ method is for Python-level logic, if any.
        self._cache["initial_value"] = float(initial_value)

    def add_item(self, item: int):
        """Adds an item to the internal C++ vector."""
        self._data.append(item)

    def get_data_sum(self) -> int:
        """Calculates the sum of data using a nogil loop."""
        total: int = 0
        # V3 should make this a C-level loop and run it with nogil
        for item in self._data:
            total += item
        return total

    def get_cache_value(self, key: str) -> float:
        """Retrieves a value from the internal C++ map."""
        return self._cache[key]