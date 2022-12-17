from .core_model import AutoProf_Model
from ..image import Model_Image, Target_Image
from copy import deepcopy
import torch
import numpy as np
import matplotlib.pyplot as plt

__all__ = ["Group_Model"]

class Group_Model(AutoProf_Model):
    """Model object which represents a list of other models. For each
    general AutoProf model method, this calls all the appropriate
    models from its list and combines their output into a single
    summed model. This class shoould be used when describing any
    system more comlex than makes sense to represent with a single
    light distribution.

    Parameters:
        name: unique name for the full group model
        target: the target image that this group model is trying to fit to
        model_list: list of AutoProf_Model objects which will combine for the group model
        locked: boolean for if the whole group of models should be locked

    """

    model_type = "groupmodel"
    
    def __init__(self, name, *args, model_list = None, **kwargs):
        super().__init__(name, *args, model_list = model_list, **kwargs)
        
        self.model_list = [] if model_list is None else model_list
        self._psf_mode = None
        self.update_window()
        if "filename" in kwargs:
            self.load(kwargs["filename"])
        if "equality_constraints" in kwargs:
            if isinstance(kwargs["equality_constraints"][0], str):
                self.add_equality_constraint(kwargs["equality_constraints"])
            else:
                for constraint in kwargs["equality_constraints"]:
                    self.add_equality_constraint(constraint)

    def add_equality_constraint(self, constraint):
        for model in self.model_list:
            if model.name == constraint[1]:
                root_model = model
                break
        else:
            raise ValueError(f"model name {constraint[1]} not found in model list. Could not constrain")
        for model_name in constraint[2:]:
            for model in self.model_list:
                if model.name == model_name:
                    model.add_equality_constraint(constraint[0], root_model)
                    break
            else:
                raise ValueError(f"model name {constraint[1]} not found in model list. Could not constrain")
            
    def add_model(self, model):
        self.model_list.append(model)
        self.update_window()

    def update_window(self, include_locked = False):
        new_window = None
        for model in self.model_list:
            if model.locked and not include_locked:
                continue
            if new_window is None:
                new_window = model.window.make_copy()
            else:
                new_window |= model.window
        self.window = new_window
                
    @property
    def parameter_order(self):
        param_order = tuple()
        for model in self.model_list:
            if model.locked:
                continue
            param_order = param_order + tuple(f"{model.name}|{mp}" for mp in model.parameter_order)
        return param_order

    @torch.no_grad()
    def initialize(self, target = None):
        self.sync_target()
        if target is None:
            target = self.target
        super().initialize(target)

        target_copy = target.copy()
        for model in self.model_list:
            model.initialize(target_copy)
            target_copy -= model.sample()
            
    def finalize(self):
        for model in self.model_list:
            model.finalize()
        
    def sample(self, sample_image = None):

        if sample_image is None:
            sample_window = True
            sample_image = self.make_model_image()
        else:
            sample_window = False

        for model in self.model_list:
            if sample_window:
                sample_image += model.sample()
            else:
                model.sample(sample_image)

        return sample_image

    @property
    def parameters(self):
        try:
            params = {}
            for model in self.model_list:
                for p in model.parameters:
                    params[f"{model.name}|{p}"] = model.parameters[p]
            return params
        except AttributeError:
            return {}
            
    def get_parameters_representation(self, exclude_locked = True):
        all_parameters = []
        all_keys = []
        for model in self.model_list:
            keys, reps = model.get_parameters_representation(exclude_locked)
            for k, r in zip(keys, reps):
                if exclude_locked and model[k].locked:
                    continue
                all_parameters.append(r)
                all_keys.append(f"{model.name}|{k}")
        return all_keys, all_parameters
    
    def get_parameters_value(self, exclude_locked = True):
        all_parameters = {}
        for model in self.model_list:
            values = model.get_parameters_value(exclude_locked)
            for p in values:
                all_parameters[f"{model.name}|{p}"] = values[p] 
        return all_parameters

    def jacobian(self, parameters):
        vstart = 0
        ivstart = 0
        full_jac = torch.zeros(tuple(self.window.get_shape_flip(self.target.pixelscale)) + (len(parameters),), dtype = self.dtype, device = self.device)
        for model in self.model_list:
            keys, reps = model.get_parameters_representation()
            vend = vstart + np.sum(self.parameter_vector_len[ivstart:ivstart + len(keys)])
            sub_jac = model.jacobian(parameters[vstart:vend])
            indices = model.window._get_indices(self.window, self.target.pixelscale)
            for ip, i in enumerate(range(vstart, vend)):
                full_jac[indices[0], indices[1], i] = sub_jac[:,:,ip]
            ivstart += len(keys)
            vstart = vend
        return full_jac
            
        
    def __getitem__(self, key):
        if isinstance(key, tuple):
            return self.model_list[key[0]][key[1]]

        if isinstance(key, str) and "|" in key:
            model_name = key[:key.find("|")]
            for model in self.model_list:
                if model.name == model_name:
                    return model[key[key.find("|")+1:]]
        elif isinstance(key, str):
            for model in self.model_list:
                if model.name == key:
                    return model
        
        raise KeyError(f"{key} not in {self.name}. {str(self)}")

    def sync_target(self):
        if self._target is None:
            self.target = self.model_list[0].target
        for model in self.model_list:
            model.target = self.target
            
    @property
    def psf_mode(self):
        return self._psf_mode
    @psf_mode.setter
    def psf_mode(self, value):
        self._psf_mode = value
        for model in self.model_list:
            model.psf_mode = value
    
    def get_state(self):
        state = super().get_state()
        if "models" not in state:
            state["models"] = {}
        for model in self.model_list:
            state["models"][model.name] = model.get_state()
        return state

    def load(self, filename = "AutoProf.yaml"):
        state = AutoProf_Model.load(filename)
        self.name = state["name"]
        for model in state["models"]:
            for own_model in self.model_list:
                if model == own_model.name:
                    own_model.load(state["models"][model])
                    break
            else:
                self.add_model(AutoProf_Model(name = model, filename = state["models"][model], target = self.target))
