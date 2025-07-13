# py2cy/core/symbol_table.py
from typing import Optional, Dict
from py2cy.models.type_defs import TypeInfo

class Scope:
    """Represents a single lexical scope."""
    def __init__(self, parent: Optional['Scope'] = None, is_class_scope: bool = False):
        self.parent = parent
        self.variables: Dict[str, TypeInfo] = {}
        self.is_class_scope = is_class_scope

    def add_variable(self, name: str, type_info: TypeInfo):
        self.variables[name] = type_info

    def lookup_variable(self, name: str) -> Optional[TypeInfo]:
        if name in self.variables:
            return self.variables[name]
        if self.parent:
            return self.parent.lookup_variable(name)
        return None

class SymbolTable:
    """
    Manages a stack of scopes to track variables and their types.
    V3: Understands class scopes.
    """
    def __init__(self):
        self.current_scope = Scope()

    def enter_scope(self, is_class_scope: bool = False):
        self.current_scope = Scope(parent=self.current_scope, is_class_scope=is_class_scope)

    def exit_scope(self):
        if self.current_scope.parent:
            self.current_scope = self.current_scope.parent

    def add_variable(self, name: str, type_info: TypeInfo):
        self.current_scope.add_variable(name, type_info)

    def lookup_variable(self, name: str) -> Optional[TypeInfo]:
        return self.current_scope.lookup_variable(name)

    def is_in_class_scope(self) -> bool:
        scope = self.current_scope
        while scope:
            if scope.is_class_scope:
                return True
            scope = scope.parent
        return False