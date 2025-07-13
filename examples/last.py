# To make this file runnable in pure Python, we need dummy decorators and types.
def cdef(func): return func
def def_(func): return func # 'def' is a keyword, so we use 'def_'
try:
    from typing import List, Dict, Optional, Annotated
    import numpy as np
except ImportError:
    # Fallbacks for older Python
    List = dict
    Dict = dict
    Optional = object
    Annotated = object
    class NpMock:
        def ndarray(self): pass
        def float64(self): pass
        def int32(self): pass
        def zeros(self, shape, dtype): pass
    np = NpMock()


class DataProcessor:
    """
    A processor that simulates a complex data analysis pipeline.
    It uses C++ containers for performance-critical logs and NumPy for numerical data.
    """
    # V4: A dict mapping an event ID to a list of measurements (float).
    # This will become unique_ptr[map[int, unique_ptr[vector[double]]]]
    event_log: Dict[int, List[float]]

    # V4: A 2D NumPy array for storing processed results.
    # This will become a memoryview: np.float64_t[:, ::1]
    result_matrix: Annotated[np.ndarray, "float64", 2]

    # V3: A simple C-type attribute.
    processed_count: int
    
    # V4: An optional attribute, which could be a C-level pointer.
    # This will become long*
    last_error_code: Optional[int]

    def __init__(self, num_rows: int, num_cols: int):
        """
        Initializes the data processor and allocates the NumPy result matrix.
        """
        self.result_matrix = np.zeros((num_rows, num_cols), dtype=np.float64)
        self.processed_count = 0
        self.last_error_code = None # In Cython, this will be NULL

    @cdef
    def _is_valid_event(self, event_id: int) -> bool:
        """
        A C-level helper function. Fast, but not accessible from Python.
        """
        return event_id > 0 and event_id < 10000

    @def_
    def get_status_message(self) -> str:
        """
        A pure Python method. This should remain a standard 'def' function.
        It accesses C-level attributes, which Cython will handle via properties.
        """
        if self.last_error_code is not None:
            return f"Error encountered with code: {self.last_error_code}"
        return f"Successfully processed {self.processed_count} items."

    def log_event(self, event_id: int, measurement: float):
        """
        Logs a measurement for a given event ID. This function should be a 'cpdef'
        and contain a 'nogil' block for high-performance C++ operations.
        """
        if not self._is_valid_event(event_id):
            self.last_error_code = -1
            return

        # Initialize the vector for this event_id if it's the first time we see it.
        # V4: This should translate to checking if the map key exists and if the unique_ptr is set.
        if event_id not in self.event_log:
            self.event_log[event_id] = [] # V4: -> event_log.get()[event_id].reset(new vector[double]())

        # V4: This block should be a candidate for 'with nogil:'
        # It involves only C++/C types and operations.
        # It calls a method on a nested C++ object.
        self.event_log[event_id].append(measurement) # -> .get()[event_id].get().push_back(measurement)
        self.processed_count += 1
        
        # Reset error code on success
        if self.last_error_code is not None:
             self.last_error_code = None

    def process_data_stream(self, data_points: Annotated[np.ndarray, "int32", 1]):
        """
        Processes a stream of data points, performing calculations and handling
        potential errors with try/except/finally.
        """
        i: int = 0
        n: int = len(data_points)
        
        # V4: Test 'while' loop and 'try/except/finally'
        while i < n:
            try:
                point = data_points[i]
                if point == 999: # Special error code
                    # This will be caught by `except ValueError`
                    raise ValueError("Encountered sentinel value")
                
                # Simulate some calculation
                row = i % self.result_matrix.shape[0]
                col = (i // self.result_matrix.shape[0]) % self.result_matrix.shape[1]
                
                # Access memoryview
                self.result_matrix[row, col] = point * 1.5
                self.log_event(100 + row, self.result_matrix[row, col])

            except ValueError as e:
                print(f"Caught a processing error: {e}")
                self.last_error_code = 500 # Internal server error
            
            finally:
                # This block must always execute
                i += 1
        
        print("Stream processing finished.")