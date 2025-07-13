# py2cy/config.py
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    """Holds configuration for the transpilation process."""
    # In a future version, this would be loaded from pyproject.toml
    compiler_directives: dict[str, bool | int] = field(default_factory=lambda: {
        "language_level": 3,
        "boundscheck": False,
        "wraparound": False,
        "cdivision": True,
        "nonecheck": False,
    })
    default_to_cpdef: bool = True
    
    # V3: Add an option to enable/disable automatic 'nogil' generation
    auto_nogil: bool = True