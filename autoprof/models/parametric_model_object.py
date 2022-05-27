from .model_object import BaseModel
import numpy as np
from autoprof.utils.initialize import isophotes
from autoprof.utils.angle_operations import Angle_Average
from scipy.stats import iqr

class Parametric_Model(BaseModel):

    model_type = " ".join(("parametric", BaseModel.model_type))
    parameter_specs = {
        "q": {"units": "b/a", "limits": (0,1), "uncertainty": 0.03},
        "PA": {"units": "rad", "limits": (0,np.pi), "cyclic": True, "uncertainty": 0.06},
    }
    
    def initialize(self, target = None):
        super().initialize(target)

        if target is None:
            target = self.target
        if self["PA"].value is None:
            iso_info = isophotes(
                target.data,
                (self["center_x"].value - target.origin[1], self["center_y"].value - target.origin[0]),
                threshold = 3*iqr(target.data, rng = (16,84))/2,
                pa = 0., q = 1., n_isophotes = 3
            )
            self["PA"].set_value((-Angle_Average(list(iso["phase2"] for iso in iso_info))/2) % np.pi, override_fixed = True)
        if self["q"].value is None:
            q_samples = np.linspace(0.1,0.9,15)
            iso_info = isophotes(
                target.data,
                (self["center_x"].value - target.origin[1], self["center_y"].value - target.origin[0]),
                threshold = 3*iqr(target.data, rng = (16,84))/2,
                pa = self["PA"].value, q = q_samples,
            ) 
            self["q"].set_value(q_samples[np.argmin(list(iso["amplitude2"] for iso in iso_info))], override_fixed = True)
        
