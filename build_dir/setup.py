from setuptools import setup, Extension
from Cython.Build import cythonize

ext_modules = [
    Extension(
        "final",
        ["final.pyx"],
        language="c++"
    )
]

setup(
    name='final_module',
    ext_modules=cythonize(ext_modules, compiler_directives={"language_level": "3"})
)