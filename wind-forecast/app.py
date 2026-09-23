import argparse
import json
import os
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from wind.core import Agent, LOCAL, backtest, csv_text, demo_measurements, demo_weather, dt, iso, load_measurements

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'


def main():
    parser = argparse.ArgumentParser(description='WIND — прогноз выработки ВЭС')
    parser.add_argument('command', choices=['serve', 'demo', 'forecast', 'backtest', 'weather'], nargs='?', default='serve')
    parser.add_argument('--port', type=int, default=5180)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--measurements', type=Path)
    parser.add_argument('--weather-file', type=Path)
    parser.add_argument('--issue', default='2026-01-31T23:00:00+05:00')
    parser.add_argument('--horizon', type=int, choices=[24, 48], default=48)
    parser.add_argument('--height', type=int, choices=[10, 100], default=100)
    parser.add_argument('--real', action='store_true', help='Использовать измерения и оперативный архив NOAA')
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    agent = Agent(RUNTIME/'runs')
    if args.command == 'serve':
        serve(args.port, args.open, agent)
        return
    issue = dt(args.issue)
    if args.command == 'weather':
        from wind.weather import GFS
        weather = GFS(RUNTIME/'weather', args.height).forecast(issue, args.horizon)
        path = RUNTIME/'weather.json'
        path.write_text(json.dumps(weather, indent=2), encoding='utf-8')
        print(path)
        return
    if args.real:
        if not args.measurements:
            parser.error('--real требует --measurements путь.csv')
        measurements = load_measurements(args.measurements.read_text(encoding='utf-8-sig'))
        from wind.weather import GFS
        provider = GFS(RUNTIME/'weather', args.height)
        weather = json.loads(args.weather_file.read_text()) if args.weather_file else None
    else:
        if args.measurements or args.weather_file:
            parser.error('Чтобы использовать собственные файлы, добавьте --real')
        measurements = demo_measurements()
        provider, weather = None, None
    if args.command == 'backtest':
        if args.weather_file:
            parser.error('Backtest загружает отдельный оперативный запуск на каждую дату; --weather-file здесь не применяется')
        result = backtest(measurements, agent, lambda origin, horizon: (provider.forecast(origin, horizon), False) if args.real else (demo_weather(origin, horizon), True))
    else:
        rows = (weather if weather is not None else provider.forecast(issue, args.horizon)) if args.real else demo_weather(issue, args.horizon)
        result = agent.run(measurements, rows, issue, args.horizon, demo=not args.real)
    (RUNTIME/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (RUNTIME/'forecast.csv').write_text(csv_text(result['forecasts']), encoding='utf-8-sig')
    print(json.dumps(dict(demo=not args.real, forecast_rows=len(result['forecasts']), metrics=result.get('metrics'), output=str(RUNTIME)), ensure_ascii=False))


def serve(port, open_browser, agent):
    state = {'measurements': demo_measurements(), 'mode': 'demo', 'revision': 0, 'result': None, 'backtest': None}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            data = (json.dumps(body, ensure_ascii=False, allow_nan=False).encode() if isinstance(body, (dict, list)) else body)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in assets:
                filename, mime = assets[path]
                self.reply(200, (ROOT/'web'/filename).read_bytes(), mime)
            elif path == '/api/status':
                self.reply(200, dict(mode=state['mode'], rows=len(state['measurements']), result=state['result'], backtest=state['backtest']))
            elif path == '/api/export':
                with lock:
                    data = csv_text(state['result']['forecasts'] if state['result'] else [])
                self.reply(200, ('\ufeff'+data).encode(), 'text/csv; charset=utf-8')
            elif path == '/api/template':
                self.reply(200, (ROOT/'examples'/'measurements.csv').read_bytes(), 'text/csv; charset=utf-8')
            else:
                self.reply(404, {'error': 'Не найдено'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if self.headers.get('Host') not in {f'localhost:{port}', f'127.0.0.1:{port}'} or (origin and origin not in {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}):
                self.reply(403, {'error': 'Недопустимый источник запроса'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 20_000_000:
                    raise ValueError('Допустимый размер: до 20 МБ')
                payload = json.loads(self.rfile.read(length))
                with lock:
                    if self.path == '/api/import':
                        measurements = load_measurements(payload['csv'])
                        state.update(measurements=measurements, mode='real', result=None, backtest=None)
                        response = dict(rows=len(measurements), mode='real')
                    elif self.path == '/api/demo':
                        state.update(measurements=demo_measurements(), mode='demo', result=None, backtest=None, revision=0)
                        response = {'ok': True}
                    elif self.path == '/api/run':
                        issue, horizon = dt(payload['issue']), int(payload.get('horizon', 48))
                        if horizon not in (24, 48):
                            raise ValueError('Выберите 24 или 48 часов')
                        if state['mode'] == 'real':
                            from wind.weather import GFS
                            weather = GFS(RUNTIME/'weather').forecast(issue, horizon)
                        else:
                            state['revision'] += int(bool(payload.get('update')))
                            weather = demo_weather(issue, horizon, state['revision'])
                        state['result'] = agent.run(state['measurements'], weather, issue, horizon, state['mode']=='demo')
                        response = state['result']
                    elif self.path == '/api/backtest':
                        if state['mode'] != 'demo':
                            raise ValueError('Для полного расчёта NOAA используйте команду backtest --real из README: скачивание архива может занять долгое время.')
                        result = backtest(state['measurements'], agent, lambda origin, horizon: (demo_weather(origin, horizon), True))
                        state['backtest'] = {k:v for k,v in result.items() if k != 'forecasts'}
                        response = state['backtest']
                    else:
                        self.reply(404, {'error': 'Не найдено'})
                        return
                self.reply(200, response)
            except (ValueError, KeyError, OSError) as error:
                self.reply(400, {'error': str(error)})
            except Exception:
                import traceback
                traceback.print_exc()
                self.reply(500, {'error': 'Расчёт не завершён. Подробности в окне запуска.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'WIND: http://localhost:{port} — Ctrl+C для остановки', flush=True)
    if open_browser:
        webbrowser.open(f'http://localhost:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
