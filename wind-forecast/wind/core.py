from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

UTC = timezone.utc
LOCAL = timezone(timedelta(hours=5))
CUTOFF = datetime(2026, 2, 1, tzinfo=LOCAL).astimezone(UTC)
TURBINES = {'T1': (43.645150, 78.535604), 'T2': (43.643198, 78.538828)}


def dt(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('У времени должен быть часовой пояс: например 2026-01-31T23:00:00+05:00')
    return parsed.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def csv_text(rows):
    output = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue()


def load_measurements(text):
    rows = list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
    if not rows:
        raise ValueError('Таблица пустая. Нужен CSV UTF-8 с заголовком.')
    required = {'timestamp', 'turbine_id', 'wind_speed_ms', 'temperature_c', 'power_normalized'}
    if not required.issubset(rows[0]):
        raise ValueError('Обязательные столбцы: ' + ', '.join(sorted(required)))
    result, seen = [], set()
    for number, row in enumerate(rows, 2):
        try:
            time = dt(row['timestamp'])
            turbine = row['turbine_id']
            wind, temp, power = (float(row[k]) for k in ('wind_speed_ms', 'temperature_c', 'power_normalized'))
            if turbine not in TURBINES or not np.isfinite([wind, temp, power]).all():
                raise ValueError('неизвестная турбина или нечисловое значение')
            if not (0 <= wind <= 80 and -90 <= temp <= 65 and 0 <= power <= 1):
                raise ValueError('ветер 0–80 м/с, температура −90…65 °C, мощность строго 0…1')
            if time.minute or time.second or time.microsecond:
                raise ValueError('нужны почасовые метки начала интервала')
            key = (time, turbine)
            if key in seen:
                raise ValueError('повтор времени для одной турбины')
            seen.add(key)
            available = dt(row['available_at']) if row.get('available_at') else time + timedelta(hours=1)
            if available < time + timedelta(hours=1):
                raise ValueError('среднее за час доступно только после окончания часа')
            result.append(dict(timestamp=iso(time), available_at=iso(available), turbine_id=turbine,
                               wind_speed_ms=wind, temperature_c=temp, power_normalized=power))
        except (ValueError, KeyError) as error:
            raise ValueError(f'Строка {number}: {error}') from error
    return sorted(result, key=lambda r: (r['timestamp'], r['turbine_id']))


def physical_power(wind, temp, turbine):
    effective = np.asarray(wind) * (1.02 if turbine == 'T1' else .97)
    base = np.clip((effective ** 3 - 3 ** 3) / (12 ** 3 - 3 ** 3), 0, 1)
    return np.clip(base * np.clip(1 - .002 * (np.asarray(temp) - 10), .85, 1.08), 0, 1) * (effective < 25)


def simulated_weather(times):
    hour = np.array([t.timestamp() / 3600 for t in times])
    wind = 7.5 + 3.2 * np.sin(hour / 19) + 1.8 * np.cos(hour / 53) + .7 * np.sin(hour / 3.8)
    temp = 5 + 14 * np.sin(hour / (24 * 365) * 2 * np.pi - 2) + 4 * np.cos(hour / 24 * 2 * np.pi)
    return wind, temp


def demo_measurements():
    start = datetime(2023, 3, 1, tzinfo=LOCAL)
    stop = datetime(2026, 3, 2, tzinfo=LOCAL)
    times = [start + timedelta(hours=i) for i in range(int((stop-start).total_seconds()/3600))]
    wind, temp = simulated_weather(times)
    rng = np.random.default_rng(2026)
    result = []
    for turbine in TURBINES:
        measured_wind = np.maximum(0, wind + rng.normal(0, .35, len(times)))
        power = np.clip(physical_power(measured_wind, temp, turbine) + rng.normal(0, .025, len(times)), 0, 1)
        for i, time in enumerate(times):
            result.append(dict(timestamp=iso(time), available_at=iso(time + timedelta(hours=1)), turbine_id=turbine,
                               wind_speed_ms=round(float(measured_wind[i]), 4), temperature_c=round(float(temp[i]), 4),
                               power_normalized=round(float(power[i]), 5)))
    return result


def demo_weather(issue, horizon, revision=0):
    times = [issue + timedelta(hours=h) for h in range(1, horizon + 1)]
    wind, temp = simulated_weather(times)
    # A synthetic scenario, never a substitute for archived operational forecasts.
    seed = int(issue.timestamp()) + revision * 1009
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, .65, horizon) + np.linspace(0, .45, horizon) * np.sin(seed)
    run = issue - timedelta(hours=6)
    return [dict(turbine_id=t, valid_at=iso(time), run_at=iso(run), available_at=iso(issue-timedelta(hours=1)),
                 wind_speed_ms=round(max(0, float(wind[i]+noise[i])), 4), temperature_c=round(float(temp[i]), 4),
                 source='synthetic', revision=revision)
            for t in TURBINES for i, time in enumerate(times)]


