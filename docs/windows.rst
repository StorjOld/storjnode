Windows is a huge pain to get working properly.

* Install 7-zip:
	- http://www.7-zip.org/download.html
* Install python2.7 for windows
	- https://www.python.org/download/releases/2.7/ (scroll to downloads)
* Setup environmental variables
	- Right click my computer
	- properties
	- advanced system settings
	- environmental settngs
	- scroll down system settings pane until you find Path
	- append path to python.exe to path variable
* Install pip
	- https://pypi.python.org/packages/source/p/pip/pip-7.1.2.tar.gz#md5=3823d2343d9f3aaab21cf9c917710196
* Install wheel
	- python -m "pip" install wheel
* Install pycharm for Windows
* Install Git - select unix tools because they are awesome.
* Open pycharm and make new projects for these Git repos: storj/pyp2p/develop and storj/storjnode/develop
* With the projects now open in pycharm: use pycharm to automatically install all the requirment packages on Windows (its faster). Note it will fail on some packages.
* Download graphwiz installer for Windows
	- http://www.graphviz.org/Download_windows.php
* Install the graphwiz wheel:
	- python -m "wheel" install 
	- https://pypi.python.org/packages/2.7/g/graphviz/graphviz-0.4.8-py2.py3-none-any.whl#md5=8a320ee55b79013c91b3ee214ded004a
* Install Mingw
	- http://sourceforge.net/projects/mingw/files/latest/download?source=files
* Install pywin32 extension for your python version: 
	- http://sourceforge.net/projects/pywin32/files/pywin32/Build%20219/
* Install VC C++ 9.0 (if you get VC C++ 9.0 errors when trying to setup pyp2p or storjnode)
	- http://microsoft-visual-c-2008.en.softonic.com/
	(message Matthew on Slack if you don't want to use this spammy mirror)
	* Open DOS:
		- cd "C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC\bin"
		- vcvars32.bat
		- cd back to where the package is
		- now run it
		
		* Completely uninstall pycrypto
			- close all pycharm windows
			- python -m "pip" uninstall pycrypto
		* Reinstall pycrypto 2.6.1 using voicespace binaries:
			- http://www.voidspace.org.uk/python/pycrypto-2.6.1/ (get the EXE)
* Set the line endings on Windows:
	- http://stackoverflow.com/questions/2517190/how-do-i-force-git-to-use-lf-instead-of-crlf-under-windows

	
	