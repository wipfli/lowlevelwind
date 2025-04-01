#!/bin/bash

set -e  # Stop on error

PYTHON_VERSION="3.11"

echo " Installing pyenv..."
if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
else
    echo "pyenv already installed."
fi

# Update shell config
# so that every time you open a new terminal, pyenv is available in your PATH
if ! grep -q 'pyenv init' ~/.bashrc; then
    echo " Adding pyenv to ~/.bashrc"
    cat <<EOF >> ~/.bashrc

# Pyenv setup
export PATH="\$HOME/.pyenv/bin:\$PATH"
# Allow python, pip, etc. to point to the correct version of Python managed by pyenv
eval "\$(pyenv init --path)"
EOF
fi

# Apply changes to current session
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init --path)"

echo " Installing Python $PYTHON_VERSION with pyenv..."
if ! pyenv versions --bare | grep -q "^$PYTHON_VERSION\$"; then
    pyenv install $PYTHON_VERSION
else
    echo "Python $PYTHON_VERSION already installed in pyenv."
fi

echo " Setting Python $PYTHON_VERSION as local version..."
pyenv local $PYTHON_VERSION

echo "Done! Python version now:"
python --version
