import os
from setuptools import setup, find_packages

# Load the README.md
from pathlib import Path
here = Path(__file__).parent
long_description = (here / "README.md").read_text()

# Load the requirements file in here to avoid duplication
with open("./requirements.txt", "r") as req_file:
    requirements = [r for r in req_file.readlines() if r.strip()]

setup(
    name='MiGreat-cli',
    version='0.1.2',
    packages=find_packages(),
    author='Philip Stefou',
    author_email='hashibuto@noreply.com',
    description='A schema isolated SQLAlchemy migrator for shared Postgres db micro services',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/hashibuto/MiGreat",
    scripts=[
        "migreat/bin/migreat"
    ],
    install_requires=requirements,
    python_requires='>=3.8',
)
