# py2cy/models/type_defs.py
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List as TypingList

@dataclass
class TypeInfo:
    """Represents the type of a variable for V4."""
    python_name: str
    cython_name: str
    is_c_type: bool = False
    is_cpp_type: bool = False
    is_memoryview: bool = False
    is_unique_ptr: bool = False   # V4: Manages C++ types via unique_ptr
    is_primitive_pointer: bool = False # V4: For Optional[int] -> long*
    is_void: bool = False
    cpp_template_params: TypingList['TypeInfo'] = field(default_factory=list)
    cpp_header: str = ""
    # V4: NumPy specific fields
    numpy_dtype: Optional[str] = None
    numpy_ndim: Optional[int] = None

# A central registry of known type mappings.
BUILTIN_TYPES = {
    # Primitives
    "int": TypeInfo(python_name="int", cython_name="long", is_c_type=True),
    "float": TypeInfo(python_name="float", cython_name="double", is_c_type=True),
    "str": TypeInfo(python_name="str", cython_name="object"),
    "bool": TypeInfo(python_name="bool", cython_name="bint", is_c_type=True),
    "void": TypeInfo(python_name="None", cython_name="void", is_c_type=True, is_void=True),
    
    # Python Containers (fallback)
    "list": TypeInfo(python_name="list", cython_name="list"),
    "dict": TypeInfo(python_name="dict", cython_name="dict"),
    "set": TypeInfo(python_name="set", cython_name="set"),
    
    # V4: C++ types now managed by unique_ptr, not raw pointers
    "List": TypeInfo(python_name="List", cython_name="vector", is_cpp_type=True, cpp_header="vector", is_unique_ptr=True),
    "Dict": TypeInfo(python_name="Dict", cython_name="map", is_cpp_type=True, cpp_header="map", is_unique_ptr=True),
    "Set": TypeInfo(python_name="Set", cython_name="set", is_cpp_type=True, cpp_header="set", is_unique_ptr=True),
    
    # V4: Numpy is now a generic base, to be specified by Annotated
    "ndarray": TypeInfo(python_name="ndarray", cython_name="object", is_memoryview=True, is_c_type=True, numpy_dtype="double", numpy_ndim=1),

    # Special case for object
    "object": TypeInfo(python_name="object", cython_name="object"),
}

# Special mapping for Python types when they are used INSIDE a C++ template
CPP_TEMPLATE_TYPE_MAP = {
    "str": TypeInfo(python_name="str", cython_name="string", is_cpp_type=True, cpp_header="string"),
}

def get_type_info(type_name: str) -> TypeInfo:
    """
    Safely retrieves a fresh copy of type information, defaulting to a Python object.
    """
    # Use dataclasses.replace to get a shallow copy, preventing mutation of the original
    type_info = BUILTIN_TYPES.get(type_name, BUILTIN_TYPES["object"])
    return dataclasses.replace(type_info, cpp_template_params=list(type_info.cpp_template_params))