def validate_weather(rows, issue, horizon, demo=False):
    expected = {(t, iso(issue+timedelta(hours=h))) for t in TURBINES for h in range(1, horizon+1)}
    seen = set()
    for row in rows:
        key = (row['turbine_id'], iso(dt(row['valid_at'])))
        if key in seen or key not in expected:
            raise ValueError('Повтор или лишний час в прогнозе погоды')
        seen.add(key)
        run, available = dt(row['run_at']), dt(row['available_at'])
        if not (run <= available <= issue < dt(row['valid_at'])):
            raise ValueError('Утечка будущего: прогноз погоды ещё не был опубликован на момент расчёта')
        allowed = {'synthetic'} if demo else {'noaa-gfs-operational'}
        if row['source'] not in allowed:
            raise ValueError('Нужен архив оперативного прогноза; наблюдения, hindcast и реанализ запрещены')
        wind, temp = float(row['wind_speed_ms']), float(row['temperature_c'])
        if not np.isfinite([wind, temp]).all() or not 0 <= wind <= 80 or not -90 <= temp <= 65:
            raise ValueError('Некорректные единицы или значения погоды')
    if seen != expected:
        raise ValueError(f'Неполный прогноз: получено {len(seen)}, нужно {len(expected)} часов по двум турбинам')


def features(wind, temp):
    w, t = np.asarray(wind), np.asarray(temp)
    return np.column_stack([np.ones(len(w)), t/30, *[np.exp(-((w-c)/2.5)**2) for c in np.arange(0, 29, 2)]])


def fit_model(rows, issue, turbine):
    eligible = sorted([r for r in rows if r['turbine_id'] == turbine and dt(r['timestamp']) < CUTOFF
                       and dt(r['available_at']) <= issue], key=lambda r: r['timestamp'])
    if len(eligible) < 168:
        raise ValueError(f'{turbine}: нужно хотя бы 168 корректных исторических часов до момента расчёта')
    # Last 90 days limits adaptation to distant seasons. Validation remains strictly later than fitting.
    eligible = eligible[-2160:]
    split = int(len(eligible)*.8)
    x = features([r['wind_speed_ms'] for r in eligible], [r['temperature_c'] for r in eligible])
    y = np.array([r['power_normalized'] for r in eligible])
    choices = []
    for alpha in (.01, .3, 3):
        coef = np.linalg.solve(x[:split].T@x[:split] + alpha*np.eye(x.shape[1]), x[:split].T@y[:split])
        pred = np.clip(x[split:]@coef, 0, 1)
        choices.append((float(np.mean(abs(pred-y[split:]))), alpha, np.abs(pred-y[split:])))
    score, alpha, residual = min(choices, key=lambda c: c[0])
    baseline = float(np.mean(abs(y[split:]-np.mean(y[:split]))))
    fallback = score > baseline
    coef = np.linalg.solve(x.T@x + alpha*np.eye(x.shape[1]), x.T@y)
    if fallback:
        residual = abs(y[split:] - np.mean(y[:split]))
    return dict(coef=coef, mean=float(np.mean(y)), fallback=fallback, band=float(np.quantile(residual, .9)),
                info=dict(turbine_id=turbine, model='historical-mean' if fallback else 'RBF ridge', alpha=alpha,
                          validation_mae=score if not fallback else baseline, historical_mean_mae=baseline,
                          fit_rows=len(eligible), train_last=eligible[-1]['timestamp'],
                          validation_note='Валидация на измеренном ветре, не на архивном NWP'),
                persistence=float(y[-1]))


