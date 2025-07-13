# py2cy/build/pxd_generator.py
from pathlib import Path
import ast
from py2cy.models.type_defs import TypeInfo

def get_cython_type_str_for_pxd(type_info: TypeInfo) -> str:
    """
    Helper to construct the full Cython type string for PXD files.
    Pointers to C++ objects are declared directly.
    """
    base_str = type_info.cython_name
    if type_info.is_cpp_type and type_info.cpp_template_params:
        params = ", ".join([get_cython_type_str_for_pxd(p) for p in type_info.cpp_template_params])
        base_str = f"{type_info.cython_name}[{params}]"
    
    if type_info.is_pointer:
        return f"{base_str}*"
    return base_str


def generate_pxd_file(
    module_name: str,
    output_dir: Path,
    class_nodes: list[ast.ClassDef],
    cimports: set[str]
):
    """
    Generates a .pxd file for cdef classes to allow for c-level access.
    """
    if not class_nodes:
        return

    pxd_code = []
    
    # Add cimports necessary for the header
    if cimports:
        for cimport_stmt in sorted(list(cimports)):
            # Only include cimports relevant to type definitions
            if "libcpp" in cimport_stmt or "numpy" in cimport_stmt:
                pxd_code.append(cimport_stmt)
        pxd_code.append("\n")

    for node in class_nodes:
        # The transformer must have attached 'cython_attributes'
        if not hasattr(node, 'cython_attributes') or not node.cython_attributes:
            continue

        pxd_code.append(f"cdef class {node.name}:")
        for attr in node.cython_attributes:
            attr_info = attr['type_info']
            type_str = get_cython_type_str_for_pxd(attr_info)
            
            # Memoryviews can be made public for easy access from other Cython modules
            if attr_info.is_memoryview:
                pxd_code.append(f"    cdef public {type_str} {attr['name']}")
            else:
                pxd_code.append(f"    cdef {type_str} {attr['name']}")
        pxd_code.append("")

    if not any(line.strip().startswith('cdef') for line in pxd_code):
        return # Don't create an empty or import-only pxd file

    output_pxd_path = output_dir / f"{module_name}.pxd"
    output_pxd_path.write_text("\n".join(pxd_code))
    print(f"Successfully wrote PXD file to: {output_pxd_path}")