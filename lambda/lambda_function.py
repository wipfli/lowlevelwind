import json
import boto3
from datetime import datetime, timedelta
from io import BytesIO

from meteodatalab import ogd_api
from earthkit.data import config
from meteodatalab.operators import regrid

import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
import numpy as np


class WeatherDataProcessor:
    def __init__(self, bucket_name='swiss-map'):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
        self.grid_config = {
            'xmin': 5.379264,
            'xmax': 11.024297,
            'ymin': 45.497280,
            'ymax': 48.105836,
            'nx': 429,
            'ny': 195
        }
        self.wind_config = {
            'shift': 128,
            'ms_to_kmh': 3.6,
            'nan_value': 0
        }
        self._setup_cache()
    
    def _setup_cache(self):
        config.set("cache-policy", "user")
        config.set("user-cache-directory", "/tmp/sma-cache")
    
    def _create_ogd_requests(self, collection, reference_datetime, perturbed, horizon):
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
        
        return req_U, req_V
    
    def _fetch_wind_data(self, req_U, req_V):
        print(ogd_api.get_asset_url(req_U))
        print(ogd_api.get_asset_url(req_V))
        
        da_U = ogd_api.get_from_ogd(req_U)
        da_V = ogd_api.get_from_ogd(req_V)
        
        return da_U, da_V
    
    def _create_destination_grid(self):
        return regrid.RegularGrid(
            CRS.from_string("epsg:4326"),
            self.grid_config['nx'],
            self.grid_config['ny'],
            self.grid_config['xmin'],
            self.grid_config['xmax'],
            self.grid_config['ymin'],
            self.grid_config['ymax']
        )
    
    def _process_wind_values(self, wind_data):
        wind_data.values[np.isfinite(wind_data.values)] *= self.wind_config['ms_to_kmh']
        wind_data.values[np.isfinite(wind_data.values)] += self.wind_config['shift']
        wind_data.values[np.isnan(wind_data.values)] = self.wind_config['nan_value']
        return wind_data
    
    def _create_alpha_channel(self, f_U):
        alpha = np.ones(f_U.values.shape)
        alpha[np.isnan(f_U.values)] = 0
        alpha *= 255
        return alpha
    
    def _create_rgba_array(self, f_U, f_V, alpha):
        rgba = np.stack([
            f_U.values.astype(np.uint8),
            f_V.values.astype(np.uint8),
            np.zeros(f_U.values.shape).astype(np.uint8),
            alpha.astype(np.uint8)
        ], axis=0)
        
        return rgba[:, ::-1, :]
    
    def _generate_filename(self, model, perturbed, eps, level, reference_datetime, horizon):
        member_filename = f'EPS{eps}' if perturbed else 'CTRL'
        model_filename = model.upper()
        level_filename = f'Z{level}'
        time_filename = int((reference_datetime + horizon).timestamp())
        return f'{model_filename}-{member_filename}-{level_filename}-{time_filename}-wind.png'
    
    def _save_to_s3(self, rgba_data, filename, height, width):
        with BytesIO() as buffer:
            with rasterio.MemoryFile() as memfile:
                with memfile.open(
                    driver="PNG",
                    height=height,
                    width=width,
                    count=4,
                    dtype=rgba_data.dtype,
                ) as dst:
                    dst.write(rgba_data)
                    dst.colorinterp = [
                        ColorInterp.red,
                        ColorInterp.green,
                        ColorInterp.blue,
                        ColorInterp.alpha
                    ]
                
                buffer.write(memfile.read())
                buffer.seek(0)
                
                self.s3_client.upload_fileobj(
                    buffer,
                    Bucket=self.bucket_name,
                    Key=filename,
                    ExtraArgs={'ContentType': 'image/png'}
                )
    
    def process_level(self, da_U, da_V, level, eps, model, perturbed, reference_datetime, horizon):
        destination = self._create_destination_grid()
        
        f_U = regrid.iconremap(da_U.isel(eps=eps, z=level), destination).squeeze()
        f_V = regrid.iconremap(da_V.isel(eps=eps, z=level), destination).squeeze()
        
        alpha = self._create_alpha_channel(f_U)
        
        f_U = self._process_wind_values(f_U)
        f_V = self._process_wind_values(f_V)
        
        rgba_flipped = self._create_rgba_array(f_U, f_V, alpha)
        
        filename = self._generate_filename(model, perturbed, eps, level, reference_datetime, horizon)
        print(f'Writing {filename}...')
        
        self._save_to_s3(rgba_flipped, filename, f_U.shape[0], f_U.shape[1])
    
    def process_levels(self, da_U, da_V, levels, eps, model, perturbed, reference_datetime, horizon):
        for level in levels:
            self.process_level(da_U, da_V, level, eps, model, perturbed, reference_datetime, horizon)
    
    def process_weather_data(self, reference_datetime, horizon, model, perturbed, eps, levels):
        collection = f'ogd-forecasting-icon-{model}'
        
        req_U, req_V = self._create_ogd_requests(collection, reference_datetime, perturbed, horizon)
        da_U, da_V = self._fetch_wind_data(req_U, req_V)
        
        self.process_levels(da_U, da_V, levels, eps, model, perturbed, reference_datetime, horizon)


class WeatherDataValidator:
    @staticmethod
    def round_down_to_last_3_hours_utc():
        now_utc = datetime.utcnow()
        hours_to_subtract = now_utc.hour % 3
        rounded_time = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_to_subtract)
        return int(rounded_time.timestamp())
    
    @staticmethod
    def find_latest_available_run(model, perturbed):
        collection = f'ogd-forecasting-icon-{model}'
        reference_datetime = datetime.fromtimestamp(WeatherDataValidator.round_down_to_last_3_hours_utc())
        
        while True:
            try:
                for variable in ["U", "V"]:
                    ogd_api.get_asset_url(ogd_api.Request(
                        collection=collection,
                        variable=variable,
                        reference_datetime=reference_datetime,
                        perturbed=perturbed,
                        horizon=timedelta(hours=30),
                    ))
                break
            except ValueError:
                reference_datetime -= timedelta(hours=3)
                continue
        
        return reference_datetime


def lambda_handler(event, context):
    try:
        processor = WeatherDataProcessor()
        validator = WeatherDataValidator()
        
        model = 'ch1'
        perturbed = False
        eps = 0
        
        reference_datetime = validator.find_latest_available_run(model, perturbed)
        horizon = timedelta(hours=0)
        levels = [int(event.get('level', 0))]
        
        processor.process_weather_data(reference_datetime, horizon, model, perturbed, eps, levels)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully created files in bucket {processor.bucket_name}',
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Failed to create file: {str(e)}'
            })
        }