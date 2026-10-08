#!/usr/bin/env bash

#
# The script will prepare the project environment for development.
# Run this script from the project root directory.
#
# Usage:
#     $ cd path/to/project
#     $ . ./scripts/setup
#

echo "Creating virtualenv (.venv/) in project..."

if command -v poetry >/dev/null 2>&1;then
    echo "Poetry found. Using poetry..." 
    poetry config --local virtualenvs.in-project true

    echo "Installing package dependencies..."
    poetry install
    PYTHON_CMD="poetry run python"
    PRE_COMMIT_CMD="poetry run pre-commit"
else
    echo "Poetry not found. Using the default python virtual environment..."
    if [ ! -d ".venv" ];then
        python3 -m venv .venv
    fi
    echo "Activating virtual environment..."
    source .venv/bin/activate
    python3 -m pip install --upgrade pip
    echo "Installing package dependencices..."
    pip install -r requirements.txt

    PYTHON_CMD="python3"
    PRE_COMMIT_CMD="pre-commit"
fi

if [ ! -d ".git" ]; then
    git init
fi

echo "Installing pre-commit hooks..."
$PRE_COMMIT_CMD install -t pre-commit
$PRE_COMMIT_CMD install -t pre-push

echo "Using local CA to sign certs..."
if [ ! -d ".certs" ]; then
    mkdir .certs
fi
$PYTHON_CMD -m trustme -d .certs/
