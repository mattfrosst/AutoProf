# Apply a different optimizer iteratively
import os
import torch
import numpy as np
from time import time
from .base import BaseOptimizer
from .. import AP_config
import matplotlib.pyplot as plt

__all__ = ["Iter"]

class Iter(BaseOptimizer):
    """Optimizer wrapper that performs optimization iteratively.

    This optimizer applies a different optimizer to a group model iteratively.
    It can be used for complex fits or when the number of models to fit is too large to fit in memory.

    Args:
        model: An `AutoProf_Model` object to perform optimization on.
        method: The optimizer class to apply at each iteration step.
        initial_state: Optional initial state for optimization, defaults to None.
        max_iter: Maximum number of iterations, defaults to 100.
        method_kwargs: Keyword arguments to pass to `method`.
        **kwargs: Additional keyword arguments. 
    """

    def __init__(self, model, method, initial_state = None, max_iter = 100, method_kwargs = {}, **kwargs):

        super().__init__(model, initial_state, max_iter = max_iter, **kwargs)

        self.method = method
        self.method_kwargs = method_kwargs
        #          # pixels      # parameters
        self.ndf = self.model.target[self.model.window].flatten("data").size(0) - len(self.current_state)
        if self.model.target.has_mask:
            # subtract masked pixels from degrees of freedom
            self.ndf -= torch.sum(self.model.target[self.model.window].flatten("mask")).item()
        
    def sub_step(self, model):
        self.Y -= model()
        model.target = model.target[model.window] - self.Y[model.window]
        res = self.method(model, **self.method_kwargs).fit()
        self.Y += model()
        if self.verbose > 1:
            AP_config.ap_logger.info(res.message)
        model.target = self.model.target
        
    def step(self):
        if self.verbose > 0:
            AP_config.ap_logger.info("--------iter-------")

        # Fit each model individually
        for model in self.model.model_list:
            if self.verbose > 0:
                AP_config.ap_logger.info(model.name)
            self.sub_step(model)
        # Update the current state
        self.current_state = self.model.get_parameter_vector(as_representation = True)

        # update the loss value
        with torch.no_grad():
            self.Y = self.model(parameters = self.current_state, as_representation = True, override_locked = False, return_data = False)
            D = self.model.target[self.model.window].flatten("data")
            V = self.model.target[self.model.window].flatten("variance") if self.model.target.has_variance else 1.
            if self.model.target.has_mask:
                M = self.model.target[self.model.window].flatten("mask")
                loss = torch.sum((((D - self.Y.flatten("data"))**2 ) / V)[torch.logical_not(M)]) / self.ndf
            else:
                loss = torch.sum(((D - self.Y.flatten("data"))**2 / V)) / self.ndf
        if self.verbose > 0:
            AP_config.ap_logger.info(f"Loss: {loss.item()}")
        self.lambda_history.append(np.copy((self.current_state).detach().cpu().numpy()))
        self.loss_history.append(loss.item())
        
        # test for convergence
        if self.iteration >= 2 and ((-self.relative_tolerance*1e-3) < ((self.loss_history[-2] - self.loss_history[-1])/self.loss_history[-1]) < (self.relative_tolerance/10)):
            self._count_finish += 1
        else:
            self._count_finish = 0

        self.iteration += 1
        
    def fit(self):

        self.iteration = 0
        self.Y = self.model(parameters = self.current_state, as_representation = True, override_locked = False, return_data = False)
        start_fit = time()
        try:
            while True:
                self.step()
                if self.save_steps is not None:
                    self.model.save(os.path.join(self.save_steps, f"{self.model.name}_Iteration_{self.iteration:03d}.yaml"))
                if self.iteration > 2 and self._count_finish >= 2:
                    self.message = self.message + "success"
                    break                    
                elif self.iteration > self.max_iter:
                    self.message = self.message + f"fail max iterations reached: {self.iteration}"
                    break
                    
        except KeyboardInterrupt:
            self.message = self.message + "fail interrupted"
            
        self.model.set_parameters(self.res(), as_representation = True, override_locked = False)
        if self.verbose > 1:
            AP_config.ap_logger.info("Iter Fitting complete in {time() - start_fit} sec with message: self.message")
            
        return self
