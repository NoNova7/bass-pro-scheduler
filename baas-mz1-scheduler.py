import json
import time
import subprocess
import logging
import os
from datetime import datetime, date, time as dt_time
import threading
from dataclasses import dataclass
import requests
from schedule import every, repeat, run_pending, idle_seconds


class Configuration:
    def __init__(self,
                 name: str,
                 instance: int,
                 only_daily_task: bool = True,
                 endday_jjc: bool = False
                 ):

        self.name = name
        self.only_daily_task = only_daily_task
        self.instance = instance
        self.endday_jjc = endday_jjc

        self.path = os.path.join(r'C:\baas-pro\baas-pro\configs', f'{name}.json')
        self.time_off = 0


CONFIGURATIONS = [
    Configuration('1-梦之一', 1, False, False),
    Configuration('9-狸豚', 2),
    Configuration('7-很厉害1', 4),
    Configuration('8-很厉害2', 3),
]

NEXT_ACTIVITY_DATE = date(2025, 12, 18)

for index, config in enumerate(CONFIGURATIONS):
    config.time_off = index


@dataclass(frozen=True)
class Activity():
    CAFE = 'cafe'
    EXCHANGE = 'exchange_meeting'
    WANT = 'wanted'
    JJC = 'arena'
    SHOP = 'shop'
    RICHENG = 'schedule'
    GROUP = 'group'
    HARD = 'hard_task'
    NORMAL = 'normal_task'
    CN_ACTIVITY = 'cn_activity'
    MOMO_TALK = 'momo_talk'


