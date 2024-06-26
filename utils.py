import numpy as np
import os
from astropy.io import fits
import time

class Timer:
    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        print(f"Elapsed time: {elapsed_time:.2f} seconds")

def crop(img, x_c, y_c, w=512, h=512):
    return img[y_c-h//2:y_c+h//2, x_c-w//2:x_c+w//2]

def combine_red_green(img1, img2):
    img = np.zeros((img1.shape[0], img1.shape[1], 3))
    img[:,:,0] = img1
    img[:,:,1] = img2 
    return img

def ht(x, m, low=None, high=None, shadow_clipping=False):
    if low is None:
        if shadow_clipping:
            low = np.median(x)
        else:
            low = x.min()
    if high is None:
        high = x.max()
    x = np.clip(x, low, high)
    x = (x - low)/(high - low)
    x = mtf(x, m)
    return x

def mtf(x, m):
    return (m-1)*x/((2*m-1)*x-m)

def read_fits_as_float(filepath, verbose=True):
    if verbose:
        print(f"Opening {filepath}...")
    # Open image/header
    with fits.open(filepath) as hdul:
        img = hdul[0].data
        header = hdul[0].header
    # Type checking and float conversion
    if np.issubdtype(img.dtype, np.uint16): 
        img = img.astype('float') / 65535
    elif np.issubdtype(img.dtype, np.floating):
        pass
    else:
        raise TypeError(f"FITS image format must be either 16-bit unsigned integer, or floating point.")
    # If color image : CxHxW -> HxWxC
    if len(img.shape) == 3:
        img = np.moveaxis(img, 0, 2)
    return img, header

def remove_pedestal(img, header):
    '''Updates header in-place'''
    if "PEDESTAL" in header:
        img = img - header["PEDESTAL"] / 65535
        img = np.maximum(img, 0)
        del header["PEDESTAL"]
    return img

def save_as_fits(img, header, filepath, convert_to_uint16=True):
    print(f"Saving to {filepath}...")
    if convert_to_uint16:
        img = (np.clip(img, 0, 1)*65535).astype('uint16')
    if len(img.shape) == 3:
        img = np.moveaxis(img, 2, 0)
    hdu = fits.PrimaryHDU(data=img, header=header)
    hdu.writeto(filepath, overwrite=True)

def read_fits_header(filepath):
    with fits.open(filepath) as hdul:
        header = hdul[0].header
    return header

def extract_subheader(header, keys):
    kv_dict = {}
    for k in keys:
        kv_dict[k] = header[k]
    subheader = fits.Header(kv_dict)
    return subheader

def combine_headers(header1, header2):
    # common keys will be overriden by header2's keywords
    kv_dict = {}
    for k in header1.keys():
        kv_dict[k] = header1[k]
    for k in header2.keys():
        kv_dict[k] = header2[k]
    header = fits.Header(kv_dict)
    return header

def get_filepaths_per_exptime(dirname):
    filepaths_per_exptime = {}
    dirpath, _, filenames = next(os.walk(dirname)) # not going into subfolders
    for filename in filenames:
        if filename.endswith('.fits'):
            filepath = os.path.join(dirpath, filename)
            header = read_fits_header(filepath)
            if str(header["EXPTIME"]) in filepaths_per_exptime.keys():
                filepaths_per_exptime[str(header["EXPTIME"])].append(filepath)
            else:
                filepaths_per_exptime[str(header["EXPTIME"])] = [filepath]
    return filepaths_per_exptime

def crop_inset(img, crop_center, crop_radii, scale=4, border_value=np.nan, border_thickness=2):
    # Crop
    i_left, i_right = crop_center[0]-crop_radii[0], crop_center[0]+crop_radii[0]
    j_top, j_bottom = crop_center[1]-crop_radii[1], crop_center[1]+crop_radii[1]
    crop = img[i_left:i_right+1, j_top:j_bottom+1]
    # Crop border
    img[i_left-border_thickness:i_right+1+border_thickness, j_top-border_thickness:j_top] = border_value
    img[i_left-border_thickness:i_right+1+border_thickness, j_bottom+1:j_bottom+1+border_thickness] = border_value
    img[i_left-border_thickness:i_left, j_top-border_thickness:j_bottom+1+border_thickness] = border_value
    img[i_right+1:i_right+1+border_thickness, j_top-border_thickness:j_bottom+1+border_thickness] = border_value
    # Add inset
    inset = crop.repeat(scale,axis=0).repeat(scale,axis=1)
    img[-inset.shape[0]:, -inset.shape[1]:] = inset
    # Inset border 
    img[-inset.shape[0]:, -inset.shape[1]-border_thickness:-inset.shape[1]] = border_value
    img[-inset.shape[0]-border_thickness:-inset.shape[0], -inset.shape[1]:] = border_value

def crop_img(img, left, right, top, bottom, header=None):
    # Crop image
    new_img = img[top:bottom+1, left:right+1]
    if header is not None:
        # Create and update new header
        new_header = fits.Header(header, copy=True)
        new_header["NAXIS1"], new_header["NAXIS2"] = img.shape[1], img.shape[0] 
        for k, v in new_header.items():
            if k in ["MOON-X", "SUN-X"]:
                new_header[k] = v - left 
            if k in ["MOON-Y", "SUN-Y"]:
                new_header[k] = v - top
        return new_img, new_header 
    else:
        return new_img