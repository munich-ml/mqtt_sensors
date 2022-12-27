#!/usr/bin/env python3

import psutil, socket, subprocess, sys


# Temperature method depending on system distro
def get_temp():
    temp = 'Unknown'
    # Utilising psutil for temp reading on ARM arch
    try:
        t = psutil.sensors_temperatures()
        for x in ['cpu-thermal', 'cpu_thermal', 'coretemp', 'soc_thermal', 'k10temp']:
            if x in t:
                temp = t[x][0].current
                break
    except Exception as e:
            print('Could not establish CPU temperature reading: ' + str(e))
            raise
    return round(temp, 1) if temp != 'Unknown' else temp


def get_wifi_strength():  # subprocess.check_output(['/proc/net/wireless', 'grep wlan0'])
    wifi_strength_value = subprocess.check_output(
                              [
                                  'bash',
                                  '-c',
                                  'cat /proc/net/wireless | grep wlan0: | awk \'{print int($4)}\'',
                              ]
                          ).decode('utf-8').rstrip()
    if not wifi_strength_value:
        wifi_strength_value = '0'
    return (wifi_strength_value)


def get_host_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except socket.error:
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return '127.0.0.1'
    finally:
        sock.close()


def hex2addr(hex_addr):
    l = len(hex_addr)
    first = True
    ip = ""
    for i in range(l // 2):
        if (first != True):
            ip = "%s." % ip
        else:
            first = False
        ip = ip + ("%d" % int(hex_addr[-2:], 16))
        hex_addr = hex_addr[:-2]
    return ip


sensors = {
          'hostname':
                {'name': 'Hostname',
                 'icon': 'card-account-details',
                 'sensor_type': 'sensor',
                 'function': socket.gethostname},
          'host_ip':
                {'name': 'Host IP',
                 'icon': 'lan',
                 'sensor_type': 'sensor',
                 'function': get_host_ip},
          'temperature':
                {'name':'Temperature',
                 'class': 'temperature',
		         'state_class':'measurement',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'sensor_type': 'sensor',
                 'function': get_temp},
          'wifi_strength':
                {'class': 'signal_strength',
                 'state_class':'measurement',
                 'name':'Wifi Strength',
                 'unit': 'dBm',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_strength},
          }

