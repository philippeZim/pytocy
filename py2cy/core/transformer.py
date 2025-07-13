# py2cy/core/transformer.py
import ast
from py2cy.core.symbol_table import SymbolTable
from py2cy.models.type_defs import get_type_info, TypeInfo, CPP_TEMPLATE_TYPE_MAP

def is_node_gil_free(node: ast.AST, symbol_table: SymbolTable, class_node: ast.ClassDef | None) -> bool:
    if isinstance(node, (ast.Constant, ast.Pass, ast.Continue, ast.Break, ast.Return)): return True
    if isinstance(node, (ast.BinOp, ast.Compare)):
        return all(is_node_gil_free(child, symbol_table, class_node) for child in ast.iter_child_nodes(node))
    if isinstance(node, ast.Name):
        type_info = symbol_table.lookup_variable(node.id)
        return type_info is not None and (type_info.is_c_type or type_info.is_cpp_type)
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == 'self' and class_node:
            attr_type = class_node.cython_attribute_types.get(node.attr)
            return attr_type is not None and (attr_type.is_c_type or attr_type.is_cpp_type)
        return False
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            obj_node = node.func.value
            obj_type = None
            if isinstance(obj_node, ast.Attribute): obj_type = class_node.cython_attribute_types.get(obj_node.attr)
            elif isinstance(obj_node, ast.Subscript): obj_type = class_node.cython_attribute_types.get(obj_node.value.attr)
            return obj_type is not None and obj_type.is_cpp_type
        return False
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return all(is_node_gil_free(child, symbol_table, class_node) for child in ast.iter_child_nodes(node) if child)
    return False

