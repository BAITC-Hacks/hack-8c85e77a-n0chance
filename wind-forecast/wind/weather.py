"""Operational NOAA GFS archives with publication-time checks and bounded byte-range reads."""
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from .core import TURBINES, UTC, dt, iso, validate_weather

BASE = 'https://noaa-gfs-bdp-pds.s3.amazonaws.com/'


def request(url, headers=None, limit=8_000_000):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'WindForecastMVP/1.0', **(headers or {})})
            with urllib.request.urlopen(req, timeout=45) as response:
                if headers and 'Range' in headers and response.status != 206:
                    raise ValueError('Сервер не поддержал Range: загрузка полного GRIB запрещена')
                body = response.read(limit+1)
                if len(body) > limit:
                    raise ValueError('Ответ превысил допустимый размер')
                return body, dict(response.headers)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(.5 * 2**attempt)


def published(headers, issue):
    lookup = {k.lower(): v for k, v in headers.items()}
    if 'last-modified' not in lookup:
        raise ValueError('Нет подтверждения времени публикации NOAA')
    value = parsedate_to_datetime(lookup['last-modified']).astimezone(UTC)
    if value > issue:
        raise ValueError('Этот архивный объект опубликован позже момента расчёта')
    return value


def ranges_from_index(content, wind_height=100):
    lines = [line.split(':') for line in content.splitlines() if line.strip()]
    needed = [('UGRD', f'{wind_height} m above ground'), ('VGRD', f'{wind_height} m above ground'), ('TMP', '2 m above ground')]
    result = {}
    for i, row in enumerate(lines):
        for variable, level in needed:
            if len(row) > 5 and row[3] == variable and row[4] == level:
                if i+1 >= len(lines):
                    raise ValueError('Неизвестен конец GRIB-сообщения')
                result[variable] = (int(row[1]), int(lines[i+1][1])-1)
    if len(result) != 3:
        raise ValueError('В архиве нет нужных компонентов ветра и температуры')
    return result


def decode(message, run, lead, variable, height):
    try:
        import eccodes as ec
    except ImportError as error:
        raise ValueError('Для NOAA установите зависимости: python -m pip install -r requirements-weather.txt') from error
    handle = ec.codes_new_from_message(message)
    try:
        if int(ec.codes_get(handle, 'dataDate')) != int(run.strftime('%Y%m%d')) or int(ec.codes_get(handle, 'dataTime')) != run.hour*100:
            raise ValueError('GRIB содержит другой запуск модели')
        if int(ec.codes_get(handle, 'endStep')) != lead:
            raise ValueError('GRIB содержит другой горизонт')
        expected_level = 2 if variable == 'TMP' else height
        if ec.codes_get(handle, 'typeOfLevel') != 'heightAboveGround' or int(ec.codes_get(handle, 'level')) != expected_level:
            raise ValueError('Неверная высота GRIB')
        expected_parameter = {'TMP': 0, 'UGRD': 2, 'VGRD': 3}[variable]
        expected_category = 0 if variable == 'TMP' else 2
        if int(ec.codes_get(handle, 'parameterNumber')) != expected_parameter or int(ec.codes_get(handle, 'parameterCategory')) != expected_category:
            raise ValueError('Неверная переменная GRIB')
        return {t: dict(ec.codes_grib_find_nearest(handle, lat, lon)[0]) for t, (lat, lon) in TURBINES.items()}
    finally:
        ec.codes_release(handle)


class GFS:
    def __init__(self, directory, height=100):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if height not in (10, 100):
            raise ValueError('Поддерживаемая высота ветра: 10 или 100 м')
        self.height = height
        self.decisions = []

    def hour(self, run, lead, issue):
        key = f'gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{lead:03d}'
        cache = self.directory / f'{run:%Y%m%d%H}-{lead:03d}-{self.height}.json'
        if cache.exists():
            record = json.loads(cache.read_text(encoding='utf-8'))
            if dt(record['available_at']) > issue:
                raise ValueError('Закэшированный прогноз ещё не был опубликован')
            return record
        index, index_headers = request(BASE+key+'.idx', limit=200_000)
        available = published(index_headers, issue)
        fields, evidence = {}, []
        for variable, (start, end) in ranges_from_index(index.decode(), self.height).items():
            raw, headers = request(BASE+key, {'Range': f'bytes={start}-{end}'})
            lower_headers = {k.lower(): v for k, v in headers.items()}
            if not lower_headers.get('content-range', '').startswith(f'bytes {start}-{end}/') or len(raw) != end-start+1:
                raise ValueError('Неполный или неверный диапазон байтов GRIB')
            available = max(available, published(headers, issue))
            fields[variable] = decode(raw, run, lead, variable, self.height)
            evidence.append(dict(url=BASE+key, byte_range=f'{start}-{end}', etag=lower_headers.get('etag'),
                                 last_modified=lower_headers.get('last-modified'), sha256=hashlib.sha256(raw).hexdigest(),
                                 variable=variable))
        values = {}
        for turbine in TURBINES:
            values[turbine] = dict(wind_speed_ms=math.hypot(fields['UGRD'][turbine]['value'], fields['VGRD'][turbine]['value']),
                                   temperature_c=fields['TMP'][turbine]['value']-273.15,
                                   grid_lat=fields['TMP'][turbine]['lat'], grid_lon=fields['TMP'][turbine]['lon'])
        record = dict(run_at=iso(run), valid_at=iso(run+timedelta(hours=lead)), available_at=iso(available),
                      values=values, evidence=evidence, source='noaa-gfs-operational', wind_height_m=self.height)
        temporary = cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(record), encoding='utf-8')
        temporary.replace(cache)
        return record

    def forecast(self, issue, horizon):
        # Conservative six-hour lag plus actual object Last-Modified checks.
        candidate = (issue-timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
        candidate = candidate.replace(hour=candidate.hour//6*6)
        for attempt in range(3):
            run = candidate-timedelta(hours=6*attempt)
            try:
                records = [self.hour(run, int((issue-run).total_seconds()/3600)+h, issue) for h in range(1, horizon+1)]
                rows = [dict(turbine_id=t, valid_at=r['valid_at'], run_at=r['run_at'], available_at=r['available_at'],
                             wind_speed_ms=r['values'][t]['wind_speed_ms'], temperature_c=r['values'][t]['temperature_c'],
                             source=r['source'], evidence=r['evidence'], wind_height_m=self.height)
                        for r in records for t in TURBINES]
                validate_weather(rows, issue, horizon)
                self.decisions.append(dict(run_at=iso(run), selected=True))
                return rows
            except (ValueError, urllib.error.URLError, TimeoutError) as error:
                self.decisions.append(dict(run_at=iso(run), selected=False, reason=str(error)))
        raise ValueError('Не найден полный архив, доступный на момент расчёта. ' + json.dumps(self.decisions[-3:], ensure_ascii=False))
