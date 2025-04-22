import logging
from pathlib import Path
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
import nbformat

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')


KERNEL_NAME = "notebooks-nwp-env"
ROOT_DIR = Path(__file__).resolve().parent
NOTEBOOK_DIRS = [ROOT_DIR, ROOT_DIR / "clean_notebooks"]

def run_notebook(notebook_path):
    with open(notebook_path) as f:
        nb = nbformat.read(f, as_version=4)

    # configure the notebook execution mode
    ep = ExecutePreprocessor(timeout=600, kernel_name=KERNEL_NAME)

    try:
        # run the notebook
        ep.preprocess(nb, {'metadata': {'path': notebook_path.parent}})
        logger.info(f"Notebook ran successfully: {notebook_path}")
    except CellExecutionError as e:
        logger.error(f"Error in notebook: {notebook_path}")
        logger.exception(e)

def main():
    for directory in NOTEBOOK_DIRS:
        for nb_path in directory.glob("*.ipynb"):
            run_notebook(nb_path)

if __name__ == "__main__":
    main()
