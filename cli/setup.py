from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="clinical-matcher-cli",
    version="1.0.0",
    author="Clinical Disease Matcher Team",
    author_email="",
    description="CLI инструмент для сопоставления клинических диагнозов с кодами OMIM/MONDO",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/clinical-disease-matcher",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Healthcare Industry",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pandas>=1.5.0",
        "openpyxl>=3.0.0",
        "aiohttp>=3.8.0",
        "rapidfuzz>=3.0.0",
        "numpy>=1.20.0",
        "click>=8.0.0",
    ],
    entry_points={
        'console_scripts': [
            'clinical-matcher=clinical_matcher.cli:main',
        ],
    },
    include_package_data=True,
)