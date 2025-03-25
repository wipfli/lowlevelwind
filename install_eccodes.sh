#!/bin/bash

# ========= CONFIG ==========
ENV_NAME=eccodes_env
ECCODES_VERSION=2.36.0
INSTALL_PREFIX="${HOME}/tools"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-py310_22.11.1-1-Linux-x86_64.sh"
SHA256="00938c3534750a0e4069499baf8f4e6dc1c2e471c86a59caa0dd03f4a9269db6"
# ===========================

set -e


# Check if conda exists
if ! command -v conda &> /dev/null; then
  echo "Installing Miniconda in $INSTALL_PREFIX ..."
  mkdir -p "$INSTALL_PREFIX"
  wget -O "$INSTALL_PREFIX/miniconda.sh" "$MINICONDA_URL"
  echo "$SHA256  $INSTALL_PREFIX/miniconda.sh" | sha256sum --check || exit 1
  bash "$INSTALL_PREFIX/miniconda.sh" -b -p "$INSTALL_PREFIX/miniconda"
  source "$INSTALL_PREFIX/miniconda/etc/profile.d/conda.sh"
  conda config --set always_yes yes --set changeps1 no
  conda config --add channels conda-forge
  conda init bash
  rm "$INSTALL_PREFIX/miniconda.sh"
else
  echo "Found existing conda at: $(which conda)"
  source "$(conda info --base)/etc/profile.d/conda.sh"
fi

# Create environment and install eccodes
echo "Creating environment '$ENV_NAME' with eccodes=$ECCODES_VERSION ..."
conda create -n "$ENV_NAME" eccodes="$ECCODES_VERSION" -c conda-forge

# Get the full path to the environment
ENV_PATH=$(conda env list | grep "$ENV_NAME" | awk '{print $2}')

echo "Environment created at: $ENV_PATH"
echo ""
echo "In your notebook, set:"
echo "    os.environ[\"ECCODES_DIR\"] = \"$ENV_PATH\""
