# py2cy/core/transformer.py
import ast
from py2cy.core.symbol_table import SymbolTable
from py2cy.models.type_defs import get_type_info, TypeInfo, CPP_TEMPLATE_TYPE_MAP

def is_node_gil_free(node: ast.AST, symbol_table: SymbolTable, class_node: ast.ClassDef | None) -> bool:
    """
    Recursively checks if an AST node is GIL-free.
    V3.5: This is a more robust check.
    """
    # Base cases: Simple nodes
    if isinstance(node, ast.Constant): return True
    if isinstance(node, (ast.BinOp, ast.Compare, ast.AugAssign)):
        return all(is_node_gil_free(child, symbol_table, class_node) for child in ast.iter_child_nodes(node))

    if isinstance(node, ast.Name):
        type_info = symbol_table.lookup_variable(node.id)
        return type_info is not None and type_info.is_c_type

    # Attribute access: a.b
    if isinstance(node, ast.Attribute):
        # Check for self.c_attribute
        if isinstance(node.value, ast.Name) and node.value.id == 'self' and class_node:
            attr_type = class_node.cython_attribute_types.get(node.attr)
            return attr_type is not None and (attr_type.is_c_type or attr_type.is_cpp_type)
        # Check for local_c_var.shape
        elif isinstance(node.value, ast.Name):
            var_type = symbol_table.lookup_variable(node.value.id)
            return var_type is not None and var_type.is_c_type
        return False

    # Calls: func()
    if isinstance(node, ast.Call):
        # Python built-ins like range() and len() on C-types are usually safe
        if isinstance(node.func, ast.Name) and node.func.id in ('range', 'len'):
            return True
        # A call to a C++ method or another nogil function is safe
        if isinstance(node.func, ast.Attribute):
            return is_node_gil_free(node.func, symbol_table, class_node)
        
    # Any other node type, especially those involving Python objects, is unsafe.
    # This includes print(), dict access, etc.
    return False


class CythonASTTransformer(ast.NodeTransformer):
    """
    V3.5 Transformer: Includes robust nogil purity analysis.
    """
    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table
        self.required_cimports = set()
        self.uses_cpp = False
        self.class_nodes = []

    def _parse_type_hint(self, node: ast.AST) -> TypeInfo:
        if isinstance(node, ast.Attribute):
            if ast.unparse(node) in ('np.ndarray', 'numpy.ndarray'):
                self.required_cimports.add("cimport numpy as np"); self.required_cimports.add("import numpy as np")
                return get_type_info("ndarray")
        
        if isinstance(node, ast.Name): return get_type_info(node.id)
        
        if isinstance(node, ast.Subscript):
            base_type_name = ast.unparse(node.value).replace("typing.","")
            # Normalize list/dict to their C++ counterpart names from typing
            if base_type_name.lower() == "list": base_type_name = "List"
            if base_type_name.lower() == "dict": base_type_name = "Dict"
            if base_type_name.lower() == "set": base_type_name = "Set"
            
            base_type_info = get_type_info(base_type_name)

            if base_type_info.is_cpp_type:
                self.uses_cpp = True
                self.required_cimports.add(f"from libcpp.{base_type_info.cpp_header} cimport {base_type_info.cython_name}")
                if base_type_info.is_pointer: self.required_cimports.add("from cython.operator cimport dereference as deref")
                slice_node = node.slice
                params = [self._parse_type_hint(elt) for elt in (slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node])]
                for i, p in enumerate(params):
                    if p.python_name in CPP_TEMPLATE_TYPE_MAP:
                        params[i] = CPP_TEMPLATE_TYPE_MAP[p.python_name]
                        self.required_cimports.add(f"from libcpp.{params[i].cpp_header} cimport {params[i].cython_name}")
                base_type_info.cpp_template_params = params
            return base_type_info
        return get_type_info("object")

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.symbol_table.enter_scope()
        
        # We need to pre-process attributes to build the type map
        # before visiting methods, so the purity checker can use it.
        attribute_types = {}
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_info = self._parse_type_hint(item.annotation)
                attribute_types[item.target.id] = type_info
        node.cython_attribute_types = attribute_types
        
        # Now visit all children (methods, etc.)
        self.generic_visit(node)

        attributes, cpp_members, new_body = [], [], []
        body_items = node.body
        if body_items and isinstance(body_items[0], ast.Expr) and isinstance(body_items[0].value, ast.Constant):
            node.cython_docstring = body_items[0].value.s
            body_items = body_items[1:]
        else: node.cython_docstring = None
        
        for item in body_items:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_info = item.cython_type
                attr_name = item.target.id
                attr_info = {'name': attr_name, 'type_info': type_info}
                attributes.append(attr_info)
                if type_info.is_pointer: cpp_members.append(attr_info)
            elif isinstance(item, ast.FunctionDef): new_body.append(item)
            elif isinstance(item, (ast.Pass, ast.Expr)): continue

        node.body = new_body
        node.cython_attributes, node.cython_cpp_members = attributes, cpp_members
        self.class_nodes.append(node)
        self.symbol_table.exit_scope()
        return node
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.symbol_table.enter_scope()
        arg_types, is_nogil_candidate = {}, True
        
        parent_class_node = None
        if self.class_nodes: parent_class_node = self.class_nodes[-1]

        for arg in node.args.args:
            if arg.arg == 'self': continue
            arg_type = self._parse_type_hint(arg.annotation) if arg.annotation else get_type_info("object")
            if not arg_type.is_c_type: is_nogil_candidate = False
            self.symbol_table.add_variable(arg.arg, arg_type)
            arg_types[arg.arg] = arg_type
        node.cython_arg_types = arg_types
        
        has_return = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
        if node.returns: node.cython_return_type = self._parse_type_hint(node.returns)
        elif not has_return: node.cython_return_type = get_type_info("void")
        else: node.cython_return_type = get_type_info("object")
        if not node.cython_return_type.is_c_type: is_nogil_candidate = False

        if is_nogil_candidate:
            for body_node in node.body:
                if not is_node_gil_free(body_node, self.symbol_table, parent_class_node):
                    is_nogil_candidate = False
                    break
        node.is_nogil_candidate = is_nogil_candidate and node.name not in ("__init__", "__cinit__", "__dealloc__")

        self.generic_visit(node)
        self.symbol_table.exit_scope()
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        if node.value: self.visit(node.value)
        if not isinstance(node.target, ast.Name): return self.generic_visit(node)
        target_name = node.target.id
        type_info = self._parse_type_hint(node.annotation)
        node.cython_type = type_info
        node.is_declaration = not self.symbol_table.lookup_variable(target_name)
        self.symbol_table.add_variable(target_name, type_info)
        return node
    
    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.visit(node.value)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_node = node.targets[0]
            var_name = target_node.id
            existing_type = self.symbol_table.lookup_variable(var_name)
            node.is_declaration = not existing_type
            if node.is_declaration:
                inferred_type = self._infer_type_from_node(node.value)
                self.symbol_table.add_variable(var_name, inferred_type)
                node.cython_type = inferred_type
            else: node.cython_type = existing_type
        return node
    
    def _infer_type_from_node(self, node: ast.AST) -> TypeInfo:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int): return get_type_info("int")
            if isinstance(node.value, float): return get_type_info("float")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'len':
            return get_type_info("int")
        return get_type_info("object")