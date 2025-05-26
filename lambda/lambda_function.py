import json
import boto3
from datetime import datetime
from io import BytesIO

from datetime import datetime, timedelta
from meteodatalab import ogd_api
from earthkit.data import config
from meteodatalab.operators import regrid

import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
import numpy as np

def lambda_handler(event, context):
    try:

        s3_client = boto3.client('s3')
        bucket_name = 'swiss-map'  # Replace with your actual bucket name

        def makeAll(reference_datetime, horizon, model, perturbed, eps):
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
            config.set("user-cache-directory", "/tmp/sma-cache")

            print(ogd_api.get_asset_url(req_U))
            print(ogd_api.get_asset_url(req_V))

            da_U = ogd_api.get_from_ogd(req_U)
            da_V = ogd_api.get_from_ogd(req_V)

            # url = ogd_api.get_collection_asset_url(
            #     collection_id=f"ch.meteoschweiz.ogd-forecasting-icon-{model}", 
            #     asset_id=f"vertical_constants_icon-{model}-eps.grib2"
            # )

            # ds = grib_decoder.load(
            #     source=data_source.URLDataSource(urls=[url]), 
            #     request={"param": "HHL"}, 
            #     geo_coords=lambda uuid: {}
            # )

            # hfl = destagger(ds["HHL"].squeeze(drop=True), "z")

            # attrs = TargetCoordinatesAttrs("height_above_mean_sea_level", "height above the mean sea level", "m", "up")
            def makeLevels(levels):
                # tc = TargetCoordinates("heightAboveSea", [1500], attrs)

                # U_int = interpolate_k2any(da_U, "low_fold", hfl, tc, hfl)
                # V_int = interpolate_k2any(da_V, "low_fold", hfl, tc, hfl)

                xmin = 5.379264
                xmax = 11.024297
                ymin = 45.497280
                ymax = 48.105836

                nx = 429
                ny = 195

                destination = regrid.RegularGrid(
                    CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax
                )

                for level in levels:
                    f_U = regrid.iconremap(da_U.isel(eps=eps, z=level), destination).squeeze()
                    f_V = regrid.iconremap(da_V.isel(eps=eps, z=level), destination).squeeze()

                    shift = 128
                    ms_to_kmh = 3.6
                    nan_value = 0

                    alpha = np.ones(f_U.values.shape)
                    alpha[np.isnan(f_U.values)] = 0
                    alpha *= 255

                    f_U.values[np.isfinite(f_U.values)] *= ms_to_kmh
                    f_U.values[np.isfinite(f_U.values)] += shift
                    f_U.values[np.isnan(f_U.values)] = nan_value

                    f_V.values[np.isfinite(f_V.values)] *= ms_to_kmh
                    f_V.values[np.isfinite(f_V.values)] += shift
                    f_V.values[np.isnan(f_V.values)] = nan_value

                    rgba = np.stack(
                        [
                            f_U.values.astype(np.uint8),
                            f_V.values.astype(np.uint8),
                            np.zeros(f_U.values.shape).astype(np.uint8),
                            alpha.astype(np.uint8)
                        ], 
                        axis=0
                    )

                    rgba_flipped = rgba[:, ::-1, :]

                    member_filename = f'EPS{eps}' if perturbed else 'CTRL'
                    model_filename = model.upper()
                    level_filename = f'Z{level}'
                    time_filename = int((reference_datetime + horizon).timestamp())
                    # CH1-CTRL-650M-1747818000-wind.png
                    filename = f'{model_filename}-{member_filename}-{level_filename}-{time_filename}-wind.png'
                    print(f'Writing {filename}...')
                    with BytesIO() as buffer:
                        with rasterio.MemoryFile() as memfile:
                            with memfile.open(
                                driver="PNG",
                                height=f_U.shape[0],
                                width=f_U.shape[1],
                                count=4,
                                dtype=rgba.dtype,
                            ) as dst:
                                dst.write(rgba_flipped)
                                dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha]

                            # Write to buffer
                            buffer.write(memfile.read())
                            buffer.seek(0)

                            s3_client.upload_fileobj(buffer, Bucket=bucket_name, Key=filename, ExtraArgs={'ContentType': 'image/png'})

            # for altitude in list(range(600, 3050, 50)):
            makeLevels([int(event.get('level', 0))])

        def round_down_to_last_3_hours_utc():
            now_utc = datetime.utcnow()
            hours_to_subtract = now_utc.hour % 3
            rounded_time = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_to_subtract)
            unix_timestamp = int(rounded_time.timestamp())
            return unix_timestamp

        model = 'ch1'
        perturbed = False
        eps = 0
        collection = f'ogd-forecasting-icon-{model}'

        reference_datetime = datetime.fromtimestamp(round_down_to_last_3_hours_utc())
        while True:
            try:
                ogd_api.get_asset_url(ogd_api.Request(
                    collection=collection,
                    variable="U",
                    reference_datetime=reference_datetime,
                    perturbed=perturbed,
                    horizon=timedelta(hours=30),
                ))
                ogd_api.get_asset_url(ogd_api.Request(
                    collection=collection,
                    variable="V",
                    reference_datetime=reference_datetime,
                    perturbed=perturbed,
                    horizon=timedelta(hours=30),
                ))
            except ValueError as e:
                reference_datetime -= timedelta(hours=3)
                continue
            break

        latest_available_run = int(reference_datetime.timestamp())

        horizon = timedelta(hours=0)
        makeAll(reference_datetime, horizon, model, perturbed, eps)

        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully created ... in bucket {bucket_name}',
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