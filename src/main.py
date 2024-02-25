import os
import signal
import sys
import threading
import time
import logging
from threading import Event

from flask import Flask, jsonify
from sun2000_modbus import inverter
from sun2000_modbus import registers
from waitress import serve

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client import Point






app = Flask(__name__)
# Global dictionary to store status information
inverter_data = dict()
def update_data_thread(event: Event) -> None:
    while not event.is_set():
        # Update the global dictionary with the current time
        inverter_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        inverter.connect()
        if inverter.isConnected():
            sn = inverter.read_raw_value(registers.InverterEquipmentRegister.SN)
            model = inverter.read_raw_value(registers.InverterEquipmentRegister.Model)
            number_of_strings = inverter.read_raw_value(registers.InverterEquipmentRegister.NumberOfPVStrings)
            number_of_mppt = inverter.read_raw_value(registers.InverterEquipmentRegister.NumberOfMPPTrackers)
            systemtime = inverter.read_raw_value(registers.InverterEquipmentRegister.SystemTime)

            sun2000 = dict()

            sun2000['sn'] = sn
            sun2000['model'] = model
            sun2000['number_of_strings'] = number_of_strings
            sun2000['number_of_mppt'] = number_of_mppt
            sun2000['system_time'] = systemtime


            # PV0
            pv1_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Voltage)
            pv1_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Current)
            pv0 = dict()
            pv0['voltage'] = pv1_voltage / 10
            pv0['current'] = pv1_current / 100

            # Current
            pv2_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Voltage)
            pv2_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Current)
            pv1 = dict()
            pv1['voltage'] = pv2_voltage / 10
            pv1['current'] = pv2_current / 100

            pv_data = dict()
            pv_data['0'] = pv0
            pv_data['1'] = pv1

            input_power = inverter.read_raw_value(registers.InverterEquipmentRegister.InputPower)
            internal_temperature = inverter.read_raw_value(registers.InverterEquipmentRegister.InternalTemperature) / 10

            sun2000['pv'] = pv_data
            sun2000['total_input_power'] = input_power
            sun2000['internal_temperature'] = internal_temperature

            inverter_dict = dict()
            inverter_dict['0'] = sun2000


            inverter_data['inverters'] = inverter_dict

            # Meter
            hasMeter = inverter.read_raw_value(registers.MeterEquipmentRegister.MeterStatus)
            if hasMeter:
                meter = dict()
                meter['type'] = inverter.read_raw_value(registers.MeterEquipmentRegister.MeterType)
                meter['active_power'] = inverter.read_raw_value(registers.MeterEquipmentRegister.ActivePower)
                meter['reactive_power'] = inverter.read_raw_value(registers.MeterEquipmentRegister.ReactivePower)
                meter['power_factor'] = inverter.read_raw_value(registers.MeterEquipmentRegister.PowerFactor) / 1000
                meter['grid_frequency'] = inverter.read_raw_value(registers.MeterEquipmentRegister.GridFrequency) / 100

                phase_a = dict()
                phase_a['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.APhaseVoltage) / 10
                phase_a['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.APhaseCurrent) /100
                meter['phase_a'] = phase_a

                if meter['type'] == 1:
                    phase_b = dict()
                    phase_b['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.BPhaseVoltage) / 10
                    phase_b['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.BPhaseCurrent) /100
                    meter['phase_b'] = phase_b

                    phase_c = dict()
                    phase_c['voltage'] = inverter.read_raw_value(registers.MeterEquipmentRegister.CPhaseVoltage) / 10
                    phase_c['current'] = inverter.read_raw_value(registers.MeterEquipmentRegister.CPhaseCurrent) /100
                    meter['phase_c'] = phase_c

                inverter_data['meter'] = meter

                write_api.write(bucket, org, [
                    {
                        "measurement": "inverter",
                        "timestamp": systemtime,
                        "tags": {
                            "serial_number": sn,
                            "unit": inverter_unit
                        },
                        "fields": {
                            "pv0_voltage": pv0['voltage'],
                            "pv0_current": pv0['current'],
                            "pv1_voltage": pv1['voltage'],
                            "pv1_current": pv1['current'],
                            "input_power": input_power,
                            "internal_temperature": internal_temperature
                        }
                    }
                ])

                write_api.write(bucket, org, [
                    {
                        "measurement": "meter",
                        "tags": {
                            "serial_number": sn,
                            "unit": inverter_unit
                        },
                        "fields": {
                            "active_power": meter['active_power'],
                            "reactive_power": meter['reactive_power'],
                            "power_factor": meter['power_factor'],
                            "grid_frequency": meter['grid_frequency'],
                            "phase_a_voltage": phase_a['voltage'],
                            "phase_a_current": phase_a['current']
                        }
                    }
                ])

        else:
            inverter_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            inverter_data['status'] = "Not connected"
            inverter.connect()
        time.sleep(5)


# Thread to run the Flask app
def run_flask_thread():
    serve(app, host="0.0.0.0", port=3000)


# Route to display the contents of the global dictionary
@app.route('/status')
def status():
    return jsonify(inverter_data)


def signal_handler(signal, frame):
    sys.exit(0)



if __name__ == "__main__":

    signal.signal(signal.SIGINT, signal_handler)

    if os.environ.get('HOST') is None:
        print("Please set the HOST environment variable")
        sys.exit(1)

    inverter_host = os.environ.get('HOST', '')
    inverter_port = os.environ.get('PORT', 6607)
    inverter_unit = os.environ.get('UNIT', 0)

    bucket = os.environ.get('INFLUX_BUCKET', 'sun2000')
    org = os.environ.get('INFLUX_ORG', 'hangas')
    token = os.environ.get('INFLUX_TOKEN')
    url = os.environ.get('INFLUX_URL', 'http://localhost:8086')

    # InfluxDB client
    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)


    inverter = inverter.Sun2000(host=inverter_host, port=inverter_port, unit=inverter_unit)


    # Create and start the update status thread
    event = Event()
    update_thread = threading.Thread(target=update_data_thread, args=(event,))
    update_thread.start()

    # Create and start the Flask thread
    flask_thread = threading.Thread(target=run_flask_thread)
    flask_thread.start()
