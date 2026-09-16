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

# All session observations below are synthetic, never hardware evidence.
from turbo.telemetry import EnergySession


class SyntheticMeter:
    def __init__(self, clock):
        self.clock, self.joules, self.closed = clock, 100., False
        self.power = 2.
        self.error = None
    def sample(self):
        return {'monotonic_s': self.clock[0], 'channels_pwh': {'SYS': self.joules / 3.6e-9}, 'error': self.error}
    def advance(self, seconds):
        self.clock[0] += seconds
        self.joules += seconds * self.power
    def close(self):
        self.closed = True


class EnergySessionTests(unittest.TestCase):
    def setUp(self):
        self.protocol = dict(channel='SYS', counter_resolution_s=1., idle_window_s=10.,
                             idle_repeats=3, warmup_count=3, idle_max_cv=.1,
                             counter_resolution_evidence='synthetic test only', power_mode='synthetic')
        self.clock = [0.]
        self.meter = SyntheticMeter(self.clock)
        self.session = EnergySession(self.protocol, self.meter, lambda: self.clock[0], self.meter.advance)

    def test_runtime_idle_then_task_and_inference_boundaries(self):
        idle = self.session.measure_idle('runtime')
        self.assertTrue(idle['stable'])
        self.assertAlmostEqual(idle['mean_power_w'], 2)
        self.meter.power = 5
        with self.session.measure('warm_task') as task:
            self.meter.advance(2)
        self.assertAlmostEqual(task['gross_energy_j'], 10)
        self.assertAlmostEqual(task['net_energy_j'], 6)
        with self.session.measure('inference') as short:
            self.meter.advance(1.99)
        self.assertIsNone(short['gross_energy_j'])
        self.assertEqual(short['unavailable_reason'], 'duration_below_two_counter_intervals')
        self.assertIs(self.session.last_inference, short)
        self.session.close()
        self.assertTrue(self.meter.closed)

    def test_negative_net_not_clamped(self):
        self.session.idle_power_w = 3
        with self.session.measure('warm_task') as task:
            self.meter.advance(3)
        self.assertIsNone(task['net_energy_j'])
        self.assertEqual(task['unavailable_reason'], 'negative_net_energy')
        self.assertAlmostEqual(task['gross_energy_j'], 6)

    def test_platform_idle_does_not_set_runtime_idle(self):
        self.assertTrue(self.session.measure_idle('platform')['stable'])
        self.assertIsNone(self.session.idle_power_w)

    def test_unstable_idle_clears_previous_reference(self):
        self.session.idle_power_w = 2
        def variable_sleep(seconds):
            self.meter.power *= 3
            self.meter.advance(seconds)
        self.session.sleep = variable_sleep
        self.assertFalse(self.session.measure_idle('runtime')['stable'])
        self.assertIsNone(self.session.idle_power_w)

    def test_error_and_nonfinite_counters_are_unavailable(self):
        self.meter.error = 'synthetic error'
        with self.session.measure('inference') as result:
            self.meter.advance(3)
        self.assertIsNone(result['gross_energy_j'])
        a = {'monotonic_s': 0, 'channels_pwh': {'SYS': 1}}
        for b in ({'monotonic_s': 2, 'channels_pwh': {'SYS': float('inf')}},
                  {'monotonic_s': float('nan'), 'channels_pwh': {'SYS': 10}},
                  {'monotonic_s': 2, 'channels_pwh': {'SYS': 10}, 'error': 'failed'},
                  {'monotonic_s': 2}):
            self.assertEqual(energy_delta(a,b)['channels'], {})

    def test_protocol_requires_observations(self):
        for key, value in [('channel','GPU'), ('counter_resolution_s',0),
                           ('idle_window_s',9), ('idle_repeats',2), ('warmup_count',0),
                           ('counter_resolution_evidence',''), ('power_mode',None),
                           ('idle_max_cv',float('nan'))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                EnergySession({**self.protocol,key:value}, meter=self.meter)

    def test_protocol_validation_does_not_open_meter(self):
        from unittest.mock import patch
        with patch('turbo.telemetry.EnergyMeter', side_effect=AssertionError('must not open')):
            self.assertEqual(EnergySession.validate_protocol(self.protocol), self.protocol)

    def test_nonfinite_raw_observation_is_json_safe_and_unavailable(self):
        import json
        self.meter.joules = float('nan')
        with self.session.measure('inference') as result:
            self.meter.advance(3)
        self.assertIsNone(result['gross_energy_j'])
        self.assertIsNone(result['raw_before']['channels_pwh']['SYS'])
        self.assertIn('sample.channels_pwh.SYS', result['raw_before']['invalid_numeric_fields'])
        json.dumps(result, allow_nan=False)
