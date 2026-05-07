#!/usr/bin/env bash

set -e
set -x

ruff check src/nextcloud_cli
mypy src/nextcloud_cli
