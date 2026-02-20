#!/usr/bin/env python3
"""Setup script for VibeBuild."""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8", errors="ignore") if (here / "README.md").exists() else ""

setup(
    name="vibebuild",
    version="0.1.0",
    description="Koji extension for automatic dependency resolution and building",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="VibeBuild Team",
    author_email="vibebuild@example.com",
    url="https://github.com/vibebuild/vibebuild",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
        "Topic :: System :: Software Distribution",
    ],
    keywords="koji, rpm, srpm, build, fedora, dependency",
    packages=find_packages(exclude=["tests", "tests.*", "docs"]),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.25.0",
    ],
    extras_require={
        "ml": [
            "scikit-learn>=1.3",
            "joblib>=1.3",
        ],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "isort>=5.12",
            "mypy>=1.0",
            "flake8>=6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "vibebuild=vibebuild.cli:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/vibebuild/vibebuild/issues",
        "Source": "https://github.com/vibebuild/vibebuild",
        "Documentation": "https://github.com/vibebuild/vibebuild/docs",
    },
)
