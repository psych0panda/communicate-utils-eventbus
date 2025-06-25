from os.path import dirname, join

from setuptools import setup

PACKAGE_INFO = {}
with open(
        join(
            dirname(__file__),
            "src",
            "communicate",
            "utils",
            "eventbus",
            "version.py",
        )
) as fh:
    exec(fh.read(), PACKAGE_INFO)

setup(version=PACKAGE_INFO["__version__"])
