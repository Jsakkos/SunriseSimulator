##Sunrise simulator##
##Adapted from https://github.com/rasathus/circadianLighting##

import os
import sys
#import tty
import pigpio
import time
import logging
from logging.handlers import RotatingFileHandler
from queue import Queue
import threading
import json
from datetime import datetime
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, jsonify, views
import random

#Start PIGPIO to control GPIO pins
pi = pigpio.pi()
if not pi.connected:
   exit()

#Setup Logger
log_formatter = logging.Formatter('%(asctime)s %(threadName)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
logFile = 'log.txt'
my_handler = RotatingFileHandler(logFile, mode='a', maxBytes=5*1024*1024,backupCount=2, encoding=None, delay=1)
my_handler.setFormatter(log_formatter)
my_handler.setLevel(logging.DEBUG)
app_log = logging.getLogger('root')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(my_handler)
######

###Time modes
class auto_settings:
    def __init__(self,hour,minute,startRGB,finishRGB,duration):
        self.hour = hour
        self.minute = minute
        self.startRGB = startRGB
        self.finishRGB = finishRGB
        self.duration = duration

#Auto settings
Wakeup = auto_settings(7,0,[0,0,0],[255,109,0],500)
Wakeup2 = auto_settings(7,15,[255,109,0],[255,255,255],500)
Bedtime = auto_settings(22,30,[255,100,0],[0,0,0],1000)

##Color conversions
def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return list(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

#LED controller class    
class LED_Communicator:
    
    def __init__(self):
        self.auto_resume_job = None
        self.queue = Queue()
        self.mode = 'auto'
        self.state = [0,0,0]
        self.set = [0,0,0]
        self.set_mood = [0,0,0]
        self.run = True
        app_log.debug("Communicator starting main_loop.")
        self.thread = threading.Thread(name='Communicator',target=self.main_loop)
        self.thread.start()
        self.mode_thread = threading.Thread(name='Mode Loop',target=self.mode_loop)
        self.mode_thread.start()
        self.event = threading.Event()
        self.lock = threading.Lock()
        app_log.debug("Communicator init complete.")
        #set GPIO pins being used to control LEDs
        self.pins = [17,22,24]
        app_log.info("Running resume auto, in case were in an auto event.")
        self.resume_auto()
        app_log.debug("Communicator init complete.")
    def get_state(self):
        app_log.info('Desired settings: {} set to {}'.format(self.pins,self.set))
        # turned off for testing
        for i in range(3):
            self.state[i] = pi.get_PWM_dutycycle(self.pins[i])
        app_log.info('Pins {} set to {}'.format(self.pins,self.state))
        
    def write(self,set_state):

        for i in range(3):  
        # turned off for testing
            pi.set_PWM_dutycycle(self.pins[i], self.state[i])
#        print(self.pins,set_state)
        self.get_state()
        self.state = set_state
            
        app_log.debug('LED state {}'.format(self.state))

    def main_loop(self):
        try:
            app_log.debug("main_loop - processing queue ...")
            while self.run :
                #get desired LED color from the queue
                lighting_event = self.queue.get(block=True)
                # set our LED state
                self.write(lighting_event)

        except KeyboardInterrupt:
            self.run = False
            app_log.warning("Caught keyboard interrupt in main_loop.  Shutting down ...")
            
    def transition(self, set_state,transition_duration=100, transition_mode='fade'):
        self.set = set_state
        #clear queue
        with self.queue.mutex:
            self.queue.queue.clear()
        app_log.info("Current state is : %s , destination state is : %s , transitioning via %s in : %d ticks" % (self.state, self.set, transition_mode, transition_duration))
        if transition_mode is 'fade':        
            # Using a modified version of http://stackoverflow.com/questions/6455372/smooth-transition-between-two-states-dynamically-generated for smooth transitions between states.
            for transition_count in range(transition_duration - 1):
                RGB = []
                self.get_state()
                for component in range(3):
                    RGB.append(int((self.state[component] + (self.set[component] - self.state[component]) * transition_count / transition_duration)))
                self.queue.put(RGB)
            self.queue.put(self.set)

    def clear_mode(self):
        app_log.debug("Removing mode")
        with self.lock:
            self.mode = []

    def resume_auto(self):
          self.clear_mode()
         # returns system state to autonomous, to be triggered via the scheduler, or via a request hook from the web ui.
          self.mode = 'auto'
          self.transition([0,0,0])
          app_log.debug("Resume auto called, system state is now : {}".format(self.mode))
          
    def mode_loop(self):

        while self.run:
            app_log.debug('Starting mode loop')
        ### Auto mode loop
            if self.mode =='auto' and not self.event.isSet():
                app_log.info('{} mode running'.format(self.mode))
                #Get the current time
                now = datetime.now().time()
#                morning fade in
                if (now.hour == Wakeup.hour and now.minute == Wakeup.minute and self.mode == 'auto'):
                    
                    self.transition(Wakeup.finishRGB,Wakeup.duration)        
                #alert fade out
                elif (now.hour == Wakeup2.hour and now.minute == Wakeup2.minute and self.mode == 'auto'):
                    self.transition(Wakeup2.finishRGB,Wakeup2.duration)
                    time.sleep(30)
                    self.transition([0,0,0])
                elif (now.hour == Bedtime.hour and now.minute == Bedtime.minute and self.mode == 'auto'):
                    self.transition(Bedtime.startRGB)
                    time.sleep(600)
                    self.transition(Bedtime.finishRGB,Bedtime.duration)
                time.sleep(30)
            elif self.mode =='mood' and not self.event.isSet():
                app_log.info('{} mode running'.format(self.mode))
                app_log.debug('{} mode enabled'.format(self.mode))
                self.transition(self.set_mood,500)
                time.sleep(3)
                self.transition([0,0,0],500)
            elif self.mode =='cycle' and not self.event.isSet():
                app_log.info('{} mode running'.format(self.mode))
                color=[]
                for i in range(3):
                    color.append(random.randint(0,255))
                self.transition(color,500)
                time.sleep(1)
            time.sleep(1)

    def shutdown(self):
        
        # send final state to avoid blocking on queue.
        self.queue.put([0,0,0])
        self.run = False
        self.thread.join()
        self.mode_thread.join()
        self.write([0,0,0])
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
#sends the current RGB values to flask    
@app.route('/get/current_state')
def get_state():
    app_log.info('Get state {}'.format(LED.state))
    return jsonify({'state': "%s" % rgb_to_hex(tuple(LED.state))})

            
@app.route('/get/current_mode')
def get_mode():
    app_log.info('Mode is {}'.format(LED.mode))
    return jsonify({'mode': "%s" % LED.mode}) 
      
@app.route('/mode/off')
def off_mode():
    app_log.debug('Initiate shutdown')
    LED.shutdown()
    return jsonify({'success' : True})
    
@app.route('/mode/auto')
def auto_mode():
    app_log.info('Auto mode called')
    LED.mode = 'auto'
    app_log.info('Auto mode set')
    get_state()
    app_log.info('Calling Resume Auto')
    LED.resume_auto()
    app_log.info('{} mode enabled'.format(LED.mode))
    return jsonify({'success' : True})   
    
@app.route('/mode/lamp/<hex_val>', methods=['GET', 'POST'])
def lamp_mode(hex_val):
    LED.mode = 'lamp'
    app_log.info('{} mode enabled'.format(LED.mode))
    get_mode()
    app_log.info('Desired color is {}'.format(hex_to_rgb(hex_val)))
    LED.transition(hex_to_rgb(hex_val))
    return jsonify({'success' : True})
        
@app.route('/mode/mood/<hex_val>', methods=['GET', 'POST'])
def mood_mode(hex_val):
    LED.mode = 'mood'
    app_log.info('{} mode enabled'.format(LED.mode))
    get_mode()
    app_log.info('Desired color is {}'.format(hex_to_rgb(hex_val)))
    LED.set = hex_to_rgb(hex_val)
    LED.set_mood = hex_to_rgb(hex_val)
    return jsonify({'success' : True})     
@app.route('/mode/cycle')
def cycle_mode():
    LED.mode = 'cycle'
    app_log.info('{} mode enabled'.format(LED.mode))
    get_mode()
    return jsonify({'success' : True})     
            
if __name__ == '__main__':

    #initialize LED class
    LED = LED_Communicator()
    app.run(host='0.0.0.0')
    app_log.info("Calling shutdown on led chain")
    LED.shutdown()
    
    app_log.info("Shutting down logger and exiting ...")
    app_log.shutdown()
    exit(0)
####end flask