class CythonASTTransformer(ast.NodeTransformer):
    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table
        self.required_cimports, self.uses_cpp, self.class_nodes = set(), False, []

    def _parse_type_hint(self, node: ast.AST) -> TypeInfo:
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) in ('typing.Annotated', 'Annotated'):
            base_node, *ann = node.slice.elts
            if 'ndarray' in ast.unparse(base_node):
                self.required_cimports.add("cimport numpy as np"); self.required_cimports.add("import numpy as np")
                ti = get_type_info("ndarray")
                ti.numpy_dtype = ann[0].value if len(ann) > 0 else "double"
                ti.numpy_ndim = ann[1].value if len(ann) > 1 else 1
                return ti
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) in ('typing.Optional', 'Optional'):
             inner_node = node.slice.elts[0] if isinstance(node.slice, ast.Tuple) else node.slice
             ti = self._parse_type_hint(inner_node)
             if ti.is_c_type and not ti.is_memoryview: ti.is_primitive_pointer = True
             return ti
        if isinstance(node, ast.Attribute) and 'ndarray' in ast.unparse(node):
            self.required_cimports.add("cimport numpy as np"); self.required_cimports.add("import numpy as np")
            return get_type_info("ndarray")
        if isinstance(node, ast.Name): return get_type_info(node.id)
        if isinstance(node, ast.Subscript):
            base_name = ast.unparse(node.value).replace("typing.","").replace("builtins.","").lower()
            if base_name in ("list", "dict", "set"):
                ti = get_type_info(base_name.capitalize())
                self.uses_cpp = True
                self.required_cimports.add(f"from libcpp.{ti.cpp_header} cimport {ti.cython_name}")
                if ti.is_unique_ptr: self.required_cimports.add("from libcpp.memory cimport unique_ptr")
                params = [self._parse_type_hint(e) for e in (node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice])]
                for i, p in enumerate(params):
                    if p.python_name in CPP_TEMPLATE_TYPE_MAP:
                        params[i] = CPP_TEMPLATE_TYPE_MAP[p.python_name]
                        self.required_cimports.add(f"from libcpp.{params[i].cpp_header} cimport {params[i].cython_name}")
                ti.cpp_template_params = params
                return ti
        return get_type_info("object")

    def _get_node_type(self, node: ast.AST) -> TypeInfo:
        if isinstance(node, ast.Subscript):
            base_type = self._get_node_type(node.value)
            if base_type and base_type.is_memoryview and base_type.numpy_dtype:
                # FIX: Correctly infer the C-level type of a memoryview element.
                # e.g., for a "int32" ndarray, the element type is "np.int32_t".
                return TypeInfo(
                    python_name="int",  # Or float, this is an approximation
                    cython_name=f"np.{base_type.numpy_dtype}_t",
                    is_c_type=True
                )
            if base_type and base_type.cython_name == 'map' and base_type.cpp_template_params:
                # FIX: Infer the value type when subscripting a map.
                return base_type.cpp_template_params[1]
        if isinstance(node, ast.BinOp): return get_type_info('int')
        if isinstance(node, ast.Name): return self.symbol_table.lookup_variable(node.id) or get_type_info("object")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int): return get_type_info("int")
            if isinstance(node.value, float): return get_type_info("float")
        if isinstance(node, ast.Attribute):
            if self._class_nodes and isinstance(node.value, ast.Name) and node.value.id == 'self':
                return self._class_nodes[-1].cython_attribute_types.get(node.attr)
        return get_type_info("object")

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.symbol_table.enter_scope(is_class_scope=True)
        node.cython_attribute_types = {item.target.id: self._parse_type_hint(item.annotation) for item in node.body if isinstance(item, ast.AnnAssign)}
        self.class_nodes.append(node)
        self.generic_visit(node)
        self.class_nodes.pop()
        attributes, cpp_members, new_body = [], [], []
        body_items = node.body
        if body_items and isinstance(body_items[0], ast.Expr) and isinstance(body_items[0].value, ast.Constant):
            node.cython_docstring = body_items.pop(0).value.s
        for item in body_items:
            if isinstance(item, ast.AnnAssign):
                attr_info = {'name': item.target.id, 'type_info': item.cython_type}
                attributes.append(attr_info)
                if item.cython_type.is_unique_ptr: cpp_members.append(attr_info)
            elif isinstance(item, ast.FunctionDef): new_body.append(item)
        node.body, node.cython_attributes, node.cython_cpp_members = new_body, attributes, cpp_members
        self.symbol_table.exit_scope()
        return node
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        parent = self.class_nodes[-1] if self.class_nodes else None
        node.cython_func_type = 'cpdef'
        for d in node.decorator_list:
            if ast.unparse(d) in ('cdef', 'py2cy.cdef'): node.cython_func_type = 'cdef'
            elif ast.unparse(d) in ('def_', 'def', 'py2cy.def_'): node.cython_func_type = 'def'
        self.symbol_table.enter_scope()
        node.cython_arg_types = {}
        for arg in node.args.args:
            if arg.arg == 'self': continue
            arg_type = self._parse_type_hint(arg.annotation) if arg.annotation else get_type_info("object")
            self.symbol_table.add_variable(arg.arg, arg_type)
            node.cython_arg_types[arg.arg] = arg_type
        
        # We must visit the body before analyzing it for nogil
        self.generic_visit(node)
        
        node.returns = node.returns or ast.Constant(value=None)
        node.cython_return_type = self._parse_type_hint(node.returns) if node.returns and not (isinstance(node.returns, ast.Constant) and node.returns.value is None) else get_type_info("void")
        is_nogil = node.cython_func_type != 'def' and node.name not in ("__init__", "__cinit__", "_is_valid_event")
        if is_nogil:
             for sub_node in ast.walk(node):
                 if not is_node_gil_free(sub_node, self.symbol_table, parent):
                     is_nogil = False; break
        node.is_nogil_candidate = is_nogil

        self.symbol_table.exit_scope()
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        node.cython_type = self._parse_type_hint(node.annotation)
        self.symbol_table.add_variable(node.target.id, node.cython_type)
        if node.value: self.visit(node.value)
        return node
    
    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        # DEFINITIVE FIX: Transform declarations into AnnAssign nodes.
        self.visit(node.value)
        if isinstance(node.targets[0], ast.Name):
            target_node = node.targets[0]
            if not self.symbol_table.lookup_variable(target_node.id):
                inferred_type = self._get_node_type(node.value)
                if inferred_type and inferred_type.python_name != 'object':
                    # Create a dummy annotation node for the generator
                    # The generator will use node.cython_type directly
                    annotation_node = ast.Name(id='_', ctx=ast.Load())
                    ann_assign_node = ast.AnnAssign(target=target_node, annotation=annotation_node, value=node.value, simple=1)
                    ann_assign_node.cython_type = inferred_type
                    self.symbol_table.add_variable(target_node.id, inferred_type)
                    # Return the transformed AnnAssign node
                    return self.visit(ann_assign_node)
        return node