from setuptools import setup, find_packages
setup(
    name="DeepBDE-Api",
    version="0.1.0",
    description="API y herramientas para DeepBDE WebApp",
    author="chem-gl",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        req.strip() for req in open("requirements.txt") if req.strip() and not req.startswith("#")
    ],
    python_requires='>=3.7',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Framework :: Django",
        "Operating System :: OS Independent",
    ],
)