from setuptools import setup, Extension
from Cython.Build import cythonize

ext_modules = [
    Extension(
        "last",
        ["last.pyx"],
        language="c++"
    )
]

setup(
    name='last_module',
    ext_modules=cythonize(ext_modules, compiler_directives={"language_level": "3"})
)