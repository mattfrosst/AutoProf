import torch
import numpy as np
import autoprof as ap

def make_basic_sersic(N = 50, M = 50, pixelscale = 0.8, x = 24.5, y = 25.4, PA = 45*np.pi/180, q = 0.6, n = 2, Re = 7.1, Ie = 0, rand = 12345):

    np.random.seed(rand)
    target = ap.image.Target_Image(
        data = np.zeros((N,M)),
        pixelscale = pixelscale,
        psf = ap.utils.initialize.gaussian_psf(2 / pixelscale, 11, pixelscale),
    )
    
    MODEL = ap.models.Sersic_Galaxy(
        name = "basic sersic model",
        target = target,
        parameters = {
            "center": [x,y],
            "PA": PA,
            "q": q,
            "n": n,
            "Re": Re,
            "Ie": Ie,
        },
    )
    
    img = MODEL().data.detach().cpu().numpy()
    target.data = img + np.random.normal(scale = 0.1, size = img.shape) + np.random.normal(scale = np.sqrt(img)/10)
    target.variance = 0.1**2 + img/100

    return target

def make_basic_gaussian(N = 50, M = 50, pixelscale = 0.8, x = 24.5, y = 25.4, PA = 45*np.pi/180, sigma = 3, flux = 1, rand = 12345):

    np.random.seed(rand)
    target = ap.image.Target_Image(
        data = np.zeros((N,M)),
        pixelscale = pixelscale,
        psf = ap.utils.initialize.gaussian_psf(2 / pixelscale, 11, pixelscale),
    )
    
    MODEL = ap.models.Gaussian_Star(
        name = "basic gaussian star",
        target = target,
        parameters = {
            "center": [x,y],
            "sigma":sigma,
            "flux": flux,
        },
    )
    
    img = MODEL().data.detach().cpu().numpy()
    target.data = img + np.random.normal(scale = 0.1, size = img.shape) + np.random.normal(scale = np.sqrt(img)/10)
    target.variance = 0.1**2 + img/100

    return target

