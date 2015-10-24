#!/usr/bin/python
# coding: utf-8


import os
import sys
from setuptools import setup, find_packages


# Only load py2exe settings when its used, so we can install it first.
options = {}
if os.name == 'nt' and 'py2exe' in sys.argv:
    import py2exe  # NOQA
    options = {'py2exe': {
        "optimize": 2,
        "bundle_files": 2,  # This tells py2exe to bundle everything
    }}


exec(open('storjnode/version.py').read())  # load __version__
SCRIPT = os.path.join('storjnode', 'bin', 'storjnode')
DOWNLOAD_URL = "%(baseurl)s/%(name)s/%(name)s-%(version)s-py2-none-any.whl" % {
    'baseurl': "https://pypi.python.org/packages/3.4/d",
    'name': 'storjnode',
    'version': __version__  # NOQA
}


setup(
    name='storjnode',
    description="Low level storj protocol reference implementation.",
    long_description=open("README.rst").read(),
    keywords="storj, reference, protocol, DHT",
    url='http://storj.io',
    author='Shawn Wilkinson',
    author_email='shawn+storjnode@storj.io',
    license="MIT",
    version=__version__,  # NOQA
    scripts=[SCRIPT],
    console=[SCRIPT],
    test_suite="tests",
    dependency_links=[],
    install_requires=open("requirements.txt").readlines(),
    tests_require=open("test_requirements.txt").readlines(),
    download_url=DOWNLOAD_URL,
    packages=find_packages(exclude=['storjnode.bin']),
    classifiers=[
        # "Development Status :: 1 - Planning",
        # "Development Status :: 2 - Pre-Alpha",
        "Development Status :: 3 - Alpha",
        # "Development Status :: 4 - Beta",
        # "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        #"Programming Language :: Python :: 3",
        #"Programming Language :: Python :: 3.3",
        #"Programming Language :: Python :: 3.4",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    options=options
)
