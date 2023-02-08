import unittest
import autoprof as ap
import torch
import numpy as np

class TestModel(unittest.TestCase):

    def test_AutoProf_Model(self):

        self.assertRaises(AssertionError, ap.models.AutoProf_Model, "my|model")
        
        model = ap.models.AutoProf_Model("test model")

        self.assertIsNone(model.target, "model should not have a target at this point")

        target = ap.image.Target_Image(data = torch.zeros((16,32)), pixelscale = 1.)

        model.target = target

        model.window = target.window

        model.locked = True
        model.locked = False

        state = model.get_state()

        
    def test_model_creation(self):
        np.random.seed(12345)
        shape = (10,15)
        tar = ap.image.Target_Image(
            data = np.random.normal(loc = 0, scale = 1.4, size = shape),
            pixelscale = 0.8,
            variance = np.ones(shape)*(1.4**2),
            psf = np.array([[0.05, 0.1, 0.05],[0.1, 0.4, 0.1],[0.05, 0.1, 0.05]]),
        )

        mod = ap.models.Base_Model(name = "base model", target = tar, parameters = {"center": {"value": [5,5], "locked": True}})

        mod.initialize()
        
        self.assertFalse(mod.locked, "default model should not be locked")
        
        self.assertTrue(torch.all(mod.sample().data == 0), "Base_Model model_image should be zeros")

        loss = mod.compute_loss()
        
        self.assertAlmostEqual(loss.detach().item(), 147.4986368304884/np.prod(shape), 5, "Loss calculation returns incorrect value")

class TestSersic(unittest.TestCase):

    def test_sersic_creation(self):
        np.random.seed(12345)
        N = 50
        Width = 20
        shape = (N+10,N)
        true_params = [2,5,10,-3, 5, 0.7, np.pi/4]
        IXX, IYY = np.meshgrid(np.linspace(-Width, Width, shape[1]), np.linspace(-Width, Width, shape[0]))
        QPAXX, QPAYY = ap.utils.conversions.coordinates.Axis_Ratio_Cartesian_np(true_params[5], IXX - true_params[3], IYY - true_params[4], true_params[6])
        Z0 = ap.utils.parametric_profiles.sersic_np(np.sqrt(QPAXX**2 + QPAYY**2), true_params[0], true_params[1], true_params[2]) + np.random.normal(loc = 0, scale = 0.1, size = shape)
        tar = ap.image.Target_Image(
            data = Z0,
            pixelscale = 0.8,
            variance = np.ones(Z0.shape)*(0.1**2),
        )

        mod = ap.models.Sersic_Galaxy(name = "sersic model", target = tar, parameters = {"center": [-3.2 + N/2, 5.1 + (N+10)/2]})
        
        self.assertFalse(mod.locked, "default model should not be locked")
        
        mod.initialize()

        mod.requires_grad = True
        loss = mod.compute_loss()
        
        self.assertLess(loss.detach().item(), 15000, "Loss calculation returns value too high")

        loss.backward()

        for p in mod.parameters:
            self.assertFalse(mod.parameters[p].grad is None, "Gradient should be evaluated for all model parameters")

            
class TestGroup(unittest.TestCase):

    def test_groupmodel_creation(self):
        np.random.seed(12345)
        shape = (10,15)
        tar = ap.image.Target_Image(
            data = np.random.normal(loc = 0, scale = 1.4, size = shape),
            pixelscale = 0.8,
            variance = np.ones(shape)*(1.4**2),
        )

        mod1 = ap.models.Base_Model(name = "base model 1", target = tar, parameters = {"center": {"value": [5,5], "locked": True}})
        mod2 = ap.models.Base_Model(name = "base model 2", target = tar, parameters = {"center": {"value": [5,5], "locked": True}})

        smod = ap.models.AutoProf_Model(name = "group model", model_type = "group model", model_list = [mod1, mod2], target = tar)
            
        self.assertFalse(smod.locked, "default model state should not be locked")
        
        smod.initialize()

        self.assertTrue(torch.all(smod.sample().data == 0), "model_image should be zeros")

        loss = smod.compute_loss()
        
        self.assertAlmostEqual(loss.detach().item(), 147.4986368304884/np.prod(shape), 5, "Loss calculation returns incorrect value")


if __name__ == "__main__":
    unittest.main()
        
