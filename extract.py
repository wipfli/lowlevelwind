from datetime import datetime, timedelta
from meteodatalab import ogd_api
from earthkit.data import config
from meteodatalab.operators import regrid
from meteodatalab import grib_decoder, data_source
from meteodatalab.operators.destagger import destagger
from meteodatalab.operators.vertical_interpolation import interpolate_k2any, TargetCoordinates, TargetCoordinatesAttrs

import time
import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
import numpy as np
import json
import os
import shutil
import requests
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def makeAll(reference_datetime, horizon, model, perturbed, eps):
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            collection = f'ogd-forecasting-icon-{model}'

            req_U = ogd_api.Request(
                collection=collection,
                variable="U",
                reference_datetime=reference_datetime,
                perturbed=perturbed,
                horizon=horizon,
            )

            req_V = ogd_api.Request(
                collection=collection,
                variable="V",
                reference_datetime=reference_datetime,
                perturbed=perturbed,
                horizon=horizon, 
            )

            config.set("cache-policy", "user")
            config.set("user-cache-directory", "/app/sma-cache")

            logger.info(f"Attempting to get asset URLs for horizon {horizon}")
            
            try:
                urls_U = ogd_api.get_asset_urls(req_U)
                urls_V = ogd_api.get_asset_urls(req_V)
                logger.info(f"Got URLs: {urls_U}, {urls_V}")
            except (requests.exceptions.JSONDecodeError, requests.exceptions.ConnectionError) as e:
                logger.warning(f"API request failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    raise

            da_U = ogd_api.get_from_ogd(req_U)
            da_V = ogd_api.get_from_ogd(req_V)

            url = ogd_api.get_collection_asset_url(
                collection_id=f"ch.meteoschweiz.ogd-forecasting-icon-{model}", 
                asset_id=f"vertical_constants_icon-{model}-eps.grib2"
            )

            ds = grib_decoder.load(
                source=data_source.URLDataSource(urls=[url]), 
                request={"param": "HHL"}, 
                geo_coords=lambda uuid: {}
            )

            hfl = destagger(ds["HHL"].squeeze(drop=True), "z")

            attrs = TargetCoordinatesAttrs("height_above_mean_sea_level", "height above the mean sea level", "m", "up")

            def makeAltitudes(altitudes):
                tc = TargetCoordinates("heightAboveSea", altitudes, attrs)

                U_int = interpolate_k2any(da_U, "low_fold", hfl, tc, hfl)
                V_int = interpolate_k2any(da_V, "low_fold", hfl, tc, hfl)

                xmin = 5.379264
                xmax = 11.024297
                ymin = 45.497280
                ymax = 48.105836

                nx = 429
                ny = 195

                destination = regrid.RegularGrid(
                    CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax
                )

                for i in range(len(altitudes)):
                    f_U = regrid.iconremap(U_int.isel(eps=eps, z=i), destination).squeeze()
                    f_V = regrid.iconremap(V_int.isel(eps=eps, z=i), destination).squeeze()

                    shift = 128
                    ms_to_kmh = 3.6
                    nan_value = 0

                    alpha = np.ones(f_U.values.shape)
                    alpha[np.isnan(f_U.values)] = 0
                    alpha *= 255

                    f_U_vals = f_U.values.copy()
                    f_V_vals = f_V.values.copy()

                    f_U_vals[np.isfinite(f_U_vals)] *= ms_to_kmh
                    f_U_vals[np.isfinite(f_U_vals)] += shift
                    f_U_vals[np.isnan(f_U_vals)] = nan_value

                    f_V_vals[np.isfinite(f_V_vals)] *= ms_to_kmh
                    f_V_vals[np.isfinite(f_V_vals)] += shift
                    f_V_vals[np.isnan(f_V_vals)] = nan_value

                    rgba = np.stack(
                        [
                            f_U_vals.astype(np.uint8),
                            f_V_vals.astype(np.uint8),
                            np.zeros(f_U_vals.shape).astype(np.uint8),
                            alpha.astype(np.uint8)
                        ], 
                        axis=0
                    )

                    rgba_flipped = rgba[:, ::-1, :]

                    member_filename = f'EPS{eps}' if perturbed else 'CTRL'
                    model_filename = model.upper()
                    altitude_filename = f'{altitudes[i]}M'
                    time_filename = int((reference_datetime + horizon).timestamp())
                    filename = f'data/{model_filename}-{member_filename}-{altitude_filename}-{time_filename}-wind.png'
                    
                    os.makedirs('data', exist_ok=True)
                    logger.info(f'Writing {filename}...')
                    
                    with rasterio.open(
                        filename,
                        "w",
                        driver="PNG",
                        height=f_U.shape[0],
                        width=f_U.shape[1],
                        count=4,
                        dtype=rgba.dtype,
                    ) as dst:
                        dst.write(rgba_flipped)
                        dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha]

            for altitude in list(range(600, 3050, 50)):
                makeAltitudes([altitude])
            
            return f"Successfully processed horizon {horizon}"
            
        except Exception as e:
            logger.error(f"Error processing horizon {horizon} on attempt {attempt + 1}: {e}")
            logger.error(traceback.format_exc())
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                raise

