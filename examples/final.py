# edge_case_stress_test.py
"""
A stress test designed to probe for edge cases in the py2cy transpiler.
It focuses on nested C++ containers, multi-class interactions, and mixed
GIL/nogil code blocks.
"""
from typing import Dict, List, Set
import numpy as np

class Config:
    """A simple configuration class. Tests multi-class handling."""
    
    # A set of strings, testing another C++ container
    valid_ids: Set[str]

    def __init__(self):
        # This __init__ is intentionally empty to test this edge case.
        pass

    def setup_ids(self):
        """Tests C++ method translation for set.add -> set.insert."""
        self.valid_ids.add("ID-001")
        self.valid_ids.add("ID-007")

    def is_valid(self, an_id: str) -> bool:
        """Tests C++ set.count() for checking existence."""
        # A common way to check for existence in a C++ set is .count()
        return self.valid_ids.count(an_id) > 0


class Processor:
    """
    A more complex class that uses nested C++ types and interacts
    with another transpiled class.
    """
    # Nested C++ container: map of strings to vectors of integers.
    # This is a key stress test for the type parser.
    event_log: Dict[str, List[int]]
    config: Config # Tests handling of attributes that are other cdef classes
    status_codes: np.ndarray

    def __init__(self, config_obj: Config):
        """Initializes with another class instance."""
        self.event_log = {}
        self.config = config_obj
        self.status_codes = np.array([0, 0, 0], dtype=np.int32)
    
    def register_event(self, event_id: str, event_code: int):
        """
        Tests appending to a vector that is a value in a map. This is
        a complex dereferencing scenario.
        """
        # Ensure the key exists before trying to append.
        if event_id not in self.event_log:
            self.event_log[event_id] = []
        
        self.event_log[event_id].append(event_code)

    def process_events(self):
        """
        A mixed-mode method. The outer loop can be nogil, but the inner
        print statement requires the GIL. This tests context handling.
        """
        num_events: int = len(self.event_log)
        print(f"Processing {num_events} unique event IDs.")

        # This loop should be a candidate for nogil, but the body is not.
        # The transpiler should correctly choose NOT to use `with nogil`.
        for key in self.event_log:
            if self.config.is_valid(key):
                # This requires a GIL-bound call to another class method
                print(f"  Processing valid key: {key}")
                self.status_codes[0] += 1
            else:
                print(f"  Skipping invalid key: {key}")
                self.status_codes[1] += 1
    
    def get_events_for_id(self, event_id: str) -> List[int]:
        """
        Tests returning a C++ container, which Cython should auto-convert
        to a Python list for the caller.
        """
        if event_id in self.event_log:
            return self.event_log[event_id]
        return []


if __name__ == "__main__":
    print("--- Starting Edge Case Stress Test ---")
    
    # Test multi-class setup
    conf = Config()
    conf.setup_ids()
    proc = Processor(conf)

    # Test complex registration
    proc.register_event("ID-001", 100)
    proc.register_event("ID-001", 101)
    proc.register_event("ID-007", 200)
    proc.register_event("ID-INVALID", 999)

    print("\n[State] Initial Processor State:")
    print(f"  Event Log: {proc.event_log}")
    
    # Test mixed-mode processing
    print("\n[Action] Processing events...")
    proc.process_events()
    print("\n[State] Status codes after processing [valid, invalid, other]:")
    print(f"  {proc.status_codes}")
    assert proc.status_codes[0] == 2 # ID-001, ID-007
    assert proc.status_codes[1] == 1 # ID-INVALID

    # Test returning a C++ vector as a Python list
    events = proc.get_events_for_id("ID-001")
    print(f"\n[State] Events retrieved for ID-001: {events}")
    assert isinstance(events, list)
    assert events == [100, 101]

    print("\n--- Edge Case Stress Test Completed Successfully ---")