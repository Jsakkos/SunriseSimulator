# Sunrise simulator##
# Adapted from https://github.com/rasathus/circadianLighting##

import os
import random
import sys
import threading
import time
from datetime import datetime, date
from queue import Queue

import pigpio
from flask import Flask, render_template, jsonify

# Start PIGPIO to control GPIO pins
pi = pigpio.pi()
if not pi.connected:
    exit()

# Time modes
class auto_settings:
    def __init__(self, hour, minute, color, duration):
        self.hour = hour
        self.minute = minute
        self.color = color
        self.duration = duration

# Auto settings
Wakeup = auto_settings(7, 30, [255, 109, 0], 1000)
Wakeup2 = auto_settings(7, 45, [255, 255, 255], 1000)

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
        # set GPIO pins being used to control LEDs
        self.pins = [17, 22, 24]
        self.range = 1000
        pi.set_PWM_range(self.pins[0], self.range)
        pi.set_PWM_range(self.pins[1], self.range)
        pi.set_PWM_range(self.pins[2], self.range)
        self.thread = threading.Thread(name='Communicator', target=self.main_loop)
        self.thread.start()
        self.mode_thread = threading.Thread(name='Mode Loop', target=self.mode_loop)
        self.mode_thread.start()
        self.write(self.set)

    def get_state(self):
        for i in range(3):
            self.state[i] = pi.get_PWM_dutycycle(self.pins[i]) * 255 / self.range

    def write(self, set_state):
        for i in range(3):
            pi.set_PWM_dutycycle(self.pins[i], set_state[i])
        self.get_state()

    def main_loop(self):
        try:
            while self.run:
                # get desired LED color from the queue
                lighting_event = self.queue.get(block=True)
                # set our LED state
                self.write(lighting_event)

        except KeyboardInterrupt:
            self.run = False

    def transition(self, set_state, transition_duration=500, delay=.001):
        self.set = set_state
        # clear queue
        self.clear_queue()
        for transition_count in range(transition_duration - 1):
            RGB = []
            self.get_state()
            for component in range(3):
                RGB.append(int((self.state[component] * self.range / 255 + (
                    self.set[component] * self.range / 255 - self.state[
                        component] * self.range / 255) * transition_count / transition_duration)))
            self.queue.put(RGB)
            time.sleep(delay)

    def clear_queue(self):
        with self.queue.mutex:
            self.queue.queue.clear()

    def change_mode(self, mode):
        self.mode = mode
        self.button_event.set()
        self.clear_queue()
        if mode is 'auto':
            self.transition([0, 0, 0])

    def mode_loop(self):

        try:
            while self.run:
                # Auto mode loop
                # todo add scheduling from google calendar
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
                    if now.hour is Wakeup.hour and now.minute is Wakeup.minute and weekend is False and self.mode is 'auto':
                        self.transition(Wakeup.color, Wakeup.duration, 2)
                        self.button_event.wait(timeout=60)
                        self.transition(Wakeup2.color, Wakeup2.duration, .5)
                        self.button_event.wait(timeout=600)
                        self.transition([0, 0, 0])
                    else:
                        self.button_event.wait(timeout=30)
                elif self.mode is 'lamp':
                    if self.set != self.state:
                        self.transition(self.set, 200)
                    else:
                        self.button_event.wait(1)
                elif self.mode is 'mood':
                    self.transition(self.set_mood, 1000, .1)
                    self.button_event.wait(timeout=3)
                    self.transition([0, 0, 0], 200, .1)
                elif self.mode == 'cycle':
                    color = []
                    for i in range(3):
                        color.append(random.randint(0, 255))
                    self.transition(color, 1000, .1)
                    self.button_event.wait(timeout=1)
                elif self.mode == 'bedtime':
                    self.transition([255, 0, 0], 500)
                    self.button_event.wait(timeout=300)
                    self.transition([0, 0, 0], 1000, 1)
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
    return render_template('index.html')

# sends the current RGB values to flask
@app.route('/get/current_state')
def get_state():
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

# set the secret key.
app.secret_key = os.urandom(24)

if __name__ == '__main__':
    LED = LED_Communicator()
    app.run(host='0.0.0.0')
    LED.shutdown()
    exit(0)