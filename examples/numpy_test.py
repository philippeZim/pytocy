# numpy_test.py
import numpy as np

def normalize_array(arr: np.ndarray) -> np.ndarray:
    """
    Scales an array by its max value. This should be a high-performance,
    no-gil function in Cython.
    """
    max_val: float = 0.0
    
    # Find the maximum value
    # V3 should recognize this as a C-level loop over a memoryview
    for i in range(len(arr)):
        if arr[i] > max_val:
            max_val = arr[i]
            
    if max_val == 0.0:
        return arr

    # Create a new array for the result
    result = np.empty_like(arr)

    # Scale the array
    for i in range(len(arr)):
        result[i] = arr[i] / max_val
        
    return result

def main_logic():
    # This shows how the cythonized function would be used from Python
    my_array = np.array([10.0, 20.0, 50.0, 20.0], dtype=np.float64)
    
    normalized = normalize_array(my_array)
    
    print("Original:", my_array)
    print("Normalized:", normalized)