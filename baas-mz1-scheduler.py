import json
from time import sleep
import subprocess
import logging
import os
from datetime import datetime, date, timedelta
import threading
from dataclasses import dataclass
import requests
from schedule import every, repeat, run_pending, idle_seconds


NEXT_ACTIVITY_DATE = date(2026, 1, 8)


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


def toggle_cafe_enable(data, enable, mode, config_name):

    # mode = invite or ap

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


def restart_mumu_instance(config: Configuration, mode: str):

    assert mode in ('restart', 'launch', 'shutdown')

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


def get_task_time_off(minutes_after, hour=None):

    today = datetime.now().date()
    if hour is None:
        hour = 5

    base_dt = datetime.combine(today, datetime.min.time()).replace(hour=hour)

    result_dt = base_dt + timedelta(seconds=minutes_after*60)

    return result_dt.strftime("%Y-%m-%d %H:%M:%S")


@repeat(every().day.at("03:55"))
def update_midnight():

    for config in CONFIGURATIONS:

        data = read_json(config.path)
        time_str = get_task_time_off(config.time_off*15)
        data = update_daily_tasks(data, time_str, config.only_daily_task, config.name)
        data = toggle_cafe_enable(data, False, 'ap', config.name)

        if not config.only_daily_task:
            data = toggle_next_time(data, Activity.CAFE, time_str, config.name)
            data = toggle_cafe_enable(data, True, 'invite', config.name)

        if config.endday_jjc:
            data = toggle_activity_enable(data, Activity.JJC, False, config.name)

        write_json(config.path, data)


@repeat(every().day.at("15:55"))
def update_afternoon():

    for config in CONFIGURATIONS:
        if config.only_daily_task:
            continue

        time_str = get_task_time_off(config.time_off*15, 16)

        data = read_json(config.path)
        data = toggle_next_time(data, Activity.CAFE, time_str, config.name)
        data = toggle_cafe_enable(data, False, 'invite', config.name)

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
def update_mumu_emulator(flag: str | None = None):

    for config in CONFIGURATIONS:
        if not config.only_daily_task:
            continue

        time_off = config.time_off * 15 * 60

        set_timeout(restart_mumu_instance, time_off, config, 'launch')
        set_timeout(start_baas, time_off+30, config, 'start')

        set_timeout(start_baas, time_off+3600, config, 'stop')
        set_timeout(restart_mumu_instance, time_off+3605, config, "shutdown")


@repeat(every().day.at("04:57"))
@repeat(every().day.at("07:59"))
@repeat(every().day.at("10:59"))
@repeat(every().day.at("13:59"))
@repeat(every().day.at("15:57"))
@repeat(every().day.at("21:59"))
@repeat(every().day.at("00:59"))
def restart_mumu_emulator():

    if date.today() == NEXT_ACTIVITY_DATE:
        if datetime.now().strftime("%H:%M") in {"13:59", "15:57"}:
            return

    for config in CONFIGURATIONS:
        if config.only_daily_task:
            continue

        data = read_json(config.path)
        target_time = datetime.strptime(data[Activity.CAFE]['base'].get('next'), "%Y-%m-%d %H:%M:%S")
        delta = target_time - datetime.now()
        if delta.total_seconds() > 60:
            set_timeout(restart_mumu_instance, delta.total_seconds()-60, config, 'restart')
            set_timeout(start_baas, delta.total_seconds()-30, config, 'start')


@repeat(every().day.at("19:00"))
def update_activity_cn():

    if date.today() != NEXT_ACTIVITY_DATE:
        return

    for config in CONFIGURATIONS:
        if '很厉害' in config.name:
            restart_mumu_instance(config, 'launch')
            set_timeout(start_baas, 30, config, 'start')

            set_timeout(start_baas, 3600*2, config, 'stop')
            set_timeout(restart_mumu_instance, 3605*2, config, "shutdown")


@repeat(every().day.at("21:00"))
def update_activity_cn_2():

    if date.today() != NEXT_ACTIVITY_DATE:
        return

    for config in CONFIGURATIONS:
        if '很厉害' in config.name:
            continue

        if config.only_daily_task:
            mode = 'launch'
        else:
            mode = 'restart'
        restart_mumu_instance(config, mode)
        set_timeout(start_baas, 30, config, 'start')

        if config.only_daily_task:
            set_timeout(start_baas, 3600*2, config, 'stop')
            set_timeout(restart_mumu_instance, 3605*2, config, "shutdown")


def main():

    print('baas-mz1-schedule started!')

    for config in CONFIGURATIONS:
        data = read_json(config.path)
        if not data:
            raise ValueError(f"Config {config.path} read failed")

        data = toggle_cafe_enable(data, False, 'invite', config.name)
        data = toggle_cafe_enable(data, False, 'ap', config.name)
        write_json(config.path, data)

    while True:
        run_pending()
        n = idle_seconds()
        if n is None:   # won’t happen with daily jobs, but safe
            break
        elif n > 0:
            sleep(n)


if __name__ == "__main__":
    main()
