#!/usr/bin/env python3

from os import error, path
import sys
import time
import yaml
import signal
import pathlib
import argparse
import threading
import paho.mqtt.client as mqtt

from sensors import *


mqttClient = None
global poll_interval
devicename = None
settings = {}

class ProgramKilled(Exception):
    pass

def signal_handler(signum, frame):
    raise ProgramKilled

class Job(threading.Thread):
    def __init__(self, interval, execute, *args, **kwargs):
        threading.Thread.__init__(self)
        self.daemon = False
        self.stopped = threading.Event()
        self.interval = interval
        self.execute = execute
        self.args = args
        self.kwargs = kwargs

    def stop(self):
        self.stopped.set()
        self.join()

    def run(self):
        while not self.stopped.wait(self.interval.total_seconds()):
            self.execute(*self.args, **self.kwargs)


def update_sensors():
    payload_str = f'{{'
    payload_str = payload_str[:-1]
    payload_str += f'}}'
    topic = f'system-sensors/sensor/{devicename}/state'
    pub_ret = mqttClient.publish(
        topic=topic,
        payload=payload_str,
        qos=1,
        retain=False)
    print(f"{pub_ret} from publish(topic={topic}, payload={payload_str})")


def send_config_message(mqttClient):

    write_message_to_console('Sending config message to host...')

    for sensor, attr in sensors.items():
        try:
            # Added check in case sensor is an external drive, which is nested in the config
            if settings['sensors'][sensor]:
                topic = f'homeassistant/{attr["sensor_type"]}/{devicename}/{sensor}/config'
                payload = (f'{{'
                        + (f'"device_class":"{attr["class"]}",' if 'class' in attr else '')
            + (f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else '')
                        + f'"name":"{deviceNameDisplay} {attr["name"]}",'
                        + f'"state_topic":"system-sensors/sensor/{devicename}/state",'
                        + (f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else '')
                        + f'"value_template":"{{{{value_json.{sensor}}}}}",'
                        + f'"unique_id":"{devicename}_{attr["sensor_type"]}_{sensor}",'
                        + f'"availability_topic":"system-sensors/sensor/{devicename}/availability",'
                        + f'"device":{{"identifiers":["{devicename}_sensor"],'
                        + f'"name":"{deviceNameDisplay} Sensors"}}'
                        + (f',"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else '')
                            + (f',{attr["prop"]}' if 'prop' in attr else '')
                        + f'}}'
                        )
                print("publish topic=", topic)
                print("payload", payload)           
                mqttClient.publish(
                    topic = topic,
                    payload = payload,
                    qos=1,
                    retain=True,
                )
        except Exception as e:
            write_message_to_console('An error was produced while processing ' + str(sensor) + ' with exception: ' + str(e))
            print(str(settings))
            raise
        
    mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'online', retain=True)

def _parser():
    """Generate argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument('settings', help='path to the settings file')
    return parser


def check_settings(settings):
    for value in ['mqtt', 'timezone', 'devicename', 'client_id', 'update_interval']:
        if value not in settings:
            write_message_to_console(value + ' not defined in settings.yaml! Please check the documentation')
            sys.exit()
    if 'hostname' not in settings['mqtt']:
        write_message_to_console('hostname not defined in settings.yaml! Please check the documentation')
        sys.exit()
    if 'user' in settings['mqtt'] and 'password' not in settings['mqtt']:
        write_message_to_console('password not defined in settings.yaml! Please check the documentation')
        sys.exit()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        write_message_to_console('Connected to broker')
        print("subscribing : hass/status")
        client.subscribe('hass/status')
        print("subscribing : " + f"system-sensors/sensor/{devicename}/availability")
        mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'online', retain=True)
        print("subscribing : " + f"system-sensors/sensor/{devicename}/command")
        client.subscribe(f"system-sensors/sensor/{devicename}/command")#subscribe
        client.publish(f"system-sensors/sensor/{devicename}/command", "setup", retain=True)
    elif rc == 5:
        write_message_to_console('Authentication failed.\n Exiting.')
        sys.exit()
    else:
        write_message_to_console('Connection failed')


def on_message(client, userdata, message):
    print (f'Message received: {message.payload.decode()}'  )
    if message.payload.decode() == 'online':
        send_config_message(client)
    elif message.payload.decode() == "display_on":
        reading = subprocess.check_output([vcgencmd, "display_power", "1"]).decode("UTF-8")
        update_sensors()
    elif message.payload.decode() == "display_off":
        reading = subprocess.check_output([vcgencmd, "display_power", "0"]).decode("UTF-8")
        update_sensors()


if __name__ == '__main__':
    try:
        args = _parser().parse_args()
        settings_file = args.settings
    except:
        write_message_to_console('Could not find settings.yaml. Please check the documentation')
        exit()

    with open(settings_file) as f:
        settings = yaml.safe_load(f)

    # Make settings file keys all lowercase
    settings = {k.lower(): v for k,v in settings.items()}
    # Check for settings that will prevent the script from communicating with MQTT broker or break the script
    check_settings(settings)

    devicename = settings['devicename'].replace(' ', '').lower()   
    deviceNameDisplay = settings['devicename']
    
    mqttClient = mqtt.Client(client_id=settings['client_id'])
    mqttClient.on_connect = on_connect                      #attach function to callback
    mqttClient.on_message = on_message
    mqttClient.will_set(f'system-sensors/sensor/{devicename}/availability', 'offline', retain=True)
    if 'user' in settings['mqtt']:
        mqttClient.username_pw_set(
            settings['mqtt']['user'], settings['mqtt']['password']
        )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            mqttClient.connect(settings['mqtt']['hostname'], settings['mqtt']['port'])
            break
        except ConnectionRefusedError:
            # sleep for 2 minutes if broker is unavailable and retry.
            # Make this value configurable?
            # this feels like a dirty hack. Is there some other way to do this?
            time.sleep(120)
        except OSError:
            # sleep for 10 minutes if broker is not reachable, i.e. network is down
            # Make this value configurable?
            # this feels like a dirty hack. Is there some other way to do this?
            time.sleep(600)
    try:
        send_config_message(mqttClient)
    except Exception as e:
        write_message_to_console('Error while attempting to send config to MQTT host: ' + str(e))
        exit()
    try:
        update_sensors()
    except Exception as e:
        write_message_to_console('Error while attempting to perform inital sensor update: ' + str(e))
        exit()

    job = Job(interval=dt.timedelta(seconds=settings["update_interval"]), execute=update_sensors)
    job.start()

    mqttClient.loop_start()

    while True:
        try:
            sys.stdout.flush()
            time.sleep(1)
        except ProgramKilled:
            write_message_to_console('Program killed: running cleanup code')
            mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'offline', retain=True)
            mqttClient.disconnect()
            mqttClient.loop_stop()
            sys.stdout.flush()
            job.stop()
            break
