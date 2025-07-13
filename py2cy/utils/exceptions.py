class Py2CyError(Exception):
    """Base exception for the py2cy application."""
    pass

class TypeInferenceError(Py2CyError):
    """Raised when a variable's type cannot be reliably inferred."""
    pass

class TranslationError(Py2CyError):
    """Raised for Python syntax that cannot be translated."""
    pass