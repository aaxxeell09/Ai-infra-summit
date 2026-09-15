import unittest
from turbo.telemetry import energy_delta

class EnergyTests(unittest.TestCase):
    def test_pwh_to_joules_and_no_overlapping_rail_sum(self):
        a={'monotonic_s':1, 'channels_pwh':{'SYS':100,'GPU':20}}
        b={'monotonic_s':11, 'channels_pwh':{'SYS':10000000100,'GPU':1000000020}}
        r=energy_delta(a,b,generated_tokens=720)
        self.assertAlmostEqual(r['channels']['SYS']['energy_j'],36)
        self.assertAlmostEqual(r['channels']['SYS']['average_power_w'],3.6)
        self.assertAlmostEqual(r['channels']['SYS']['tokens_per_joule'],20)
        self.assertNotIn('total',r)
    def test_missing_stale_reset_counters_unavailable(self):
        a={'monotonic_s':1,'channels_pwh':{'SYS':100,'GPU':20,'CPU':5}}
        b={'monotonic_s':2,'channels_pwh':{'SYS':100,'GPU':1}}
        self.assertEqual(energy_delta(a,b)['channels'],{})
if __name__=='__main__':unittest.main()
