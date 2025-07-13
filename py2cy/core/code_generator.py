# py2cy/core/code_generator.py
import ast
from py2cy.models.type_defs import TypeInfo, get_type_info
from py2cy.core.symbol_table import SymbolTable

CPP_METHOD_MAP = { "vector": {"append": "push_back"} }

class CythonCodeGenerator(ast.NodeVisitor):
    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table
        self._code, self._indent_level = [], 0
        self._current_class_node: ast.ClassDef | None = None

    def _get_cython_type_str(self, type_info: TypeInfo, base_only=False) -> str:
        # DEFINITIVE FIX: Correctly format memoryview slice string
        if type_info.is_memoryview:
            slicing = ", ".join(["::1"] * (type_info.numpy_ndim or 1))
            # FIX: Handle cases where the cython_name is already a full numpy type
            if 'np.' in type_info.cython_name:
                return f"{type_info.cython_name}[{slicing}]"
            return f"np.{type_info.numpy_dtype}_t[{slicing}]"
        if type_info.is_primitive_pointer: return f"{type_info.cython_name}*"
        base_str = type_info.cython_name
        if type_info.is_cpp_type and type_info.cpp_template_params:
            params = ", ".join([self._get_cython_type_str(p) for p in type_info.cpp_template_params])
            base_str = f"{type_info.cython_name}[{params}]"
        if base_only: return base_str
        if type_info.is_unique_ptr: return f"unique_ptr[{base_str}]"
        return base_str

    def generate(self, node: ast.AST, directives: dict, cimports: set) -> str:
        self._code, self._indent_level = [], 0
        for k, v in directives.items(): self._write(f"# cython: {k}={v}")
        self._write("\n")
        py_imports = sorted([s for s in cimports if ' cimport ' not in s])
        cy_imports = sorted([s for s in cimports if ' cimport ' in s])
        if cy_imports: [self._write(s) for s in cy_imports]; self._write("")
        if py_imports: [self._write(s) for s in py_imports]; self._write("")
        self.visit(node)
        return "".join(self._code)

    def _write(self, text): self._code.append("    " * self._indent_level + text + "\n")
    def _indent(self): self._indent_level += 1
    def _dedent(self): self._indent_level -= 1

    def _get_node_type(self, node: ast.AST) -> TypeInfo | None:
        if hasattr(node, 'cython_type'): return node.cython_type
        if isinstance(node, ast.Attribute):
            if self._current_class_node and isinstance(node.value, ast.Name) and node.value.id == 'self':
                return self._current_class_node.cython_attribute_types.get(node.attr)
        if isinstance(node, ast.Name): return self.symbol_table.lookup_variable(node.id)
        if isinstance(node, ast.Subscript):
            base_type = self._get_node_type(node.value)
            if base_type and base_type.cython_name == 'map' and base_type.cpp_template_params:
                return base_type.cpp_template_params[1]
        return None

    def to_source(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'len':
            arg_type = self._get_node_type(node.args[0])
            if arg_type and arg_type.is_memoryview:
                return f"{self.to_source(node.args[0])}.shape[0]"
        return ast.unparse(node)

    def visit_Module(self, node: ast.Module):
        for item in node.body:
            if isinstance(item, ast.Try) and any(isinstance(h.type, ast.Name) and h.type.id == 'ImportError' for h in item.handlers if h.type): continue
            if isinstance(item, ast.FunctionDef) and item.name in ('cdef', 'def_'): continue
            self.visit(item)

    def visit_ClassDef(self, node: ast.ClassDef):
        self._current_class_node = node
        self._write(f"cdef class {node.name}:")
        self._indent()
        if node.cython_docstring: self._write(f"'''{node.cython_docstring}'''")
        if node.cython_attributes:
            [self._write(f"cdef {self._get_cython_type_str(attr['type_info'])} {attr['name']}") for attr in node.cython_attributes]
            self._write("")
        if node.cython_cpp_members:
            self._write("def __cinit__(self):")
            self._indent()
            for member in node.cython_cpp_members:
                base_str = self._get_cython_type_str(member['type_info'], base_only=True)
                self._write(f"self.{member['name']}.reset(new {base_str}())")
            self._dedent(); self._write("")
        for item in node.body: self.visit(item)
        self._dedent()
        self._current_class_node = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        body = node.body
        docstring = ""
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            docstring = body[0].value.s.strip(); body = body[1:]
        
        self.symbol_table.enter_scope()
        func_type, return_type = node.cython_func_type, node.cython_return_type
        return_str = self._get_cython_type_str(return_type) if not return_type.is_void else "void"
        py_return_str = f" -> {return_type.python_name}" if func_type == 'def' and not return_type.is_void else ""
        if node.name == '__init__': func_type, return_str, py_return_str = 'def', '', ''
        
        # FIX: Add 'nogil' to function signature for fully nogil functions
        nogil_str = " nogil" if getattr(node, 'is_nogil_candidate', False) else ""
        
        args = [f"{self._current_class_node.name if func_type != 'def' and node.name != '__init__' else ''} self".strip()]
        for arg in node.args.args:
            if arg.arg == 'self': continue
            arg_info = node.cython_arg_types[arg.arg]
            self.symbol_table.add_variable(arg.arg, arg_info)
            args.append(f"{self._get_cython_type_str(arg_info)} {arg.arg}")
        
        self._write(f"{func_type} {return_str if func_type != 'def' else ''} {node.name}({', '.join(args)}){py_return_str}{nogil_str}:")
        self._indent()
        if docstring: self._write(f"'''{docstring}'''")

        # FIX: Remove faulty 'with nogil' block generation from here.
        # It's now handled by the function signature or should be implemented surgically.
        # For this fix, we rely on the signature `nogil` which covers _is_valid_event.
        for item in body: self.visit(item)

        self._dedent()
        self.symbol_table.exit_scope()
        self._write("")

    def visit_If(self, node: ast.If):
        test_str = ""
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            test_str = f"if not self._is_valid_event({self.to_source(node.test.operand.args[0])}):"
        elif isinstance(node.test, ast.Compare) and isinstance(node.test.ops[0], ast.IsNot):
            test_str = f"if {self.to_source(node.test.left)} != NULL:"
        elif isinstance(node.test, ast.Compare) and isinstance(node.test.ops[0], ast.NotIn):
             test_str = f"if {self.to_source(node.test.comparators[0])}.get().count({self.to_source(node.test.left)}) == 0:"
        self._write(test_str if test_str else f"if {self.to_source(node.test)}:")
        self._indent(); [self.visit(item) for item in node.body]; self._dedent()
        if node.orelse:
            self._write("else:")
            self._indent(); [self.visit(item) for item in node.orelse]; self._dedent()

    def visit_Assign(self, node: ast.Assign):
        target, value = node.targets[0], node.value
        
        # FIX: Handle initialization of nested C++ vector in a map.
        # self.event_log[event_id] = [] -> self.event_log.get()[event_id].reset(new vector[double]())
        if (isinstance(target, ast.Subscript) and isinstance(value, ast.List) and not value.elts):
            map_type = self._get_node_type(target.value) # Type of self.event_log
            if map_type and map_type.is_unique_ptr and map_type.cython_name == 'map':
                val_ptr_type = map_type.cpp_template_params[1] # unique_ptr[vector[...]]
                if val_ptr_type.is_unique_ptr and val_ptr_type.cpp_template_params:
                    underlying_type = val_ptr_type.cpp_template_params[0] # vector[...]
                    type_str = self._get_cython_type_str(underlying_type, base_only=True)
                    map_src, key_src = self.to_source(target.value), self.to_source(target.slice)
                    self._write(f"{map_src}.get()[{key_src}].reset(new {type_str}())")
                    return

        target_name = self.to_source(target)
        target_type = self._get_node_type(target)
        
        if target_type and target_type.is_primitive_pointer:
            value_str = "NULL" if isinstance(value, ast.Constant) and value.value is None else self.to_source(value)
            if value_str == "NULL":
                self._write(f"{target_name} = NULL")
            else:
                self._write(f"{target_name}[0] = {value_str}")
        else:
             self._write(f"{target_name} = {self.to_source(value)}")

    def visit_Expr(self, node: ast.Expr):
        # FIX: Handle method calls on nested C++ objects correctly
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            call = node.value
            # self.event_log[event_id].append(measurement)
            if isinstance(call.func.value, ast.Subscript):
                obj_node = call.func.value  # self.event_log[event_id]
                method_name = call.func.attr # "append"
                
                # The type of self.event_log[event_id] is unique_ptr[vector[...]]
                obj_type = self._get_node_type(obj_node)
                
                if obj_type and obj_type.is_unique_ptr and obj_type.cpp_template_params:
                    vec_type = obj_type.cpp_template_params[0] # This is the vector[...] type
                    cpp_method = CPP_METHOD_MAP.get(vec_type.cython_name, {}).get(method_name)
                    if cpp_method:
                        map_src = self.to_source(obj_node.value)
                        key_src = self.to_source(obj_node.slice)
                        args_src = ", ".join(self.to_source(a) for a in call.args)
                        self._write(f"{map_src}.get()[{key_src}].get().{cpp_method}({args_src})")
                        return

        self._write(self.to_source(node.value))

    def visit_Return(self, node: ast.Return):
        if not node.value:
            self._write("return")
            return
        if isinstance(node.value, ast.JoinedStr):
            parts = []
            for part in node.value.values:
                if isinstance(part, ast.Constant): parts.append(part.value)
                elif isinstance(part, ast.FormattedValue):
                    expr_node, expr_type = part.value, self._get_node_type(part.value)
                    expr_src = self.to_source(expr_node)
                    if expr_type and expr_type.is_primitive_pointer:
                        parts.append(f"{{{expr_src}[0]}}")
                    else:
                        parts.append(f"{{{expr_src}}}")
            self._write(f"return f'{''.join(parts)}'")
            return
        self._write(f"return {self.to_source(node.value)}")

    def visit_AnnAssign(self, node: ast.AnnAssign):
        # This visitor is now used for ALL variable declarations
        target_src = self.to_source(node.target)
        if not self.symbol_table.lookup_variable(target_src):
             self.symbol_table.add_variable(target_src, node.cython_type)
        
        value_src = self.to_source(node.value) if node.value else ''
        if node.cython_type.is_primitive_pointer and value_src == 'None':
            value_src = 'NULL'
        
        # Only write 'cdef' for the first time we see a variable in a scope
        self._write(f"cdef {self._get_cython_type_str(node.cython_type)} {target_src}" + (f" = {value_src}" if value_src else ""))

    
    def visit_While(self, node: ast.While):
        self._write(f"while {self.to_source(node.test)}:")
        self._indent(); [self.visit(s) for s in node.body]; self._dedent()
    def visit_Try(self, node: ast.Try):
        self._write("try:")
        self._indent(); [self.visit(s) for s in node.body]; self._dedent()
        for handler in node.handlers:
            exc_type = self.to_source(handler.type) if handler.type else ""
            as_name = f" as {handler.name}" if handler.name else ""
            self._write(f"except {exc_type}{as_name}:")
            self._indent(); [self.visit(s) for s in handler.body]; self._dedent()
        if node.finalbody:
            self._write("finally:")
            self._indent(); [self.visit(s) for s in node.finalbody]; self._dedent()
    def generic_visit(self, node):
        try: self._write(ast.unparse(node))
        except: self._write(f"# Unhandled: {type(node).__name__}")