class Agent:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def run(self, measurements, weather, issue, horizon=48, demo=False):
        if horizon not in (24, 48):
            raise ValueError('Горизонт должен быть 24 или 48 часов')
        if issue.minute or issue.second or issue.microsecond:
            raise ValueError('Момент расчёта должен быть на границе часа')
        validate_weather(weather, issue, horizon, demo)
        history = [r for r in measurements if dt(r['timestamp']) < CUTOFF and dt(r['available_at']) <= issue]
        digest = fingerprint(dict(history=history, weather=weather, issue=iso(issue), horizon=horizon, demo=demo, version=1))
        path = self.directory / (digest + '.json')
        if path.exists():
            result = json.loads(path.read_text(encoding='utf-8'))
            result['cache_hit'] = True
            self._audit('cache_hit', digest)
            return result
        events = [dict(step='Проверка данных', detail=f'{len(history):,} исторических строк; будущие измерения исключены'),
                  dict(step='Проверка погоды', detail='Все часы доступны до момента расчёта; происхождение проверено')]
        forecasts, model_info = [], []
        for turbine in TURBINES:
            model = fit_model(history, issue, turbine)
            model_info.append(model['info'])
            part = sorted([r for r in weather if r['turbine_id'] == turbine], key=lambda r: r['valid_at'])
            x = features([r['wind_speed_ms'] for r in part], [r['temperature_c'] for r in part])
            values = np.full(len(part), model['mean']) if model['fallback'] else np.clip(x@model['coef'], 0, 1)
            for row, value in zip(part, values):
                forecasts.append(dict(issue_at=iso(issue), valid_at=row['valid_at'], turbine_id=turbine,
                                      lead_hours=int((dt(row['valid_at'])-issue).total_seconds()/3600),
                                      power_normalized=round(float(value), 5),
                                      lower=round(max(0, float(value)-model['band']), 5),
                                      upper=round(min(1, float(value)+model['band']), 5),
                                      persistence=model['persistence'], wind_speed_ms=row['wind_speed_ms'],
                                      temperature_c=row['temperature_c'], source=row['source'], run_at=row['run_at'],
                                      available_at=row['available_at']))
        events.extend([dict(step='Выбор модели', detail='Хронологическая валидация трёх моделей; контроль против среднего'),
                       dict(step='Прогноз готов', detail=f'{horizon} часов × 2 турбины; версия {digest[:8]}')])
        result = dict(demo=demo, issue_at=iso(issue), horizon=horizon, fingerprint=digest, cache_hit=False,
                      forecasts=forecasts, models=model_info, events=events,
                      uncertainty_note='Полоса — историческая ошибка модели на измеренном ветре. Не учитывает всю ошибку NWP и не является гарантированным 90% интервалом.')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
        self._audit('forecast_created', digest)
        return result

    def _audit(self, event, digest):
        with (self.directory / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(at=iso(datetime.now(UTC)), event=event, fingerprint=digest))+'\n')


def evaluate(forecasts, actuals):
    truth = {(r['turbine_id'], r['timestamp']): r['power_normalized'] for r in actuals}
    end = datetime(2026, 3, 1, tzinfo=LOCAL).astimezone(UTC)
    groups = []
    for turbine in TURBINES:
        for low, high in ((1, 24), (25, 48)):
            pairs = [(r, truth[(turbine, r['valid_at'])]) for r in forecasts if r['turbine_id'] == turbine
                     and low <= r['lead_hours'] <= high and CUTOFF <= dt(r['valid_at']) < end
                     and (turbine, r['valid_at']) in truth]
            if not pairs:
                continue
            errors = np.array([r['power_normalized']-y for r, y in pairs])
            persistence = np.array([r['persistence']-y for r, y in pairs])
            groups.append(dict(turbine_id=turbine, horizon=f'{low}–{high}', n=len(pairs),
                               mae=float(np.mean(abs(errors))), rmse=float(np.sqrt(np.mean(errors**2))),
                               persistence_mae=float(np.mean(abs(persistence))),
                               band_coverage=float(np.mean([r['lower'] <= y <= r['upper'] for r, y in pairs]))))
    return groups


def backtest(measurements, agent, provider):
    all_rows = []
    for day in range(28):
        issue = datetime(2026, 1, 31, 23, tzinfo=LOCAL)+timedelta(days=day)
        weather, demo = provider(issue, 48)
        all_rows.extend(agent.run(measurements, weather, issue, 48, demo)['forecasts'])
    return dict(metrics=evaluate(all_rows, measurements), forecasts=all_rows, origins=28,
                note='672 часа на турбину для горизонта 1–24; 25–48 оценивается отдельно, до 28 февраля.')
