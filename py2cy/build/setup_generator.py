from pathlib import Path

SETUP_TEMPLATE = """
from setuptools import setup, Extension
from Cython.Build import cythonize

# To compile, run:
# python setup.py build_ext --inplace

ext_modules = [
    Extension(
        "{module_name}",
        ["{module_name}.pyx"],
        language="{language}"
    )
]

setup(
    name='{module_name}_module',
    ext_modules=cythonize(
        ext_modules,
        compiler_directives={{'language_level': "3"}},
        quiet=True
    ),
)
"""

def generate_setup_file(module_name: str, output_dir: Path, use_cpp: bool):
    """Generates a setup.py file for compiling the Cython module."""
    language = "c++" if use_cpp else "c"
    
    setup_content = SETUP_TEMPLATE.format(
        module_name=module_name,
        language=language
    )
    
    setup_path = output_dir / "setup.py"
    setup_path.write_text(setup_content)
    print(f"Generated build script: {setup_path}")