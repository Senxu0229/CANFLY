"""
Minimal GeoTIFF reading/writing without GDAL.

Reads the georeferencing tags of a GeoTIFF and resamples it onto a lon/lat grid.
Supported coordinate systems: EPSG:4326 (lon/lat), EPSG:3857 (web mercator),
WGS 84 / UTM north (EPSG:326xx) and south (EPSG:327xx). That covers SNAP and
most GIS exports. For anything else the error message gives the one-line
gdalwarp command that converts the file.

Pixel reading uses `tifffile` when installed (handles every compression and
tiling), else Pillow.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# --- projections --------------------------------------------------------------
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
K0 = 0.9996


def _utm_params(epsg: int):
    if 32601 <= epsg <= 32660:
        return epsg - 32600, False
    if 32701 <= epsg <= 32760:
        return epsg - 32700, True
    return None


def lonlat_to_xy(lon: np.ndarray, lat: np.ndarray, epsg: int):
    """Forward projection from degrees to the file's coordinates."""
    if epsg == 4326:
        return lon, lat
    if epsg == 3857:
        x = A * np.radians(lon)
        y = A * np.log(np.tan(np.pi / 4 + np.radians(np.clip(lat, -85, 85)) / 2))
        return x, y
    utm = _utm_params(epsg)
    if utm:
        zone, south = utm
        lon0 = math.radians((zone - 1) * 6 - 180 + 3)
        phi = np.radians(lat)
        lam = np.radians(lon) - lon0
        ep2 = E2 / (1 - E2)
        n = A / np.sqrt(1 - E2 * np.sin(phi) ** 2)
        t = np.tan(phi) ** 2
        c = ep2 * np.cos(phi) ** 2
        a = np.cos(phi) * lam
        m = A * ((1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256) * phi
                 - (3 * E2 / 8 + 3 * E2**2 / 32 + 45 * E2**3 / 1024) * np.sin(2 * phi)
                 + (15 * E2**2 / 256 + 45 * E2**3 / 1024) * np.sin(4 * phi)
                 - (35 * E2**3 / 3072) * np.sin(6 * phi))
        x = K0 * n * (a + (1 - t + c) * a**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * a**5 / 120) + 500000.0
        y = K0 * (m + n * np.tan(phi) * (a**2 / 2 + (5 - t + 9 * c + 4 * c**2) * a**4 / 24
                                         + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * a**6 / 720))
        if south:
            y = y + 10_000_000.0
        return x, y
    raise ValueError(_unsupported(epsg))


def xy_to_lonlat(x: np.ndarray, y: np.ndarray, epsg: int):
    """Inverse projection, used only to find a file's footprint."""
    if epsg == 4326:
        return x, y
    if epsg == 3857:
        return np.degrees(x / A), np.degrees(2 * np.arctan(np.exp(y / A)) - np.pi / 2)
    utm = _utm_params(epsg)
    if utm:
        zone, south = utm
        lon0 = math.radians((zone - 1) * 6 - 180 + 3)
        x = x - 500000.0
        if south:
            y = y - 10_000_000.0
        ep2 = E2 / (1 - E2)
        m = y / K0
        mu = m / (A * (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256))
        e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
        phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu) + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
                + (151 * e1**3 / 96) * np.sin(6 * mu) + (1097 * e1**4 / 512) * np.sin(8 * mu))
        n1 = A / np.sqrt(1 - E2 * np.sin(phi1) ** 2)
        t1 = np.tan(phi1) ** 2
        c1 = ep2 * np.cos(phi1) ** 2
        r1 = A * (1 - E2) / (1 - E2 * np.sin(phi1) ** 2) ** 1.5
        d = x / (n1 * K0)
        lat = phi1 - (n1 * np.tan(phi1) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
                                                 + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
        lon = lon0 + (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120) / np.cos(phi1)
        return np.degrees(lon), np.degrees(lat)
    raise ValueError(_unsupported(epsg))


def _unsupported(epsg):
    return (f"Coordinate system EPSG:{epsg} is not supported by this reader. "
            f"Convert the file first:  gdalwarp -t_srs EPSG:4326 input.tif output_4326.tif")


# --- reading ---------------------------------------------------------------------
@dataclass
class GeoRaster:
    data: np.ndarray            # 2-D, first band
    epsg: int
    x0: float                   # x of the top-left corner of pixel (0, 0)
    y0: float
    sx: float                   # pixel size in x (positive)
    sy: float                   # pixel size in y (positive, rows go south)
    nodata: float | None
    path: str

    @property
    def shape(self):
        return self.data.shape

    def footprint_lonlat(self):
        h, w = self.data.shape
        xs = np.array([self.x0, self.x0 + w * self.sx, self.x0, self.x0 + w * self.sx])
        ys = np.array([self.y0, self.y0, self.y0 - h * self.sy, self.y0 - h * self.sy])
        lon, lat = xy_to_lonlat(xs, ys, self.epsg)
        return float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())

    def sample(self, lon: np.ndarray, lat: np.ndarray, fill=np.nan):
        """Nearest-neighbour value at each lon/lat (arrays of equal shape)."""
        x, y = lonlat_to_xy(lon, lat, self.epsg)
        col = np.floor((x - self.x0) / self.sx).astype(np.int64)
        row = np.floor((self.y0 - y) / self.sy).astype(np.int64)
        h, w = self.data.shape
        ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
        out = np.full(lon.shape, fill, dtype=np.float32)
        vals = self.data[row[ok], col[ok]].astype(np.float32)
        if self.nodata is not None and not (isinstance(self.nodata, float) and math.isnan(self.nodata)):
            vals[vals == self.nodata] = fill
        out[ok] = vals
        return out


