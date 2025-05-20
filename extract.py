from datetime import datetime, timezone, timedelta
from meteodatalab import ogd_api
from earthkit.data import config
from meteodatalab.operators import regrid, vertical_interpolation
from meteodatalab.operators.vertical_interpolation import interpolate_k2p

print(dir(vertical_interpolation))
exit()
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
import numpy as np


reference_datetime = datetime(2025, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
horizon = timedelta(hours=6)
perturbed = False
collection = "ogd-forecasting-icon-ch2"
z = 70
eps = 0

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

req_P = ogd_api.Request(
    collection=collection,
    variable="P",
    reference_datetime=reference_datetime,
    perturbed=perturbed,
    horizon=horizon, 
)

config.set("cache-policy", "temporary")

da_U = ogd_api.get_from_ogd(req_U)
da_V = ogd_api.get_from_ogd(req_V)
da_P = ogd_api.get_from_ogd(req_P)

def flight_level_to_hpa(flight_level: int) -> float:
    altitude_ft = flight_level * 100
    pressure_hpa = 1013.25 * (1 - (altitude_ft / 145366.45)) ** 5.255
    return pressure_hpa


target_levels = [flight_level_to_hpa(28)]
print(target_levels)

U_int = interpolate_k2p(field=da_U, mode="linear_in_lnp", p_field=da_P, p_tc_values=target_levels, p_tc_units='hPa')
V_int = interpolate_k2p(field=da_V, mode="linear_in_lnp", p_field=da_P, p_tc_values=target_levels, p_tc_units='hPa')


xmin = 5.379264
xmax = 11.024297
ymin = 45.497280
ymax = 48.105836

nx = 429
ny = 195

destination = regrid.RegularGrid(
    CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax
)

xres = (destination.xmax - destination.xmin) / destination.nx
yres = (destination.ymax - destination.ymin) / destination.ny

transform = from_origin(destination.xmin, destination.ymin, xres, -yres)

f_U = regrid.iconremap(U_int.isel(eps=eps, z=0), destination).squeeze()
f_V = regrid.iconremap(V_int.isel(eps=eps, z=0), destination).squeeze()

shift = 128
f_U.values[np.isnan(f_U.values)] = 0
f_V.values[np.isnan(f_V.values)] = 0

rgb = np.stack(
    [
        (f_U.values * 3.6 + shift).astype(np.uint8),
        (f_V.values * 3.6 + shift).astype(np.uint8),
        np.zeros(f_U.values.shape).astype(np.uint8)
    ], 
    axis=0
)

rgb_flipped = rgb[:, ::-1, :]

with rasterio.open(
    "data/wind.png",
    "w",
    driver="PNG",
    height=f_U.shape[0],
    width=f_U.shape[1],
    count=3,
    dtype=rgb.dtype,
) as dst:
    dst.write(rgb_flipped)
    dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue]