# py2cy/models/type_defs.py
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List as TypingList

@dataclass
class TypeInfo:
    """Represents the type of a variable, now with C++ and pointer support."""
    python_name: str
    cython_name: str
    is_c_type: bool = False
    is_cpp_type: bool = False
    is_memoryview: bool = False
    is_pointer: bool = False      # For C++ types managed by pointers
    is_void: bool = False         # For void return types
    cpp_template_params: TypingList['TypeInfo'] = field(default_factory=list)
    cpp_header: str = ""

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
    
    # Generic Python types mapping to C++ (now handled as pointers)
    "List": TypeInfo(python_name="List", cython_name="vector", is_cpp_type=True, cpp_header="vector", is_pointer=True),
    "Dict": TypeInfo(python_name="Dict", cython_name="map", is_cpp_type=True, cpp_header="map", is_pointer=True),
    "Set": TypeInfo(python_name="Set", cython_name="set", is_cpp_type=True, cpp_header="set", is_pointer=True),
    
    # Numpy support (maps to a default memoryview)
    "ndarray": TypeInfo(python_name="ndarray", cython_name="double[:, ::1]", is_memoryview=True, is_c_type=True),

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
    type_info = BUILTIN_TYPES.get(type_name, BUILTIN_TYPES["object"])
    # Return a copy to prevent modifications to the global registry
    return dataclasses.replace(type_info)