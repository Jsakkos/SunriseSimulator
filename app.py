##Sunrise simulator##
import os
import sys
#import tty
#import pigpio
import time
import logging
import queue
import threading
import json
from datetime import datetime
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, jsonify, views
## Set GPIO pins to use
RED_PIN   = 17
GREEN_PIN = 22
BLUE_PIN  = 24
PINS = [RED_PIN, GREEN_PIN, BLUE_PIN]

#Off for testing
#pi = pigpio.pi()

logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',filename='myapp.log', filemode='w', level=logging.DEBUG)
###Time modes
class auto_settings:
    def __init__(self,hour,minute,startRGB,finishRGB,duration):
        self.hour = hour
        self.minute = minute
        self.startRGB = startRGB
        self.finishRGB = finishRGB
        self.duration = duration
#Default settings        
Wakeup_default = auto_settings(7,0,[0,0,0],[255,109,0],500000)
Wakeup2_default = auto_settings(7,15,[255,109,0],[255,255,255],500000)
Bedtime_default = auto_settings(23,0,[255,100,0],[0,0,0],1000000)
#Programmable settings
Wakeup = auto_settings(7,0,[0,0,0],[255,109,0],500000)
Wakeup2 = auto_settings(7,15,[255,109,0],[255,255,255],500000)
Bedtime = auto_settings(23,0,[255,100,0],[0,0,0],1000000)


##Color conversions
def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return list(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb
##

#Initial values
mode = 'auto'
stop = False                
RGB = [0,0,0]                   
##

# create our little application
app = Flask(__name__)

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')
#sends the current RGB values to flask    
@app.route('/get/current_state')
def get_state():
    for i in range(3):  
#        print(PINS[i],RGB[i])
        logging.info('Get state %s',RGB)
    return jsonify({'state': "%s" % rgb_to_hex(tuple(RGB))})
#Turn on lights
def setLights():
    global RGB
    for i in range(3):  
        # turned off for testing
#        pi.set_PWM_dutycycle(PINS[i], RGB[i])
        print(PINS[i],RGB[i])
    logging.info('LED state %s',RGB)
      
#    change from initial to final LED state
def fade(final_LED_state,duration):
    global RGB
    initial_LED_state = list(RGB)
    logging.info('Fade from %s to %s over %s steps',initial_LED_state, final_LED_state, duration)
    if initial_LED_state != final_LED_state:
        for steps in range (duration+1):
            for i in range(3):
                RGB[i] =(initial_LED_state[i] + int((final_LED_state[i] - initial_LED_state[i]) * steps / duration))
            time.sleep(.1)
            setLights()
            
##additional flask stuff            
@app.route('/mode/set/<hex_val>')
def set_mode(inputRGB):
    global RGB
    RGB = inputRGB
    setLights()
    return jsonify({'success' : True}) 
    
@app.route('/set/<hex_val>', methods=['GET', 'POST'])
def send_command(hex_val):
    global RGB
    RGB = hex_to_rgb(hex_val)
    setLights()
    return jsonify({'success' : True})
       
@app.route('/mode/off')
def off_mode():
    global RGB, stop
    RGB = [0,0,0]
    setLights()
    stop = True
    logging.info('Turn off system')
    sys.exit("System off")
    return jsonify({'success' : True})
    
@app.route('/mode/auto')
def auto_mode():
    global RGB, mode, stop
    mode = 'auto'
    logging.info('%s mode enabled', mode)
    stop = False
    RGB = [0,0,0]
    setLights()
    return jsonify({'success' : True})   
    
@app.route('/mode/lamp/<hex_val>', methods=['GET', 'POST'])
def lamp_mode(hex_val):
    global RGB, mode, stop,setRGB
    mode = 'lamp'
    logging.info('%s mode enabled', mode)
    stop = False
#    while mode == 'lamp' and stop == False:
    setRGB = list(hex_to_rgb(hex_val))
    fade(setRGB,10)
    RGB = list(hex_to_rgb(hex_val))
#        setLights()
#    RGB = hex_to_rgb(hex_val)
    return jsonify({'success' : True}) 
@app.route('/mode/mood/<hex_val>', methods=['GET', 'POST'])
def mood_mode(hex_val):
    global RGB, mode, stop, setRGB
    mode = 'mood'
    logging.info('%s mode enabled', mode)
    stop = False
    while mode == 'mood' and stop == False:
        setRGB = list(hex_to_rgb(hex_val))
        fade(setRGB,10)
        fade([0,0,0],10)
    return jsonify({'success' : True})     
    
if __name__ == '__main__':
    app.run(host='0.0.0.0')   
####end flask

### Auto mode loop            
#while stop ==False:
#    #Get the current time
#    now = datetime.now().time()
#    #morning fade in
#    if (now.hour == Wakeup.hour and now.minute == Wakeup.minute and mode == 'auto'):
#        setLights(Wakeup.startRGB)
#        fade(Wakeup.finishRGB,Wakeup.duration)        
#    #alert fade out
#    elif (now.hour == Wakeup2.hour and now.minute == Wakeup2.minute and mode == 'auto'):
#        setLights(Wakeup2.startRGB)
#        fade(Wakeup2.finishRGB,Wakeup2.duration)
#    elif (now.hour == Bedtime.hour and now.minute == Bedtime.minute and mode == 'auto'):
#        setLights(Bedtime.startRGB)
#        fade(Bedtime.finishRGB,Bedtime.duration)
#    time.sleep(30)
#       
#pi.stop()
