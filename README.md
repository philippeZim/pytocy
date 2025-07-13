# Py2Cy: The Python to Cython Transpiler

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com/user/py2cy)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

**Py2Cy** is a proof-of-concept tool that automatically transpiles Python code into high-performance Cython code. By leveraging Python's type hints, it intelligently converts Python objects into C/C++ equivalents, generates corresponding Cython `.pyx` and `.pxd` files, and automatically detects opportunities for releasing Python's Global Interpreter Lock (GIL).

The goal is to bridge the gap between Python's ease of use and the raw speed of C/C++, automating the tedious and error-prone process of writing Cython by hand.

## Features

-   **Automatic Type Conversion**: Translates standard Python types (`int`, `float`, `bool`) to efficient C-level types.
-   **C++ Container Support**: Converts Python's `List` and `Dict` type hints to C++ `std::vector` and `std::map`, managed safely via `std::unique_ptr`.
-   **NumPy Integration**: Translates `Annotated` NumPy type hints (`Annotated[np.ndarray, "float64", 2]`) into fast, C-level typed memoryviews.
-   **`.pxd` Header Generation**: Automatically creates `.pxd` files to define clean, C-level APIs for your compiled modules, enabling efficient linking between Cython files.
-   **Automatic `nogil` Detection**: Analyzes function bodies to determine if they are free of Python API calls and automatically marks them as `nogil`, unlocking true parallelism.
-   **`setup.py` Generation**: Creates a ready-to-use `setup.py` file to compile your generated Cython code into a Python extension module.
-   **Local Variable Type Inference**: Infers C-level types for local variables within functions, preventing them from defaulting to slow Python objects.
-   **Custom Decorators**: Use `@cdef` and `@def_` to guide the transpiler, forcing functions to be generated as `cdef` (C-level only) or `def` (Python-level only) respectively.

## Installation

### Prerequisites

-   Python 3.9+
-   A C/C++ compiler toolchain (e.g., GCC on Linux, Clang on macOS, MSVC on Windows).

### Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/py2cy.git
    cd py2cy
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    The project relies on `click` for its CLI and `cython` for the final compilation step.
    ```bash
    pip install click cython
    ```

## Usage

The transpiler is run from the command line on a single Python file.

### Step 1: Transpile the Python Code

Run the transpiler by executing the `py2cy` module, providing your Python file as input and specifying an output directory.

```bash
python -m py2cy <your_python_file.py> -o <output_directory>
```

**Example:**
```bash
python -m py2cy examples/data_processor.py -o cython_output
```

This will generate three files inside the `cython_output` directory:
-   `data_processor.pyx`: The generated Cython source code.
-   `data_processor.pxd`: The generated Cython header file.
-   `setup.py`: The build script for compilation.

### Step 2: Compile the Cython Module

Navigate to the output directory and run the generated `setup.py` script to compile your module.

```bash
cd cython_output
python setup.py build_ext --inplace
```

This will create a compiled extension module (e.g., `data_processor.cpython-310-x86_64-linux-gnu.so`) in the same directory.

### Step 3: Use the Compiled Module

You can now import and use your high-performance module in any standard Python script.

```python
# main.py
from cython_output.data_processor import DataProcessor

# The module is now ready to use!
processor = DataProcessor(num_rows=10, num_cols=5)
processor.log_event(event_id=101, measurement=42.5)
status = processor.get_status_message()
print(status)
# Output: Successfully processed 1 items.
```

## How It Works: A Detailed Example

Let's see how Py2Cy transforms a complex Python class into optimized Cython.

### Input: `data_processor.py`

This Python code uses advanced type hints to describe its data structures.

