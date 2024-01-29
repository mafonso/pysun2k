import os
import signal
import sys
import threading
import time
from threading import Event

from flask import Flask, jsonify
from sun2000_modbus import inverter
from sun2000_modbus import registers
from waitress import serve

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

            sun2000 = dict()
            sun2000['sn'] = sn
            sun2000['model'] = model
            sun2000['number_of_strings'] = number_of_strings
            sun2000['number_of_mppt'] = number_of_mppt

            # Voltage
            pv1_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Voltage)
            pv2_voltage = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Voltage)
            voltage = dict()
            voltage['0'] = pv1_voltage
            voltage['1'] = pv2_voltage

            # Current
            pv1_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV1Current)
            pv2_current = inverter.read_raw_value(registers.InverterEquipmentRegister.PV2Current)
            current = dict()
            current['0'] = pv1_current
            current['1'] = pv2_current

            pv_data = dict()
            pv_data['voltage'] = voltage
            pv_data['current'] = current

            input_power = inverter.read_raw_value(registers.InverterEquipmentRegister.InputPower)
            internal_temperature = inverter.read_raw_value(registers.InverterEquipmentRegister.InternalTemperature)

            inverter_data['inverter'] = sun2000
            inverter_data['inverter']['pv'] = pv_data
            inverter_data['inverter']['total_input_power'] = input_power
            inverter_data['inverter']['internal_temperature'] = internal_temperature

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


def signal_handler():
    inverter.disconnect()
    Event.set()
    sys.exit(0)


if __name__ == "__main__":

    signal.signal(signal_handler, signal.SIGINT)

    if os.environ.get('HOST') is None:
        print("Please set the HOST environment variable")
        sys.exit(1)

    inverter_host = os.environ.get('HOST', '')
    inverter_port = os.environ.get('PORT', 6607)
    inverter_unit = os.environ.get('UNIT', 0)

    inverter = inverter.Sun2000(host=inverter_host, port=inverter_port, unit=inverter_unit)

    # Create and start the update status thread
    event = Event()
    update_thread = threading.Thread(target=update_data_thread, args=(event,))
    update_thread.start()

    # Create and start the Flask thread
    flask_thread = threading.Thread(target=run_flask_thread)
    flask_thread.start()
