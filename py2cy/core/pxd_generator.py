# py2cy/core/pxd_generator.py
import ast
from py2cy.models.type_defs import TypeInfo

class PxdCodeGenerator(ast.NodeVisitor):
    """
    Walks the annotated AST and generates a Cython .pxd header file.
    V3.2: Fixes illegal public C++ type declarations.
    """
    def __init__(self):
        self._code = []
        self._indent_level = 0
        self._cimports = set()

    def _get_cython_type_str(self, type_info: TypeInfo) -> str:
        """Constructs the full Cython type string, including C++ templates."""
        if type_info.is_memoryview:
            return f"{type_info.cython_name}[:, ::1]" # Basic contiguous memoryview
        if type_info.is_cpp_type and type_info.cpp_template_params:
            params = ", ".join([self._get_cython_type_str(p) for p in type_info.cpp_template_params])
            return f"{type_info.cython_name}[{params}]"
        return type_info.cython_name

    def generate(self, node: ast.AST, cimports: set) -> str:
        self._code = []
        self._write("# V3.2 Generated .pxd file by py2cy")

        if cimports:
            for cimport_stmt in sorted(list(cimports)):
                self._write(cimport_stmt)
            self._write("\n")

        self.visit(node)
        return "".join(self._code)

    def _write(self, text):
        self._code.append("    " * self._indent_level + text + "\n")

    def _indent(self):
        self._indent_level += 1

    def _dedent(self):
        self._indent_level -= 1

    def visit_Module(self, node: ast.Module):
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.ClassDef)):
                self.visit(item)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.decorator_list or "cpdef" in getattr(node, 'cython_func_type', 'cpdef'):
            return_type_str = self._get_cython_type_str(node.cython_return_type)
            args = []
            for arg in node.args.args:
                if arg.arg == 'self':
                    continue
                arg_name = arg.arg
                arg_type_str = self._get_cython_type_str(node.cython_arg_types[arg_name])
                args.append(f"{arg_type_str} {arg_name}")

            self._write(f"cpdef {return_type_str} {node.name}({', '.join(args)})")

    def visit_ClassDef(self, node: ast.ClassDef):
        self._write(f"cdef class {node.name}:")
        self._indent()
        
        has_public_attr = False
        if hasattr(node, 'cython_attributes'):
            for attr_name, attr_type, is_public in node.cython_attributes:
                # Only C-compatible types can be public
                if is_public and not attr_type.is_cpp_type:
                    has_public_attr = True
                    type_str = self._get_cython_type_str(attr_type)
                    self._write(f"cdef public {type_str} {attr_name}")
        
        if not has_public_attr:
             self._write("pass")

        self._dedent()
        self._write("\n")

    def generic_visit(self, node):
        pass