# Metropolis-Hasting Markov-Chain Monte-Carlo
import os
from time import time
from typing import Optional, Sequence
import torch
from tqdm import tqdm
import numpy as np
from .base import BaseOptimizer
from .. import AP_config

__all__ = ["MHMCMC"]


class MHMCMC(BaseOptimizer):
    """Metropolis-Hastings Markov-Chain Monte-Carlo sampler, based on:
    https://en.wikipedia.org/wiki/Metropolis-Hastings_algorithm . This
    is a naive implimentation of a standard MCMC, it is far from
    optimal and should not be used for anything but the most basic
    scenarios.

    Args:
      model (AutoProf_Model): The model which will be sampled.
      initial_state (Optional[Sequence]): A 1D array with the values for each parameter in the model. Note that these values should be in the form of "as_representation" in the model.
      max_iter (int): The number of sampling steps to perform. Default 1000
      epsilon (float or array): The random step length to take at each iteration. This is the standard deviation for the normal distribution sampling. Default 1e-2

    """

    def __init__(
        self,
        model: "AutoProf_Model",
        initial_state: Optional[Sequence] = None,
        max_iter: int = 1000,
        **kwargs
    ):
        super().__init__(model, initial_state, max_iter=max_iter, **kwargs)

        self.epsilon = kwargs.get("epsilon", 1e-2)

        self.Y = self.model.target[self.model.window].flatten("data")
        #        1 / sigma^2
        self.W = (
            1.0 / self.model.target[self.model.window].flatten("variance")
            if model.target.has_variance
            else 1.0
        )
        #          # pixels      # parameters
        self.ndf = len(self.Y) - len(self.current_state)

        self.chain = []
        self._accepted = 0
        self._sampled = 0

    def fit(
        self,
        state: Optional[torch.Tensor] = None,
        nsamples: Optional[int] = None,
        restart_chain: bool = True,
    ):
        """
        Performs the MCMC sampling using a Metropolis Hastings acceptance step and records the chain for later examination.
        """

        if nsamples is None:
            nsamples = self.max_iter

        if state is None:
            state = self.current_state
        chi2 = self.sample(state)

        if restart_chain:
            self.chain = []
        else:
            self.chain = list(self.chain)
        for _ in tqdm(range(nsamples)):
            state, chi2 = self.step(state, chi2)
            self.append_chain(state)
        self.current_state = state
        self.chain = np.stack(self.chain)
        return self

    def append_chain(self, state: torch.Tensor):
        """
        Add a state vector to the MCMC chain
        """

        self.model.set_parameters(state, as_representation=True)
        chain_state = self.model.get_parameter_vector(as_representation=False)
        self.chain.append(chain_state.detach().cpu().clone().numpy())

    @staticmethod
    def accept(log_alpha):
        """
        Evaluates randomly if a given proposal is accepted. This is done in log space which is more natural for the evaluation in the step.
        """
        return torch.log(torch.rand(log_alpha.shape)) < log_alpha

    @torch.no_grad()
    def sample(self, state: torch.Tensor):
        """
        Samples the model at the proposed state vector values
        """
        Y = self.model(
            parameters=state, as_representation=True, override_locked=False
        ).flatten("data")
        # Compute Chi^2
        if self.model.target.has_mask:
            loss = (
                torch.sum(((self.Y - Y) ** 2 * self.W)[torch.logical_not(self.mask)])
                / self.ndf
            )
        else:
            loss = torch.sum((self.Y - Y) ** 2 * self.W) / self.ndf

        return loss

    @torch.no_grad()
    def step(self, state: torch.Tensor, chi2: torch.Tensor) -> torch.Tensor:
        """
        Takes one step of the HMC sampler by integrating along a path initiated with a random momentum.
        """

        proposal_state = torch.normal(mean=state, std=self.epsilon)
        proposal_chi2 = self.sample(proposal_state)
        log_alpha = (chi2 - proposal_chi2) / 2
        accept = self.accept(log_alpha)
        self._accepted += accept
        self._sampled += 1
        return proposal_state if accept else state, proposal_chi2 if accept else chi2

    @property
    def acceptance(self):
        """
        Returns the ratio of accepted states to total states sampled.
        """

        return self._accepted / self._sampled