# Configure logging
logging.basicConfig(
    filename=r'C:\scripting\mz1-baas-log.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def set_timeout(func, seconds, *args, **kwargs):
    def runner():
        try:
            func(*args, **kwargs)
        except Exception:
            logging.exception("set_timeout task failed")
    t = threading.Timer(seconds, runner)
    t.daemon = True
    t.start()
    return t


def read_json(path):

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error reading {path}: {e}")
        return {}


def write_json(path, data):

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    except Exception as e:
        logging.error(f"Error writing {path}: {e}")


def toggle_next_time(data, key, value, config_name):

    # just let it crash
    if data[key]['base'].get('next') != value:
        data[key]['base']['next'] = value
        logging.info(f"Updated {key} - {value} for {config_name}")

    return data


def toggle_invite_enable(data, enable, mode, config_name):

    if mode == '':
        mode = 'invite'

    if data[Activity.CAFE][mode].get('enable') != enable:
        data[Activity.CAFE][mode]['enable'] = enable
        logging.info(f"Cafe {mode} {'enabled' if enable else 'disabled'} for {config_name}")

    return data


def toggle_activity_enable(data, key, enable, config_name):

    if data[key]['base'].get('enable') != enable:
        data[key]['base']['enable'] = enable
        logging.info(f"{key} {'enabled' if enable else 'disabled'} for {config_name}")

    return data


def restart_mumu_instance(config: Configuration, mode: str = "R"):

    if mode == "R":
        mode = "restart"
    if mode == 'L':
        mode = "launch"
    if mode == "S":
        mode = "shutdown"

    mumu_manager = r'C:\Program Files\Netease\MuMu Player 12\nx_main\MuMuManager.exe'
    args = ['control', '-v', str(config.instance), mode]

    subprocess.Popen([mumu_manager] + args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    logging.info(f"{mode} Mumu {config.name}: {mumu_manager} {args}")


def update_daily_tasks(data, value, incl_cafe, config_name):

    update_keys = [
        Activity.HARD,
        Activity.GROUP,
        Activity.SHOP,
        Activity.WANT,
        Activity.EXCHANGE,
        Activity.JJC,
        Activity.NORMAL,
        Activity.RICHENG,
        Activity.CN_ACTIVITY,
        Activity.MOMO_TALK
    ]

    if incl_cafe:
        update_keys.append(Activity.CAFE)

    for key in update_keys:
        if data[key]['base']['next'] != value:
            data[key]['base']['next'] = value
            logging.info(f"Updated {key} - {value} for {config_name}")

    return data


def start_baas(config: Configuration, mode: str):
    assert mode in ('start', 'stop')
    try:
        resp = requests.get(f'http://localhost:7111/baas/{mode}/{config.name}', timeout=5)
        logging.info(f"baas {mode}: {resp.status_code} for {config.name}")
    except requests.RequestException as e:
        logging.exception(f"baas {mode} request failed for {config.name}: {e}")


def get_daily_task_timeoff(config: Configuration) -> tuple[int, int]:
    minutes_total = config.time_off * 15
    hour = 5 + minutes_total // 60
    minute = minutes_total % 60
    return hour, minute


@repeat(every().day.at("03:55"))
def update_midnight():

    for config in CONFIGURATIONS:

        daily_time_off_hour, daily_time_off_minute = get_daily_task_timeoff(config)

        data = read_json(config.path)
        time_str = f'{date.today()} {daily_time_off_hour:02d}:{daily_time_off_minute:02d}:00'
        data = update_daily_tasks(data, time_str, config.only_daily_task, config.name)
        data = toggle_invite_enable(data, False, 'ap', config.name)

        if not config.only_daily_task:
            data = toggle_next_time(data, Activity.CAFE, time_str, config.name)
            data = toggle_invite_enable(data, True, '', config.name)

        if config.endday_jjc:
            data = toggle_activity_enable(data, Activity.JJC, False, config.name)

        write_json(config.path, data)


@repeat(every().day.at("15:55"))
def update_afternoon():

    for config in CONFIGURATIONS:
        if config.only_daily_task:
            continue

        daily_time_off_hour, daily_time_off_minute = get_daily_task_timeoff(config)
        time_str = f'{date.today()} {daily_time_off_hour+11:02d}:{daily_time_off_minute:02d}:00'

        data = read_json(config.path)
        data = toggle_next_time(data, Activity.CAFE, time_str, config.name)
        data = toggle_invite_enable(data, False, '', config.name)

        write_json(config.path, data)


@repeat(every().day.at("03:30"))
def update_endday_jjc():

    for config in CONFIGURATIONS:
        if not config.endday_jjc:
            continue

        data = read_json(config.path)
        data = toggle_activity_enable(data, Activity.JJC, True, config.name)
        write_json(config.path, data)


@repeat(every().day.at("04:59"), "daily_start")
@repeat(every().day.at("07:59"))
@repeat(every().day.at("10:59"))
@repeat(every().day.at("13:59"))
@repeat(every().day.at("15:59"))
@repeat(every().day.at("18:30"), "activity_start")
@repeat(every().day.at("21:59"))
@repeat(every().day.at("00:59"))
def update_mumu_emulator(flag: str | None = None):

    for config in CONFIGURATIONS:
        time_off = config.time_off * 15 * 60

        if NEXT_ACTIVITY_DATE == date.today():
            if flag == 'activity_start':
                update_activity_cn(config, time_off*2)
                continue
            if datetime.now().time() > dt_time(13, 50):
                continue

        if config.only_daily_task:
            if flag == 'daily_start':
                set_timeout(restart_mumu_instance, time_off, config, 'L')
                set_timeout(start_baas, time_off+60, config, 'start')

                set_timeout(start_baas, time_off+3600, config, 'stop')
                set_timeout(restart_mumu_instance, time_off+3605, config, "S")

            continue

        data = read_json(config.path)
        target_time = datetime.strptime(data[Activity.CAFE]['base'].get('next'), "%Y-%m-%d %H:%M:%S")
        delta = target_time - datetime.now()
        if delta.total_seconds() > 60:
            set_timeout(restart_mumu_instance, delta.total_seconds()-60, config)
            set_timeout(start_baas, delta.total_seconds(), config, 'start')


def update_activity_cn(config: Configuration, time_off: int):

    if '很厉害' in config.name:
        start_baas(config, "start")


def main():

    print('baas-mz1-schedule started!')

    for config in CONFIGURATIONS:
        data = read_json(config.path)
        if not data:
            raise ValueError(f"Config {config.path} read failed")

        data = toggle_invite_enable(data, False, '', config.name)
        data = toggle_invite_enable(data, False, 'ap', config.name)
        write_json(config.path, data)

    while True:
        run_pending()
        n = idle_seconds()
        if n is None:   # won’t happen with daily jobs, but safe
            break
        elif n > 0:
            time.sleep(n)


if __name__ == "__main__":
    main()
