import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from wind.core import Agent, CUTOFF, backtest, csv_text, demo_measurements, demo_weather, dt, evaluate, iso, load_measurements, validate_weather
from wind.weather import GFS, published, ranges_from_index


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measurements = demo_measurements()
        cls.issue = dt('2026-01-31T23:00:00+05:00')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent = Agent(self.temp.name)

    def forecast(self, history=None, horizon=48, revision=0):
        return self.agent.run(history if history is not None else self.measurements,
                              demo_weather(self.issue, horizon, revision), self.issue, horizon, True)

    def test_complete_horizons_and_bounds(self):
        for horizon in (24, 48):
            result = self.forecast(horizon=horizon)
            self.assertEqual(len(result['forecasts']), horizon*2)
            for row in result['forecasts']:
                self.assertTrue(0 <= row['lower'] <= row['power_normalized'] <= row['upper'] <= 1)
                self.assertLess(dt(row['available_at']), self.issue)
            self.assertEqual(dt(result['forecasts'][0]['valid_at']), CUTOFF)

    def test_february_truth_cannot_change_forecast(self):
        original = self.forecast()
        changed = [dict(r, power_normalized=1-r['power_normalized'], wind_speed_ms=40) if dt(r['timestamp']) >= CUTOFF else r for r in self.measurements]
        result = self.forecast(changed)
        self.assertEqual(original['forecasts'], result['forecasts'])
        self.assertEqual(original['fingerprint'], result['fingerprint'])

    def test_unavailable_telemetry_cannot_change_forecast(self):
        original = self.forecast()
        changed = [dict(r, power_normalized=1) if dt(r['available_at']) > self.issue else r for r in self.measurements]
        self.assertEqual(original['fingerprint'], self.forecast(changed)['fingerprint'])

    def test_cache_and_weather_revision(self):
        first = self.forecast()
        self.assertFalse(first['cache_hit'])
        self.assertTrue(self.forecast()['cache_hit'])
        updated = self.forecast(revision=1)
        self.assertNotEqual(first['fingerprint'], updated['fingerprint'])
        self.assertNotEqual(first['forecasts'], updated['forecasts'])

    def test_reject_late_weather_and_reanalysis(self):
        weather = demo_weather(self.issue, 24)
        for key, value in [('available_at', iso(self.issue+timedelta(seconds=1))), ('run_at', iso(self.issue+timedelta(hours=1))), ('source', 'reanalysis')]:
            changed = copy.deepcopy(weather)
            changed[0][key] = value
            with self.assertRaises(ValueError):
                validate_weather(changed, self.issue, 24, True)

    def test_reject_synthetic_in_real_mode(self):
        with self.assertRaises(ValueError):
            validate_weather(demo_weather(self.issue, 24), self.issue, 24, False)

    def test_missing_duplicate_and_nan_weather(self):
        weather = demo_weather(self.issue, 24)
        cases = [weather[:-1], weather + [weather[0]], [dict(weather[0], wind_speed_ms=float('nan'))]+weather[1:]]
        for rows in cases:
            with self.assertRaises(ValueError):
                validate_weather(rows, self.issue, 24, True)

    def test_measurement_units_duplicates_and_availability(self):
        good = dict(timestamp='2026-01-01T00:00:00+05:00', turbine_id='T1', wind_speed_ms=8, temperature_c=3, power_normalized=.2)
        self.assertEqual(len(load_measurements(csv_text([good]))), 1)
        for bad in [dict(good, power_normalized=20), dict(good, wind_speed_ms='nan'), dict(good, timestamp='2026-01-01T00:00:00'), dict(good, available_at=good['timestamp'])]:
            with self.assertRaises(ValueError):
                load_measurements(csv_text([bad]))
        with self.assertRaises(ValueError):
            load_measurements(csv_text([good, good]))

    def test_incomplete_history_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, '168'):
            self.forecast(self.measurements[:10])

    def test_timezone_equivalence(self):
        self.assertEqual(self.issue, dt('2026-01-31T18:00:00Z'))
        with self.assertRaises(ValueError):
            dt('2026-01-31T18:00:00')

    def test_rolling_coverage_and_independent_evaluation(self):
        result = backtest(self.measurements, self.agent, lambda origin,horizon: (demo_weather(origin,horizon),True))
        self.assertEqual(result['origins'], 28)
        self.assertEqual(len(result['forecasts']), 2688)
        for metric in result['metrics']:
            self.assertEqual(metric['n'], 672 if metric['horizon']=='1–24' else 648)
            self.assertTrue(0 <= metric['mae'] <= 1)
        zeros = [dict(r, power_normalized=0) for r in self.measurements]
        self.assertNotEqual(result['metrics'], evaluate(result['forecasts'], zeros))


class WeatherTests(unittest.TestCase):
    def test_index_ranges_and_missing_fields(self):
        index = '1:0:d=2026013112:UGRD:100 m above ground:12 hour fcst:\n2:10:d=2026013112:VGRD:100 m above ground:12 hour fcst:\n3:30:d=2026013112:TMP:2 m above ground:12 hour fcst:\n4:60:d=2026013112:RH:2 m above ground:12 hour fcst:'
        self.assertEqual(ranges_from_index(index), {'UGRD':(0,9),'VGRD':(10,29),'TMP':(30,59)})
        with self.assertRaises(ValueError):
            ranges_from_index(index, 10)

    def test_actual_publication_time_required(self):
        issue = dt('2026-01-31T18:00:00Z')
        self.assertLess(published({'Last-Modified':'Sat, 31 Jan 2026 15:49:07 GMT'}, issue), issue)
        for headers in [{}, {'Last-Modified':'Sat, 31 Jan 2026 19:49:07 GMT'}]:
            with self.assertRaises(ValueError):
                published(headers, issue)

    def test_fallback_to_previous_run(self):
        issue = dt('2026-01-31T18:00:00Z')
        with tempfile.TemporaryDirectory() as directory:
            provider = GFS(directory)
            def hour(run, lead, origin):
                if run.hour == 12:
                    raise ValueError('late publication')
                return dict(run_at=iso(run), valid_at=iso(run+timedelta(hours=lead)), available_at=iso(run+timedelta(hours=4)),
                            values={t:dict(wind_speed_ms=7, temperature_c=5) for t in ['T1','T2']}, source='noaa-gfs-operational', evidence=[])
            with patch.object(provider, 'hour', side_effect=hour):
                result = provider.forecast(issue, 24)
            self.assertEqual(len(result), 48)
            self.assertEqual(dt(result[0]['run_at']).hour, 6)
            self.assertFalse(provider.decisions[0]['selected'])
            self.assertTrue(provider.decisions[1]['selected'])


if __name__ == '__main__':
    unittest.main()
