
repo=localhost
user=pypiadmin
password=pypiadmin

install:
	python -m pip install -U pip
	pip install -i http://$(repo):8036 --trusted-host $(repo) -U --pre -r test_requirements.txt

.PHONY: build
build:
	shellfoundry install

download:
	pip download -i http://$(repo):8036 --trusted-host $(repo) --pre -r src/requirements.txt -d dist/downloads