def round_down_to_last_3_hours_utc():
    now_utc = datetime.utcnow()
    hours_to_subtract = now_utc.hour % 3
    rounded_time = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_to_subtract)
    unix_timestamp = int(rounded_time.timestamp())
    return unix_timestamp

def delete_all_files_in_folder(folder):
    if not os.path.exists(folder):
        return
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                logger.warning(f"Could not remove {file_path}: {e}")

def copy_all_files(src_folder, dst_folder):
    logger.info(f'Copy files from {src_folder} to {dst_folder}...')
    os.makedirs(dst_folder, exist_ok=True)
    
    if not os.path.exists(src_folder):
        logger.warning(f"Source folder {src_folder} does not exist")
        return
    
    for filename in os.listdir(src_folder):
        src_file = os.path.join(src_folder, filename)
        dst_file = os.path.join(dst_folder, filename)
        
        if os.path.isfile(src_file):
            try:
                shutil.copy2(src_file, dst_file)
                logger.info(f'Copied {src_file} to {dst_file}.')
            except IOError as e:
                logger.error(f"Could not copy {src_file} to {dst_file}: {e}")

def check_data_availability(reference_datetime, model, perturbed, eps):
    collection = f'ogd-forecasting-icon-{model}'
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            ogd_api.get_asset_urls(ogd_api.Request(
                collection=collection,
                variable="U",
                reference_datetime=reference_datetime,
                perturbed=perturbed,
                horizon=timedelta(hours=30),
            ))
            ogd_api.get_asset_urls(ogd_api.Request(
                collection=collection,
                variable="V",
                reference_datetime=reference_datetime,
                perturbed=perturbed,
                horizon=timedelta(hours=30),
            ))
            return True
        except (ValueError, requests.exceptions.JSONDecodeError, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Data availability check failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return False

def main():
    while True:
        tic = time.time()

        last_run = ''
        try:
            with open('data/last_run.json') as f:
                last_run = json.load(f)['last_run']
        except FileNotFoundError:
            pass

        model = 'ch1'
        perturbed = False
        eps = 0

        reference_datetime = datetime.fromtimestamp(round_down_to_last_3_hours_utc())
        
        logger.info(f"Checking data availability starting from {reference_datetime}")
        
        while True:
            if check_data_availability(reference_datetime, model, perturbed, eps):
                break
            reference_datetime -= timedelta(hours=3)
            logger.info(f"Data not available, trying {reference_datetime}")

        latest_available_run = int(reference_datetime.timestamp())

        if last_run == latest_available_run:
            sleep_min = 1
            logger.info(f'No new run available. Sleep for {sleep_min} min...')
            time.sleep(sleep_min * 60)
            continue
        
        logger.info(f'Found new run {reference_datetime}...')
        delete_all_files_in_folder('data')
        
        num_threads = 4
        logger.info(f"Starting parallel tasks with {num_threads} threads...")
        
        successful_tasks = 0
        failed_tasks = 0
        
        with ProcessPoolExecutor(max_workers=num_threads) as executor:
            hours_list = range(0, 31, 1)
            horizons = [timedelta(hours=hours) for hours in hours_list]
            
            future_to_horizon = {
                executor.submit(makeAll, reference_datetime, horizon, model, perturbed, eps): horizon 
                for horizon in horizons
            }
            
            for future in as_completed(future_to_horizon):
                horizon = future_to_horizon[future]
                try:
                    result = future.result()
                    logger.info(f"Completed: {result}")
                    successful_tasks += 1
                except Exception as e:
                    logger.error(f"Task for horizon {horizon} failed: {e}")
                    failed_tasks += 1
        
        logger.info(f"Completed with {successful_tasks} successful and {failed_tasks} failed tasks")
        
        if successful_tasks > 0:
            try:
                with open('data/last_run.json', 'w') as f:
                    json.dump({"last_run": latest_available_run}, f)
                
                copy_all_files('data', '/var/www/html/data-copy/')
            except Exception as e:
                logger.error(f"Error in post-processing: {e}")
        
        delete_all_files_in_folder('sma-cache')
        logger.info(f'Finished in {(time.time() - tic) / 60:.2f} min')

if __name__ == "__main__":
    main()