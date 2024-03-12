import os
import signal
import sys
import threading
import time
from threading import Event
import traceback

from flask import Flask, jsonify
from sun2000_modbus import inverter
from sun2000_modbus import registers
from waitress import serve

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

app = Flask(__name__)

# Global dictionary to store status information
inverter_data = dict()

def read_inverter_values():
    global inverter_data
    inverter_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    sun2000 = dict()
    sun2000['internal_temperature'] = inverter.read_raw_value(registers.InverterEquipmentRegister.InternalTemperature) / 10
    sun2000['model'] = inverter.read_raw_value(registers.InverterEquipmentRegister.Model)
    sun2000['number_of_mppt'] = inverter.read_raw_value(registers.InverterEquipmentRegister.NumberOfMPPTrackers)
    sun2000['number_of_strings'] = inverter.read_raw_value(registers.InverterEquipmentRegister.NumberOfPVStrings)
    sun2000['sn'] = inverter.read_raw_value(registers.InverterEquipmentRegister.SN)
    sun2000['system_time'] = inverter.read_raw_value(registers.InverterEquipmentRegister.SystemTime)
    sun2000['total_input_power'] = inverter.read_raw_value(registers.InverterEquipmentRegister.InputPower)

    # Todo: Interate PV Strings and MPPT Trackers
    # PV1
    pv1_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Voltage)
    pv1_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Current)
    pv1 = dict()
    pv1['voltage'] = pv1_voltage / 10
    pv1['current'] = pv1_current / 100

    # PV2
    pv2_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Voltage)
    pv2_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Current)
    pv2 = dict()
    pv2['voltage'] = pv2_voltage / 10
    pv2['current'] = pv2_current / 100

    pv_data = dict()
    pv_data['0'] = pv1
    pv_data['1'] = pv2
    sun2000['pv'] = pv_data

    inverter_dict = dict()
    inverter_dict['0'] = sun2000
    inverter_data['inverters'] = inverter_dict

    # Meter
    has_meter = inverter.read_raw_value(registers.MeterEquipmentRegister.MeterStatus)
    if has_meter:
        meter = dict()
        meter['type'] = inverter.read_raw_value(registers.MeterEquipmentRegister.MeterType)
        meter['active_power'] = inverter.read_raw_value(registers.MeterEquipmentRegister.ActivePower)
        meter['reactive_power'] = inverter.read_raw_value(registers.MeterEquipmentRegister.ReactivePower)
        meter['power_factor'] = inverter.read_raw_value(registers.MeterEquipmentRegister.PowerFactor) / 1000
        meter['grid_frequency'] = inverter.read_raw_value(registers.MeterEquipmentRegister.GridFrequency) / 100

        phase_a = dict()
        phase_a['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.APhaseVoltage) / 10
        phase_a['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.APhaseCurrent) / 100
        meter['phase_a'] = phase_a

        if meter['type'] == 1:
            phase_b = dict()
            phase_b['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.BPhaseVoltage) / 10
            phase_b['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.BPhaseCurrent) / 100
            meter['phase_b'] = phase_b

            phase_c = dict()
            phase_c['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.CPhaseVoltage) / 10
            phase_c['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.CPhaseCurrent) / 100
            meter['phase_c'] = phase_c

        inverter_data['meter'] = meter

def push_to_influxdb():
    global inverter_data
    write_api.write(bucket, org, [
        {
            "measurement": "inverter",
            "timestamp": inverter_data['inverters']['0']['system_time'],
            "tags": {
                "serial_number": inverter_data['inverters']['0']['sn'],
                "unit": inverter_unit
            },
            "fields": {
                "pv0_voltage": inverter_data['inverters']['0']['pv']['0']['voltage'],
                "pv0_current": inverter_data['inverters']['0']['pv']['0']['current'],
                "pv1_voltage": inverter_data['inverters']['0']['pv']['1']['voltage'],
                "pv1_current": inverter_data['inverters']['0']['pv']['1']['current'],
                "input_power": inverter_data['inverters']['0']['total_input_power'],
                "internal_temperature": inverter_data['inverters']['0']['internal_temperature']
            }
        }
    ])

    write_api.write(bucket, org, [
        {
            "measurement": "meter",
            "timestamp": inverter_data['inverters']['0']['system_time'],
            "tags": {
                "serial_number": inverter_data['inverters']['0']['sn'],
                "unit": inverter_unit
            },
            "fields": {
                "active_power": inverter_data['meter']['active_power'],
                "reactive_power": inverter_data['meter']['reactive_power'],
                "power_factor": inverter_data['meter']['power_factor'],
                "grid_frequency": inverter_data['meter']['grid_frequency'],
                "phase_a_voltage": inverter_data['meter']['phase_a']['voltage'],
                "phase_a_current": inverter_data['meter']['phase_a']['current']
            }
        }
    ])

def update_data_thread(thread_event: Event) -> None:
    while not thread_event.is_set():
        try:
            if inverter.isConnected():
                print("Updating inverter data", time.strftime("%Y-%m-%d %H:%M:%S"))
                read_inverter_values()
                push_to_influxdb()
        except Exception as e:
                print("Exception in thread:", e)
                traceback.print_exc()
        time.sleep(5)
    print("Exiting update thread")

# Thread to run the Flask app
def run_flask_thread(thread_event: Event) -> None:
    serve(app, host="0.0.0.0", port=3000)

# Route to display the contents of the global dictionary
@app.route('/status')
def status():
    return jsonify(inverter_data)

def signal_handler(sig, frame):
    if sig == signal.SIGINT:
        event.set()
        inverter.disconnect()
    sys.exit(0)


if __name__ == "__main__":

    signal.signal(signal.SIGINT, signal_handler)

    if os.environ.get('SUN2000_HOST') is None:
        print("Please set the HOST environment variable")
        sys.exit(1)

    inverter_host = os.environ.get('SUN2000_HOST', '')
    inverter_port = os.environ.get('SUN2000_PORT', 6607)
    inverter_unit = os.environ.get('SUN2000_UNIT', 0)

    # ToDo: Make InfluDB optional based on environment variable
    bucket = os.environ.get('INFLUX_BUCKET', 'sun2000')
    org = os.environ.get('INFLUX_ORG', 'hangas')
    token = os.environ.get('INFLUX_TOKEN')
    url = os.environ.get('INFLUX_URL', 'http://localhost:8086')

    # InfluxDB client
    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    inverter = inverter.Sun2000(host=inverter_host, port=inverter_port, unit=inverter_unit)
    inverter.connect()


# Create and start the update status thread
    event = Event()
    update_thread = threading.Thread(target=update_data_thread, args=(event,))
    update_thread.start()

    # Create and start the Flask thread
    flask_thread = threading.Thread(target=run_flask_thread, args=(event,))
    flask_thread.start()