```python
# To make this file runnable in pure Python, we need dummy decorators and types.
def cdef(func): return func
def def_(func): return func

try:
    from typing import List, Dict, Optional, Annotated
    import numpy as np
except ImportError:
    # Fallbacks for older Python
    List, Dict, Optional, Annotated = object, object, object, object
    class NpMock: ...
    np = NpMock()

class DataProcessor:
    """A processor that simulates a complex data analysis pipeline."""
    # This will become: unique_ptr[map[long, unique_ptr[vector[double]]]]
    event_log: Dict[int, List[float]]

    # This will become a memoryview: np.float64_t[:, ::1]
    result_matrix: Annotated[np.ndarray, "float64", 2]

    # This will become a C-level pointer: long*
    last_error_code: Optional[int]

    processed_count: int

    def __init__(self, num_rows: int, num_cols: int):
        self.result_matrix = np.zeros((num_rows, num_cols), dtype=np.float64)
        self.processed_count = 0
        self.last_error_code = None # -> NULL

    @cdef
    def _is_valid_event(self, event_id: int) -> bool:
        return event_id > 0

    def log_event(self, event_id: int, measurement: float):
        if not self._is_valid_event(event_id):
            return

        # Initialize the vector for this event ID if it's new
        if event_id not in self.event_log:
            self.event_log[event_id] = []

        # This entire block will be marked `nogil`
        self.event_log[event_id].append(measurement)
        self.processed_count += 1
```

### Output: `data_processor.pyx` (Annotated)

The transpiler generates the following `.pyx` file, translating Python concepts to their C/C++ counterparts.

```cython
# cython: language_level=3, boundscheck=False, wraparound=False, ...

from libcpp.map cimport map
from libcpp.memory cimport unique_ptr
from libcpp.vector cimport vector
cimport numpy as np
import numpy as np

cdef class DataProcessor:
    # --- Python attributes are converted to C/C++ declarations ---
    cdef unique_ptr[map[long, unique_ptr[vector[double]]]] event_log
    cdef np.float64_t[::1, ::1] result_matrix
    cdef long processed_count
    cdef long* last_error_code

    def __cinit__(self):
        # --- unique_ptr members are safely initialized in __cinit__ ---
        self.event_log.reset(new map[long, unique_ptr[vector[double]]]())

    def __init__(self, num_rows: int, num_cols: int):
        self.result_matrix = np.zeros((num_rows, num_cols), dtype=np.float64)
        self.processed_count = 0
        self.last_error_code = NULL # --- None is converted to NULL for pointers ---

    # --- @cdef decorator created a C-only function, marked nogil ---
    cdef bint _is_valid_event(self, long event_id) nogil:
        return event_id > 0

    # --- This entire function was detected as GIL-free ---
    cpdef void log_event(self, long event_id, double measurement) nogil:
        if not self._is_valid_event(event_id):
            return

        # --- "in" check translated to C++ map.count() ---
        if self.event_log.get().count(event_id) == 0:
            # --- `[]` assignment translated to C++ vector initialization ---
            self.event_log.get()[event_id].reset(new vector[double]())

        # --- `.append()` translated to C++ `.push_back()` with correct pointer access ---
        self.event_log.get()[event_id].get().push_back(measurement)
        self.processed_count += 1
```

## Translation Guide

Py2Cy uses the following conventions to translate Python type hints:

| Python Type Hint                           | Cython/C++ Translation                               |
| ------------------------------------------ | ---------------------------------------------------- |
| `int`, `float`, `bool`                     | `long`, `double`, `bint`                             |
| `str`, `object`                            | `object` (remains a Python object)                   |
| `List[float]`                              | `unique_ptr[vector[double]]`                         |
| `Dict[int, str]`                           | `unique_ptr[map[long, string]]`                      |
| `Optional[int]`                            | `long*` (a C pointer, initialized to `NULL`)         |
| `np.ndarray`                               | `object` (Python object)                             |
| `Annotated[np.ndarray, "dtype", ndim]`     | Typed Memoryview (e.g., `np.dtype_t[::1, ...]` )     |
| `@cdef` decorator                          | `cdef` function (not visible to Python)              |
| `@def_` decorator                          | `def` function (pure Python, visible)                |
| (no decorator)                             | `cpdef` function (C and Python visible)              |

## Future Work

Py2Cy is currently a proof-of-concept. Future development could include:

-   [ ] Loading configuration from `pyproject.toml`.
-   [ ] Support for a wider range of C++ containers (`std::string`, `std::deque`, `std::set`).
-   [ ] More sophisticated `nogil` analysis for functions with mixed Python/C operations.
-   [ ] Enhanced error reporting for unsupported Python syntax.
-   [ ] Broader support for the Python standard library.

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.