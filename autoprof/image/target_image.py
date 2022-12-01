from .image_object import BaseImage
import torch
import numpy as np
from torch.nn.functional import avg_pool2d
from astropy.io import fits

class Target_Image(BaseImage):
    """Image object which represents the data to be fit by a model. It can
    include a variance image, mask, and PSF as anciliary data which
    describes the target image.

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_variance(kwargs.get("variance", None))
        self.set_mask(kwargs.get("mask", None))
        self.set_psf(kwargs.get("psf", None))

    @property
    def variance(self):
        if self.has_variance:
            return self._variance
        return torch.ones_like(self.data)
    @variance.setter
    def variance(self, variance):
        self.set_variance(variance)
    @property
    def has_variance(self):
        return self._variance is not None
    
    @property
    def mask(self):
        if self.has_mask:
            return self._mask
        return torch.zeros_like(self.data, dtype = torch.bool)
    @mask.setter
    def mask(self, mask):
        self.set_mask(mask)
    @property
    def has_mask(self):
        return self._mask is not None
    
    @property
    def psf(self):
        return self._psf
    @psf.setter
    def psf(self, psf):
        self.set_psf(psf)
    @property
    def psf_border(self):
        return self.pixelscale * (1 + torch.flip(torch.tensor(self.psf.shape, dtype = self.dtype, device = self.device), (0,))) / 2
    @property
    def psf_border_int(self):
        return ((1 + torch.flip(torch.tensor(self.psf.shape, dtype = self.dtype, device = self.device), (0,))) / 2).int()
    @property
    def has_psf(self):
        return self._psf is not None

    def set_variance(self, variance):
        if variance is None:
            self._variance = None
            return
        assert variance.shape == self.data.shape, "variance must have same shape as data"
        self._variance = variance.to(dtype = self.dtype, device = self.device) if isinstance(variance, torch.Tensor) else torch.as_tensor(variance, dtype = self.dtype, device = self.device)
        
    def set_psf(self, psf):
        if psf is None:
            self._psf = None
            return
        assert torch.all((torch.tensor(psf.shape) % 2) == 1), "psf must have odd shape"
        self._psf = psf.to(dtype = self.dtype, device = self.device) if isinstance(psf, torch.Tensor) else torch.as_tensor(psf, dtype = self.dtype, device = self.device)

    def set_mask(self, mask):
        if mask is None:
            self._mask = None
            return
        assert mask.shape == self.data.shape, "mask must have same shape as data"
        self._mask = mask.to(dtype = torch.bool, device = self.device) if isinstance(mask, torch.Tensor) else torch.as_tensor(mask, dtype = torch.bool, device = self.device)

    def to(self, dtype = None, device = None):
        super().to(dtype = dtype, device = device)
        if self.has_variance:
            self._variance = self._variance.to(dtype = self.dtype, device = self.device)
        if self.has_psf:
            self._psf = self._psf.to(dtype = self.dtype, device = self.device)
        if self.has_mask:
            self._mask = self.mask.to(dtype = torch.bool, device = self.device)
        return self
            
    def or_mask(self, mask):
        self._mask = torch.logical_or(self.mask, mask)
    def and_mask(self, mask):
        self._mask = torch.logical_and(self.mask, mask)
        
    def blank_copy(self):
        return self.__class__(
            data = torch.zeros_like(self.data),
            device = self.device,
            dtype = self.dtype,
            zeropoint = self.zeropoint,
            mask = self._mask,
            psf = self._psf,
            note = self.note,
            window = self.window,
        )
    
    def get_window(self, window):
        indices = window.get_indices(self)
        return self.__class__(
            data = self.data[indices],
            device = self.device,
            dtype = self.dtype,
            pixelscale = self.pixelscale,
            zeropoint = self.zeropoint,
            variance = self._variance[indices] if self.has_variance else None,
            mask = self._mask[indices] if self.has_mask else None,
            psf = self._psf,
            note = self.note,
            origin = (torch.max(self.origin[0], window.origin[0]),
                      torch.max(self.origin[1], window.origin[1]))
        )
    
    def reduce(self, scale):
        assert isinstance(scale, int)
        assert scale > 1

        MS = self.data.shape[0] // scale
        NS = self.data.shape[1] // scale
        return self.__class__(
            data = self.data[:MS*scale, :NS*scale].reshape(MS, scale, NS, scale).sum(axis=(1, 3)),
            device = self.device,
            dtype = self.dtype,
            pixelscale = self.pixelscale * scale,
            zeropoint = self.zeropoint,
            variance = self.variance[:MS*scale, :NS*scale].reshape(MS, scale, NS, scale).sum(axis=(1, 3)) if self.has_variance else None,
            mask = self.mask[:MS*scale, :NS*scale].reshape(MS, scale, NS, scale).max(axis=(1, 3)) if self.has_mask else None,
            psf = self.psf[:MS*scale, :NS*scale].reshape(MS, scale, NS, scale).sum(axis=(1, 3)) if self.has_psf else None,#fixme, psf doesnt reduce properly,  MS NS too large
            note = self.note,
            origin = self.origin,
        )

    def _save_image_list(self):
        image_list = super()._save_image_list()
        if self._psf is not None:
            psf_header = fits.Header()
            psf_header["IMAGE"] = "PSF"
            image_list.append(fits.ImageHDU(self._psf.detach().cpu().numpy(), header = psf_header))
        if self._variance is not None:
            var_header = fits.Header()
            var_header["IMAGE"] = "VARIANCE"
            image_list.append(fits.ImageHDU(self._variance.detach().cpu().numpy(), header = var_header))
        if self._mask is not None:
            mask_header = fits.Header()
            mask_header["IMAGE"] = "MASK"
            image_list.append(fits.ImageHDU(self._mask.detach().cpu().numpy(), header = mask_header))
        return image_list

    def load(self, filename):
        hdul = super().load(filename)

        for hdu in hdul:
            if "IMAGE" in hdu.header and hdu.header["IMAGE"] == "PSF":
                self.set_psf(np.array(hdu.data, dtype = np.float64))
            if "IMAGE" in hdu.header and hdu.header["IMAGE"] == "VARIANCE":
                self.set_variance(np.array(hdu.data, dtype = np.float64))
            if "IMAGE" in hdu.header and hdu.header["IMAGE"] == "MASK":
                self.set_mask(np.array(hdu.data, dtype = bool))
        return hdul
