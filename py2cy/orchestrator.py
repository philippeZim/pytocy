# py2cy/orchestrator.py
import ast
from pathlib import Path
from py2cy.config import AppConfig
from py2cy.core.symbol_table import SymbolTable
from py2cy.core.transformer import CythonASTTransformer
from py2cy.core.code_generator import CythonCodeGenerator
# from py2cy.build.setup_generator import generate_setup_file # Assuming this exists
from py2cy.build.pxd_generator import generate_pxd_file

# Placeholder for the setup generator if it doesn't exist in the provided code
def generate_setup_file(module_name: str, output_dir: Path, use_cpp: bool):
    language = '"c++"' if use_cpp else 'None'
    setup_content = f"""
from setuptools import setup, Extension
from Cython.Build import cythonize

ext_modules = [
    Extension(
        "{module_name}",
        ["{module_name}.pyx"],
        language={language}
    )
]

setup(
    name='{module_name}_module',
    ext_modules=cythonize(ext_modules, compiler_directives={{"language_level": "3"}})
)
"""
    setup_path = output_dir / "setup.py"
    setup_path.write_text(setup_content.strip())
    print(f"Successfully wrote setup file to: {setup_path}")


class TranspilationPipeline:
    def __init__(self, input_path: Path, output_dir: Path, config: AppConfig):
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config
        self.module_name = input_path.stem

    def run(self):
        print(f"Starting V3 transpilation for {self.input_path}...")
        source_code = self.input_path.read_text()
        py_ast = ast.parse(source_code)
        
        symbol_table = SymbolTable()
        transformer = CythonASTTransformer(symbol_table)
        transformed_ast = transformer.visit(py_ast)
        print("AST analysis and transformation complete.")
        
        if transformer.uses_cpp:
            print("C++ types detected. Will generate C++-compatible build script.")
        
        code_gen = CythonCodeGenerator()
        cython_code = code_gen.generate(
            transformed_ast,
            self.config.compiler_directives,
            transformer.required_cimports
        )
        print("Cython code generation complete.")
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_pyx_path = self.output_dir / f"{self.module_name}.pyx"
        output_pyx_path.write_text(cython_code)
        print(f"Successfully wrote Cython file to: {output_pyx_path}")

        # --- NEW: Generate the .pxd file ---
        generate_pxd_file(
            self.module_name,
            self.output_dir,
            transformer.class_nodes,
            transformer.required_cimports
        )

        generate_setup_file(self.module_name, self.output_dir, transformer.uses_cpp)