def _read_pixels_and_tags(path):
    try:
        import tifffile  # type: ignore
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            arr = page.asarray()
            tags = {t.code: t.value for t in page.tags.values()}
        if arr.ndim == 3:  # (bands, rows, cols) or (rows, cols, bands)
            arr = arr[0] if arr.shape[0] < arr.shape[-1] else arr[..., 0]
        return np.asarray(arr), tags
    except ImportError:
        pass
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path)
    tags = dict(im.tag_v2)
    try:
        arr = np.array(im)
    except Exception as e:  # compression Pillow cannot decode
        raise RuntimeError(f"{path}: Pillow cannot decode this TIFF ({e}). Run: pip install tifffile imagecodecs") from e
    if arr.ndim == 3:
        arr = arr[..., 0]
    return arr, tags


def read_geotiff(path: str) -> GeoRaster:
    arr, tags = _read_pixels_and_tags(path)
    scale = tags.get(33550)
    tie = tags.get(33922)
    matrix = tags.get(34264)
    keys = tags.get(34735)
    if keys is None:
        raise ValueError(f"{path}: no GeoTIFF tags found. Is this a georeferenced GeoTIFF?")
    keys = list(keys)
    kv = {keys[i]: keys[i + 3] for i in range(4, 4 + 4 * keys[3], 4) if keys[i + 1] == 0}
    model = kv.get(1024)
    epsg = kv.get(3072) if model == 1 else kv.get(2048)
    if epsg in (None, 32767):
        raise ValueError(f"{path}: the coordinate system is not an EPSG code. Re-export with "
                         f"gdalwarp -t_srs EPSG:4326 {path} out.tif")
    if model == 2 and epsg != 4326:
        epsg = 4326 if epsg in (4326, 4030) else epsg
    pixel_is_point = kv.get(1025) == 2
    if scale is not None and tie is not None:
        sx, sy = float(scale[0]), float(scale[1])
        i, j, x, y = float(tie[0]), float(tie[1]), float(tie[3]), float(tie[4])
        x0, y0 = x - i * sx, y + j * sy
    elif matrix is not None:
        m = list(matrix)
        if abs(m[1]) > 1e-12 or abs(m[4]) > 1e-12:
            raise ValueError(f"{path}: rotated rasters are not supported. Run gdalwarp -t_srs EPSG:4326 first.")
        sx, sy, x0, y0 = float(m[0]), float(-m[5]), float(m[3]), float(m[7])
    else:
        raise ValueError(f"{path}: missing pixel scale / tie point tags.")
    if pixel_is_point:
        x0, y0 = x0 - sx / 2, y0 + sy / 2
    nodata = tags.get(42113)
    if isinstance(nodata, (bytes, str)):
        s = nodata.decode() if isinstance(nodata, bytes) else nodata
        s = s.strip().strip('\x00')
        nodata = float(s) if s and s.lower() != 'nan' else float('nan')
    return GeoRaster(arr, int(epsg), x0, y0, sx, sy, nodata, path)


# --- writing (used by the mock-data generator and tests) -------------------------
def write_geotiff(path: str, data: np.ndarray, epsg: int, x0: float, y0: float, sx: float, sy: float, nodata=None):
    """Write a single-band GeoTIFF readable by GDAL, QGIS and read_geotiff()."""
    from PIL import Image, TiffImagePlugin
    if data.dtype == np.float32 or data.dtype == np.float64:
        im = Image.fromarray(data.astype(np.float32), mode='F')
    elif data.dtype == np.uint8:
        im = Image.fromarray(data, mode='L')
    else:
        im = Image.fromarray(data.astype(np.int32), mode='I')
    projected = epsg != 4326
    keys = [1, 1, 0, 3,
            1024, 0, 1, 1 if projected else 2,
            1025, 0, 1, 1,
            3072 if projected else 2048, 0, 1, epsg]
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[33550] = (float(sx), float(sy), 0.0)
    info.tagtype[33550] = 12
    info[33922] = (0.0, 0.0, 0.0, float(x0), float(y0), 0.0)
    info.tagtype[33922] = 12
    info[34735] = tuple(keys)
    info.tagtype[34735] = 3
    if nodata is not None:
        info[42113] = str(nodata)
        info.tagtype[42113] = 2
    im.save(path, tiffinfo=info)
