# py2cy/core/code_generator.py
import ast
from py2cy.models.type_defs import TypeInfo

CPP_METHOD_MAP = {
    "vector": {"append": "push_back"},
    "map": {},
    "set": {"add": "insert"},
}

class CythonCodeGenerator(ast.NodeVisitor):
    """
    V3.6 Code Generator: Restored traversal logic, with careful fixes
    for nested C++ allocations and multi-level dereferencing.
    """
    def __init__(self):
        self._code, self._indent_level = [], 0
        self._current_class_node: ast.ClassDef | None = None
        self._handled_imports = set()

    def _get_cython_type_str(self, type_info: TypeInfo, base_only=False) -> str:
        base_str = type_info.cython_name
        if type_info.is_cpp_type and type_info.cpp_template_params:
            params = ", ".join([self._get_cython_type_str(p) for p in type_info.cpp_template_params])
            base_str = f"{type_info.cython_name}[{params}]"
        if base_only: return base_str
        return f"{base_str}*" if type_info.is_pointer else base_str

    def generate(self, node: ast.AST, directives: dict, cimports: set) -> str:
        self._code, self._handled_imports = [], set()
        for key, value in directives.items(): self._write(f"# cython: {key}={value}")
        self._write("\n")
        py_imports = sorted([s for s in cimports if ' cimport ' not in s])
        cy_imports = sorted([s for s in cimports if ' cimport ' in s])
        if cy_imports:
            for stmt in cy_imports: 
                self._write(stmt)
                if ' cimport ' in stmt: self._handled_imports.add(stmt.split(' cimport ')[0].split()[-1])
            self._write("")
        if py_imports:
            for stmt in py_imports:
                if stmt.split()[-1] not in self._handled_imports: self._write(stmt)
            self._write("")
        self.visit(node)
        return "".join(self._code)

    def _write(self, text): self._code.append("    " * self._indent_level + text + "\n")
    def _indent(self): self._indent_level += 1
    def _dedent(self): self._indent_level -= 1

    def _get_type_of_self_attribute(self, node: ast.AST) -> TypeInfo | None:
        if self._current_class_node and isinstance(node, ast.Attribute) and \
           isinstance(node.value, ast.Name) and node.value.id == 'self':
            return self._current_class_node.cython_attribute_types.get(node.attr)
        return None

    def visit_Module(self, node: ast.Module):
        for item in node.body: self.visit(item)

    def visit_ClassDef(self, node: ast.ClassDef):
        self._current_class_node = node
        self._write(f"cdef class {node.name}:")
        self._indent()
        if node.cython_docstring: self._write(f"'''{node.cython_docstring}'''")
        if node.cython_attributes:
            for attr in node.cython_attributes:
                self._write(f"cdef {self._get_cython_type_str(attr['type_info'])} {attr['name']}")
            self._write("")
        if node.cython_cpp_members:
            self._write("def __cinit__(self):")
            self._indent()
            for member in node.cython_cpp_members:
                self._write(f"self.{member['name']} = new {self._get_cython_type_str(member['type_info'], base_only=True)}()")
            self._dedent(); self._write("")
            self._write("def __dealloc__(self):")
            self._indent()
            for member in node.cython_cpp_members: self._write(f"del self.{member['name']}")
            self._dedent(); self._write("")
        for item in node.body: self.visit(item)
        self._dedent()
        self._current_class_node = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        is_class_method = self._current_class_node is not None
        docstring = ""
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docstring = node.body.pop(0).value.s.strip()
        
        return_type = node.cython_return_type
        if return_type.is_void: return_type_str = "void"
        elif node.name == "__init__": return_type_str = "object"
        else: return_type_str = self._get_cython_type_str(return_type)

        args = []
        if is_class_method:
            args.append(f"{self._current_class_node.name} self" if node.name not in ("__init__", "__cinit__", "__dealloc__") else "self")
        
        for arg in node.args.args:
            if arg.arg == 'self': continue
            args.append(f"{self._get_cython_type_str(node.cython_arg_types[arg.arg])} {arg.arg}")
        
        self._write(f"cpdef {return_type_str} {node.name}({', '.join(args)}):")
        self._indent()
        if docstring: self._write(f"'''{docstring}'''")
        if node.is_nogil_candidate:
            self._write("with nogil:")
            self._indent()
        
        for item in node.body: self.visit(item)

        if node.is_nogil_candidate: self._dedent()
        self._dedent()
        self._write("")

    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
            subscript = node.targets[0]
            map_type = self._get_type_of_self_attribute(subscript.value)
            if map_type and map_type.cython_name == 'map' and isinstance(node.value, (ast.List, ast.ListComp)) and not node.value.elts:
                vector_type_info = map_type.cpp_template_params[1]
                vector_base_type_str = self._get_cython_type_str(vector_type_info, base_only=True)
                map_src = self.to_source(subscript.value)
                key_src = self.to_source(subscript.slice)
                self._write(f"deref({map_src})[{key_src}] = new {vector_base_type_str}()")
                return

        prefix = "cdef " if hasattr(node, 'is_declaration') and node.is_declaration else ""
        type_str = self._get_cython_type_str(node.cython_type) if prefix else ""
        target = self.to_source(node.targets[0])
        value = self.to_source(node.value) if node.value else ""
        self._write(f"{prefix}{type_str} {target} = {value}".replace("  ", " ").strip())

    def to_source(self, node: ast.AST) -> str:
        # --- Multi-level dereferencing for method calls ---
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            obj_node = node.func.value # e.g., self.event_log[event_id]
            if isinstance(obj_node, ast.Subscript):
                map_attr_type = self._get_type_of_self_attribute(obj_node.value)
                if map_attr_type and map_attr_type.cython_name == 'map':
                    vector_ptr_type = map_attr_type.cpp_template_params[1]
                    vector_base_name = vector_ptr_type.cython_name
                    py_method = node.func.attr
                    if vector_base_name in CPP_METHOD_MAP and py_method in CPP_METHOD_MAP[vector_base_name]:
                        cpp_method = CPP_METHOD_MAP[vector_base_name][py_method]
                        map_src, key_src = self.to_source(obj_node.value), self.to_source(obj_node.slice)
                        args_src = ", ".join([self.to_source(arg) for arg in node.args])
                        return f"deref(deref({map_src})[{key_src}]).{cpp_method}({args_src})"

            type_info = self._get_type_of_self_attribute(obj_node)
            if type_info and type_info.is_cpp_type:
                cpp_type, py_method = type_info.cython_name, node.func.attr
                if cpp_type in CPP_METHOD_MAP and py_method in CPP_METHOD_MAP[cpp_type]:
                    cpp_method = CPP_METHOD_MAP[cpp_type][py_method]
                    args_src = ", ".join([self.to_source(arg) for arg in node.args])
                    return f"deref({self.to_source(obj_node)}).{cpp_method}({args_src})"

        # --- Standard dereferencing for subscriptions and len() ---
        subscripted_obj = None
        if isinstance(node, ast.Subscript): subscripted_obj = node.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'len' and node.args:
             subscripted_obj = node.args[0]
        if subscripted_obj:
            type_info = self._get_type_of_self_attribute(subscripted_obj)
            if type_info and type_info.is_pointer:
                obj_src = self.to_source(subscripted_obj)
                if isinstance(node, ast.Subscript): return f"deref({obj_src})[{self.to_source(node.slice)}]"
                if isinstance(node, ast.Call) and node.func.id == 'len': return f"deref({obj_src}).size()"
            elif type_info and type_info.is_memoryview and isinstance(node, ast.Call) and node.func.id == 'len':
                 return f"{self.to_source(subscripted_obj)}.shape[0]"

        try: return ast.unparse(node)
        except Exception: return "..."
    
    # --- Other visitors, restored to known-good state ---
    def visit_If(self, node: ast.If):
        self._write(f"if {self.to_source(node.test)}:")
        self._indent(); [self.visit(item) for item in node.body]; self._dedent()
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self._write(f"elif {self.to_source(node.orelse[0].test)}:")
                self._indent(); [self.visit(item) for item in node.orelse[0].body]; self._dedent()
                if node.orelse[0].orelse:
                    self._write("else:")
                    self._indent(); [self.visit(item) for item in node.orelse[0].orelse]; self._dedent()
            else:
                self._write("else:")
                self._indent(); [self.visit(item) for item in node.orelse]; self._dedent()

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if hasattr(node, 'is_declaration') and node.is_declaration:
            self._write(f"cdef {self._get_cython_type_str(node.cython_type)} {self.to_source(node.target)} = {self.to_source(node.value) if node.value else ''}")
    def visit_Import(self, node: ast.Import): pass
    def visit_ImportFrom(self, node: ast.ImportFrom): pass
    def visit_Pass(self, node: ast.Pass): self._write("pass")
    def visit_Return(self, node: ast.Return): self._write(f"return {self.to_source(node.value) if node.value else ''}")
    def visit_Expr(self, node: ast.Expr): self._write(self.to_source(node.value))
    def visit_For(self, node: ast.For):
        self._write(f"for {self.to_source(node.target)} in {self.to_source(node.iter)}:")
        self._indent(); [self.visit(stmt) for stmt in node.body]; self._dedent()
    def visit_AugAssign(self, node: ast.AugAssign): self._write(ast.unparse(node))
    def generic_visit(self, node):
        try: self._write(ast.unparse(node))
        except: self._write(f"# [py2cy] Unhandled node: {type(node).__name__}")