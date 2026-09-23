"""Watch revised, user-supplied inputs for one fixed historical forecast origin."""
import argparse
import json
import time
from pathlib import Path

from wind.core import Agent, csv_text, dt, load_measurements


def main():
    parser = argparse.ArgumentParser(description='Пересчитывать прогноз при обновлении входных файлов')
    parser.add_argument('--measurements', type=Path, required=True)
    parser.add_argument('--weather-file', type=Path, required=True)
    parser.add_argument('--issue', required=True)
    parser.add_argument('--horizon', type=int, choices=[24, 48], default=48)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--cycles', type=int, default=0, help='0 — до Ctrl+C')
    args = parser.parse_args()
    if args.interval < 5 or args.cycles < 0:
        parser.error('--interval минимум 5 секунд, --cycles неотрицательный')
    root = Path(__file__).resolve().parent / 'runtime'
    agent = Agent(root / 'runs')
    previous = None
    cycle = 0
    while True:
        try:
            history = load_measurements(args.measurements.read_text(encoding='utf-8-sig'))
            weather = json.loads(args.weather_file.read_text(encoding='utf-8'))
            result = agent.run(history, weather, dt(args.issue), args.horizon, demo=False)
            if result['fingerprint'] != previous:
                temporary = root / 'watch-forecast.tmp'
                temporary.write_text(csv_text(result['forecasts']), encoding='utf-8-sig')
                temporary.replace(root/'watch-forecast.csv')
                previous = result['fingerprint']
                print('Прогноз обновлён: '+previous[:12], flush=True)
        except (ValueError, OSError, KeyError) as error:
            print('Входные данные не готовы: '+str(error), flush=True)
        cycle += 1
        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Наблюдение остановлено.')
