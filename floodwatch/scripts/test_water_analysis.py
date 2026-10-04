"""Scientific invariants: valid coverage, transitions, area accounting, thresholds."""
import unittest
import numpy as np
from analyze_water import classify, area_stats, remove_small, otsu, histogram_valley
from calibrate_observations import make_graph
from pathlib import Path


class WaterAnalysisTest(unittest.TestCase):
    def test_transitions_and_area_accounting(self):
        before = np.full((24,24),-7.0)
        after = before.copy()
        valid = np.ones_like(before,dtype=bool)
        before[1:5,1:5] = after[1:5,1:5] = -20  # persistent
        after[10:14,1:5] = -20                  # new
        before[1:5,10:14] = -20                 # lost
        after[10:14,10:14] = -20
        valid[10:14,10:14] = False              # cannot count missing baseline as dry
        classes=classify(before,after,valid,-13)
        self.assertTrue((classes[~valid]==0).all())
        self.assertEqual(np.count_nonzero(classes==3),16)
        self.assertEqual(np.count_nonzero(classes==4),16)
        self.assertEqual(np.count_nonzero(classes==2),16)
        areas=area_stats(classes)
        self.assertAlmostEqual(areas['new_water_km2'],.0016)
        self.assertAlmostEqual(areas['common_valid_km2'],valid.sum()*.0001)
        self.assertAlmostEqual(areas['net_water_change_km2'],areas['after_water_km2']-areas['before_water_km2'])

    def test_isolated_noise_is_removed_without_filling_nodata(self):
        mask=np.zeros((15,15),bool)
        mask[2,2]=True
        mask[7:10,7:10]=True
        cleaned=remove_small(mask)
        self.assertFalse(cleaned[2,2])
        self.assertEqual(cleaned.sum(),9)

    def test_known_separate_distributions_and_threshold_sensitivity(self):
        rng=np.random.default_rng(42)
        values=np.concatenate([rng.normal(-20,.6,10000),rng.normal(-7,.6,10000)])
        t,separation=otsu(values)
        self.assertTrue(-18<t<-9)
        self.assertGreater(separation,.95)
        before=np.full((10,10),-11.5)
        after=np.full((10,10),-13.5)
        valid=np.ones_like(before,bool)
        self.assertEqual(np.count_nonzero(classify(before,after,valid,-12.5)==3),100)
        self.assertEqual(np.count_nonzero(classify(before,after,valid,-14.5)==3),0)

    def test_valley_uses_distribution_not_date_order_or_change_area(self):
        rng = np.random.default_rng(84)
        values = np.concatenate([rng.normal(-18, 1, 60000), rng.normal(-8, 2, 200000)])
        threshold, selection = histogram_valley(values)
        self.assertTrue(-16 < threshold < -13)
        self.assertLess(selection['valley_to_smaller_peak_ratio'], .5)
        self.assertEqual(threshold, histogram_valley(values[::-1])[0])
        self.assertLessEqual(abs(threshold - histogram_valley(values, .2)[0]), .5)

    def test_valley_refuses_single_mode(self):
        values = np.random.default_rng(5).normal(-10, 2, 200000)
        with self.assertRaisesRegex(ValueError, 'histogram modes|valley'):
            histogram_valley(values)

    def test_calibrate_complex_before_geocoding_and_subset_last(self):
        graph=make_graph(Path('/source/product.xml'),Path('/dem.tif'),Path('/out.tif')).getroot()
        nodes=graph.findall('node')
        self.assertEqual([n.findtext('operator') for n in nodes],['Read','Calibration','Terrain-Correction','Subset','Write'])
        self.assertEqual(nodes[1].findtext('parameters/outputImageScaleInDb'),'false')
        self.assertEqual(nodes[2].findtext('parameters/sourceBands'),'Sigma0_HH')
        self.assertEqual(nodes[2].findtext('parameters/applyRadiometricNormalization'),'false')


if __name__=='__main__':
    unittest.main()
