<h1 align="center">OGD Model Data Access & Processing</h1>
<h3 align="center">Jupyter Notebook Examples Using MeteoSwiss NWP Data</h3>

<p align="center">
  <img src="images/logo_mch.png" alt="MCH Logo" width="130" />
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="images/logo_opendata.jpeg" alt="Open Data Logo" width="130" />
</p>

This repository provides Jupyter notebook examples for accessing and processing numerical weather prediction (NWP) model data from **MeteoSwiss**, released through Switzerland’s **Open Government Data (OGD)** initiative.

---

## 📓 Example Notebooks

- [**01_retrieve_process_precip.ipynb**](01_retrieve_process_precip.ipynb) - Retrieve, process, and visualize ensemble precipitation forecasts from the ICON model.

## 🚀 Getting Started

### Install Dependencies

Clone the repository and install all required packages using:

 1. **Install ecCodes using conda**
    ```bash
    bash install_eccodes.sh
    ```

2. **Install Python dependencies using Poetry**
    ```bash
    poetry install
    ```

3. **Install the Jupyter kernel**  
    Activate the Poetry environment and install the current environment as a Jupyter kernel:
    ```bash
    poetry shell
    poetry run python -m ipykernel install --user --name=notebooks-nwp-env --display-name "Python (notebooks-nwp-env)"
    ```
4. **Use the Kernel in Jupyter**   
    After launching Jupyter, select the custom kernel by navigating to Kernel → Change Kernel → Python (notebooks-nwp-env) in the notebook interface.

## 📚 Related Documentation

For more context on the available numerical weather forecast data and how it’s structured, see:

  🔗 [MeteoSwiss Forecast Data Documentation](https://github.com/MeteoSwiss/opendata-forecast-data/blob/main/README.md#2-numerical-weather-forecasting-model-data)

## 💬 Feedbacks
Feel free to open issues to suggest improvements or contribute new examples!

