# setup.py
from setuptools import setup
from Cython.Build import cythonize
from pathlib import Path
pwd = Path(__file__).parent
filepath = str(pwd/"proxy_core.pyx")
setup(
    ext_modules = cythonize(filepath,build_dir=str(pwd/"build"))
)
