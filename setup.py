#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""
from setuptools import setup, find_packages

try:
    from sphinx.setup_command import BuildDoc

    cmdclass = {"build_sphinx": BuildDoc}
except ImportError:
    # sphinx not installed - do not provide build_sphinx cmd
    cmdclass = {}


with open("README.rst") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst", "rb") as history_file:
    # Norwegian characters in HISTORY.rst
    history = history_file.read().decode("UTF-8")

REQUIREMENTS = [
    "numpy",
    "pandas>0.23.0",
    "pyyaml>=5.1",
    "six>=1.12.0",
]

SETUP_REQUIREMENTS = ["setuptools>=28", "setuptools_scm"]

TEST_REQUIREMENTS = [
    "black; python_version >= '3'",
    "flake8>=2.6.0",
    "pylint",
    "pytest>=2.9.2",
    "pyyaml>=5.1",
    "sphinx>=1.4.8",
    "sphinx_rtd_theme>=0.4.1",
]

EXTRAS_REQUIRE = {"tests": TEST_REQUIREMENTS, "parquet": ["pyarrow"]}

setup(
    name="fmu-ensemble",
    use_scm_version={"write_to": "src/fmu/ensemble/version.py"},
    cmdclass=cmdclass,
    description="Python API to ensembles produced by ERT",
    long_description=readme + "\n\n" + history,
    author="Håvard Berland",
    author_email="havb@equinor.com",
    url="https://github.com/equinor/fmu-ensemble",
    license="GPLv3",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=REQUIREMENTS,
    zip_safe=False,
    keywords="fmu, ensemble",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    test_suite="tests",
    tests_require=TEST_REQUIREMENTS,
    setup_requires=SETUP_REQUIREMENTS,
    extras_require=EXTRAS_REQUIRE,
)
