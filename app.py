# Sunrise simulator##
# Adapted from https://github.com/rasathus/circadianLighting##

import os
import random
import sys
import threading
from configparser import ConfigParser
from datetime import datetime, date
from queue import Queue

import pigpio
from flask import Flask, render_template, jsonify, request, url_for, redirect

# Start PIGPIO to control GPIO pins
pi = pigpio.pi()
if not pi.connected:
    exit()

    # get cwd for config file
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(ROOT_PATH, "config.ini")

# Color conversions
def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return list(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

# LED controller class
class LED_Communicator:
    def __init__(self):
        self.queue = Queue()
        self.mode = 'auto'
        self.state = [0, 0, 0]
        self.set = [0, 0, 0]
        self.set_mood = [0, 0, 0]
        self.run = True
        self.button_event = threading.Event()
        self.button_event.clear()
        self.delay = 0.01
        # read configuration file
        config = ConfigParser()
        config.read(filepath)
        try:
            self.WakeupHour = int(config.get('Wakeup Settings', 'Hour'))
            self.WakeupMinute = int(config.get('Wakeup Settings', 'Minute'))
            self.WakeupDuration = int(config.get('Wakeup Settings', 'Duration'))
        except:
            self.WakeupHour = 7
            self.WakeupMinute = 30
            self.WakeupDuration = 3600
            config.add_section('Wakeup Settings')
            config.set('Wakeup Settings', 'Hour', str(self.WakeupHour))
            config.set('Wakeup Settings', 'Minute', str(self.WakeupMinute))
            config.set('Wakeup Settings', 'Duration', str(self.WakeupDuration))
            with open(filepath, 'w') as f:
                config.write(f)

        # set GPIO pins being used to control LEDs
        self.pins = [17, 22, 24]
        self.thread = threading.Thread(name='Communicator', target=self.main_loop)
        self.thread.start()
        self.mode_thread = threading.Thread(name='Mode Loop', target=self.mode_loop)
        self.mode_thread.start()
        self.write(self.set)

    def get_state(self):
        for i in range(3):
            self.state[i] = pi.get_PWM_dutycycle(self.pins[i])

    def write(self, set_state):
        for i in range(3):
            pi.set_PWM_dutycycle(self.pins[i], set_state[i])

    def main_loop(self):
        try:
            while self.run:
                # get desired LED color from the queue
                lighting_event = self.queue.get(block=True)
                # set our LED state
                self.write(lighting_event)
                self.button_event.wait(timeout=self.delay)

        except KeyboardInterrupt:
            self.run = False

    def transition(self, set_state, transition_duration):
        self.set = set_state
        # clear queue
        self.clear_queue()
        offset = []
        for component in range(3):
            offset.append(abs(self.set[component] - self.state[component]))
        steps = max(offset)
        self.delay = transition_duration / steps
        for i in range(steps):
            RGB = []
            for component in range(3):
                difference = self.set[component] - self.state[component]
                if difference > 0:
                    RGB.append(self.state[component] + 1)
                elif difference < 0:
                    RGB.append(self.state[component] - 1)
                else:
                    RGB.append(self.state[component])
            self.queue.put(RGB)
            self.state = RGB
            # time.sleep(delay)
            # self.button_event.wait(timeout=self.delay)

    def clear_queue(self):
        with self.queue.mutex:
            self.queue.queue.clear()

    def change_mode(self, mode):
        self.mode = mode
        self.button_event.set()
        self.clear_queue()
        self.get_state()
        if mode is 'auto':
            self.transition([0, 0, 0], 1)

    def mode_loop(self):

        try:
            while self.run:
                # Auto mode loop
                self.button_event.clear()
                if self.mode is 'auto':
                    # Get the current time
                    now = datetime.now().time()
                    today = date.weekday(date.today())
                    weekend = False
                    if today is 5 or today is 6:
                        weekend = True
                    else:
                        weekend = False
                    # morning fade in
                    if now.hour is self.WakeupHour and now.minute is self.WakeupMinute and weekend is False and self.mode is 'auto':
                        self.transition([255, 109, 0], int(self.WakeupDuration / 3))
                        self.transition([255, 255, 255], int(self.WakeupDuration * 2 / 3))
                        self.transition([0, 0, 0], 60)
                    else:
                        self.button_event.wait(timeout=30)
                elif self.mode is 'lamp':
                    if self.set != self.state:
                        self.transition(self.set, 0)
                    else:
                        self.button_event.wait(.1)
                elif self.mode is 'mood':
                    self.transition(self.set_mood, 30)
                    self.button_event.wait(timeout=3)
                    self.transition([0, 0, 0], 30)
                elif self.mode == 'cycle':
                    color = []
                    for i in range(3):
                        color.append(random.randint(0, 255))
                    self.transition(color, 10)
                    self.button_event.wait(timeout=2)
                elif self.mode == 'bedtime':
                    self.transition([255, 0, 0], 5)
                    self.button_event.wait(timeout=60)
                    self.transition([0, 0, 0], 600)
                    self.change_mode('auto')
                self.button_event.wait(timeout=.2)


        except KeyboardInterrupt:
            self.run = False

    def shutdown(self):
        # send final state to avoid blocking on queue.
        self.queue.put([0, 0, 0])
        self.run = False
        self.mode_thread.join()
        self.thread.join()
        self.write([0, 0, 0])
        pi.stop()
        # Shutdown
        os.system('shutdown now -h')
        sys.exit("System off")


# create our little application
app = Flask(__name__)


@app.route('/')
@app.route('/index')
def index():
    if LED.WakeupMinute == 0 or LED.WakeupMinute == 5:
        Wakeup_time = (str(LED.WakeupHour) + ':' + '0' + str(LED.WakeupMinute) + ' am')
    else:
        Wakeup_time = (str(LED.WakeupHour) + ':' + str(LED.WakeupMinute) + ' am')
    return render_template('index.html', Wakeup_time=Wakeup_time)

# sends the current RGB values to flask
@app.route('/get/current_state')
def get_state():
    LED.get_state()
    return jsonify({'state': "%s" % rgb_to_hex(tuple(LED.state))})

@app.route('/get/current_mode')
def get_mode():
    return jsonify({'mode': "%s" % LED.mode})

@app.route('/mode/off')
def off_mode():
    LED.shutdown()
    return jsonify({'success': True})

@app.route('/mode/auto')
def auto_mode():
    if LED.mode is not 'auto':
        LED.change_mode('auto')
    return jsonify({'success': True})


@app.route('/mode/bedtime')
def bedtime_mode():
    if LED.mode is not 'bedtime':
        LED.change_mode('bedtime')
    return jsonify({'success': True})

@app.route('/mode/lamp/<hex_val>', methods=['GET', 'POST'])
def lamp_mode(hex_val):
    if LED.mode is not 'lamp':
        LED.change_mode('lamp')
    LED.set = hex_to_rgb(hex_val)
    return jsonify({'success': True})

@app.route('/mode/mood/<hex_val>', methods=['GET', 'POST'])
def mood_mode(hex_val):
    if LED.mode is not 'mood':
        LED.change_mode('mood')
    LED.set_mood = hex_to_rgb(hex_val)
    return jsonify({'success': True})

@app.route('/mode/cycle')
def cycle_mode():
    if LED.mode is not 'cycle':
        LED.change_mode('cycle')
    return jsonify({'success': True})


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        LED.WakeupHour = int(request.form.get('hour'))
        LED.WakeupMinute = int(request.form.get('minute'))
        LED.WakeupDuration = int(request.form.get('duration')) * 60
        config = ConfigParser()
        config.read(filepath)
        config.set('Wakeup Settings', 'Hour', str(LED.WakeupHour))
        config.set('Wakeup Settings', 'Minute', str(LED.WakeupMinute))
        config.set('Wakeup Settings', 'Duration', str(LED.WakeupDuration))
        with open(filepath, 'w') as f:
            config.write(f)

        return redirect(url_for('index'))
    else:
        if LED.WakeupMinute == 0 or LED.WakeupMinute == 5:
            Wakeup_time = (str(LED.WakeupHour) + ':' + '0' + str(LED.WakeupMinute) + ' am')
        else:
            Wakeup_time = (str(LED.WakeupHour) + ':' + str(LED.WakeupMinute) + ' am')
        Wakeup_duration = (str(round(LED.WakeupDuration / 60)) + ' mins')
    return render_template('settings.html', Wakeup_time=Wakeup_time, Wakeup_duration=Wakeup_duration)
# set the secret key.
app.secret_key = os.urandom(24)

if __name__ == '__main__':
    LED = LED_Communicator()
    app.run(host='0.0.0.0')
    LED.shutdown()
    exit(0)