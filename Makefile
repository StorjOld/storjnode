PY_VERSION := 2.7
WHEEL_DIR := /tmp/wheelhouse
PIP := env/bin/pip
PY := env/bin/python
PEP8 := env/bin/pep8
COVERAGE := env/bin/coverage
USE_WHEELS := 0
ifeq ($(USE_WHEELS), 0)
  WHEEL_INSTALL_ARGS := # void
else
  WHEEL_INSTALL_ARGS := --use-wheel --no-index --find-links=$(WHEEL_DIR)
endif
export PYCOIN_NATIVE=openssl
export STORJNODE_QUERY_TIMEOUT=3.0
#export STORJNODE_ENABLE_GLOBAL_LOGGER=1


help:
	@echo "COMMANDS:"
	@echo "  clean          Remove all generated files."
	@echo "  setup          Setup development environment."
	@echo "  shell          Open ipython from the development environment."
	@echo "  test           Run tests."
	@echo "  lint           Run analysis tools."
	@echo "  wheel          Build package wheel & save in $(WHEEL_DIR)."
	@echo "  wheels         Build dependency wheels & save in $(WHEEL_DIR)."
	@echo "  publish        Build and upload package to pypi.python.org"
	@echo ""
	@echo "VARIABLES:"
	@echo "  PY_VERSION     Version of python to use. 2 or 3"
	@echo "  WHEEL_DIR      Where you save your wheels. Default: $(WHEEL_DIR)."
	@echo "  USE_WHEELS     Install packages from wheel dir, off by default."


clean:
	rm -rf env
	rm -rf build
	rm -rf dist
	rm -rf *.egg
	rm -rf *.egg-info
	find | grep -i ".*\.pyc$$" | xargs -r -L1 rm


virtualenv: clean
	virtualenv -p /usr/bin/python$(PY_VERSION) env
	$(PIP) install wheel


wheels: virtualenv
	$(PIP) wheel --find-links=$(WHEEL_DIR) --wheel-dir=$(WHEEL_DIR) -r requirements.txt
	$(PIP) wheel --find-links=$(WHEEL_DIR) --wheel-dir=$(WHEEL_DIR) -r test_requirements.txt
	$(PIP) wheel --find-links=$(WHEEL_DIR) --wheel-dir=$(WHEEL_DIR) -r develop_requirements.txt


wheel: setup
	$(PY) setup.py bdist_wheel
	mv dist/*.whl $(WHEEL_DIR)


setup: virtualenv
	$(PIP) install $(WHEEL_INSTALL_ARGS) -r requirements.txt
	$(PIP) install $(WHEEL_INSTALL_ARGS) -r test_requirements.txt
	$(PIP) install $(WHEEL_INSTALL_ARGS) -r develop_requirements.txt


install: setup
	$(PY) setup.py install


test_script: install
	#$(PY) examples/network/map_network.py --debug
	$(PY) -m unittest --verbose tests.network.node.TestNode
	#env/bin/storjnode --wallet=L3NrSTxMCwAsLXnBjESvU5LnCKwcmMXKutKzNnVpPevXeSMfB1zx farm
	#env/bin/storjnode_bootstrap_only --wallet=L3NrSTxMCwAsLXnBjESvU5LnCKwcmMXKutKzNnVpPevXeSMfB1zx --port=1337


shell: install
	env/bin/ipython


test: setup
	$(PEP8) storjnode
	$(PEP8) examples
	$(PEP8) tests
	$(COVERAGE) run --source="storjnode" -m unittest --quiet tests
	$(COVERAGE) report --fail-under=85


publish: test
	$(PY) setup.py register bdist_wheel upload


# Break in case of bug!
# import pudb; pu.db
