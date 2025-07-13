# py2cy/core/pxd_generator.py
import ast
from py2cy.models.type_defs import TypeInfo

class PxdCodeGenerator(ast.NodeVisitor):
    def __init__(self):
        self._code = []
        self._indent_level = 0

    def _get_cython_type_str(self, type_info: TypeInfo) -> str:
        if type_info.is_memoryview:
            dtype = type_info.numpy_dtype or "double"
            dtype_str = f"np.{dtype}_t"
            # In pxd, we specify C-contiguity with `::1` at the end
            slicing = ", ".join([":"] * (type_info.numpy_ndim - 1) + ["::1"]) if type_info.numpy_ndim > 0 else ""
            return f"{dtype_str}[{slicing}]"
        if type_info.is_primitive_pointer:
            return f"{type_info.cython_name}*"
        if type_info.is_cpp_type and type_info.cpp_template_params:
            params = ", ".join([self._get_cython_type_str(p) for p in type_info.cpp_template_params])
            return f"{type_info.cython_name}[{params}]"
        return type_info.cython_name

    def generate(self, node: ast.AST, cimports: set) -> str:
        self._code = []
        self._write("# V4 Generated .pxd file by py2cy (FINAL)")
        
        has_numpy = any('numpy' in s for s in cimports)
        
        unique_cimports = set()
        for s in cimports:
            if ' cimport ' in s: unique_cimports.add(s)
        if has_numpy: unique_cimports.add("cimport numpy as np")

        if unique_cimports:
            for cimport_stmt in sorted(list(unique_cimports)):
                self._write(cimport_stmt)
            self._write("\n")

        self.visit(node)
        return "".join(self._code)

    def _write(self, text): self._code.append("    " * self._indent_level + text + "\n")
    def _indent(self): self._indent_level += 1
    def _dedent(self): self._indent_level -= 1

    def visit_Module(self, node: ast.Module):
        for item in node.body:
            if isinstance(item, ast.Try) and any(isinstance(h.type, ast.Name) and h.type.id == 'ImportError' for h in item.handlers if h.type):
                continue
            if isinstance(item, ast.FunctionDef) and item.name in ('cdef', 'def_'):
                continue
            if isinstance(item, ast.ClassDef):
                self.visit(item)

    def visit_ClassDef(self, node: ast.ClassDef):
        self._write(f"cdef class {node.name}:")
        self._indent()
        
        has_content = False
        if hasattr(node, 'cython_attributes'):
             for attr_dict in node.cython_attributes:
                attr_name, attr_type = attr_dict['name'], attr_dict['type_info']
                # FINAL FIX: Add is_primitive_pointer to this check
                if attr_type.is_c_type or attr_type.is_memoryview or attr_type.is_primitive_pointer:
                    has_content = True
                    type_str = self._get_cython_type_str(attr_type)
                    self._write(f"cdef readonly {type_str} {attr_name}")
        
        body_methods = [item for item in node.body if isinstance(item, ast.FunctionDef)]
        
        if has_content and any(item for item in body_methods if getattr(item, 'cython_func_type', 'cpdef') != 'def'):
             self._write("")

        for item in body_methods:
            func_type = getattr(item, 'cython_func_type', 'cpdef')
            if func_type == 'def' or item.name == "__init__":
                continue
            has_content = True
            return_type_str = self._get_cython_type_str(item.cython_return_type)
            args = []
            for arg in item.args.args:
                if arg.arg == 'self': continue
                arg_type_str = self._get_cython_type_str(item.cython_arg_types[arg.arg])
                args.append(f"{arg_type_str} {arg.arg}")
            self._write(f"{func_type} {return_type_str} {item.name}({', '.join(args)})")

        if not has_content:
             self._write("pass")

        self._dedent()
        self._write("\n")