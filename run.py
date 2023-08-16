"""
Copyright (C) 2023 Julian Metzler

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import datetime
import dateutil.parser
import hashlib
import json
import os
import random
import time
import traceback

from c3toc import C3TOCAPI
from pretalx_api import PretalxAPI, ongoing_or_future_filter, max_duration_filter

from pprint import pprint
from pyfis.oltmann import VistraI
from pyfis.oltmann.utils import get_text_width

from _config import *


DISPLAY_MODES = [
    #"arr_dep_eta",
    "pretalx"
]

TRACK_CODES = {
    "Digitalcourage": "DC",
    "Live Music": "LM",
    "Bits & Bäume": "BB",
    "DJ Set": "DJ",
    "CCC": "C",
    "Nerds der OberRheinischen Tiefebene und der xHain (N\\:O:R:T:x)": "NX",
    "Entertainment": "E",
    "Performance": "P",
    "Milliways": "MW"
}

ROOM_ABBREVIATIONS = {
    "Digitalcourage": "Dig.courage",
    "Bits & Bäume": "Bits+Bäume",
    "Hardware Hacking Village": "HW Hck Vlg",
    "Milliways Workshop Dome": "MW Dome"
}
    

def main():
    mode_index = 0
    mode = DISPLAY_MODES[mode_index]
    display_width = 96
    display_height = 64
    page_interval = 20 # Page switch interval in seconds (roughly)
    
    eta_lookback = 10 # How many minutes of past train positions to consider for ETA
    eta_max_jump = 30 # Maximum ETA jump in seconds
    trackmarker_delta_arrived = 20 # "station zone" size in track units
    display_trackmarker = 163 # Physical trackmarker position of the display
    
    toc = C3TOCAPI()
    pretalx = PretalxAPI("https://pretalx.c3voc.de/camp2023/schedule/export/schedule.json")
    display = VistraI(CONFIG_VISTRA_I_HOST, CONFIG_VISTRA_I_PORT)
    display.set_brightness(128)
    
    tracks = toc.get_tracks()
    track_length = sorted(tracks['waypoints'].values(), key=lambda e: e['trackmarker'])[-1]['trackmarker']
    #print("Track length: {}".format(track_length))
    
    while True:
        try:
            display.init_queue()
            print("Handling mode: " + mode)
            utcnow = datetime.datetime.utcnow()
            now = datetime.datetime.now()
            display.clear_panel()
            
            # Handle all background calculations and data operations
            
            # c3toc API #######################################################
            # Get trains from API and calculate ETAs
            # This is run more frequently than it is displayed to keep the ETA more accurate
            train_info = toc.get_train_info(display_trackmarker, eta_lookback, eta_max_jump, trackmarker_delta_arrived, track_length)
            
            for name, info in train_info.items():
                if info['eta'] is None:
                    pass #print("No ETA available for {name}".format(name=name))
                else:
                    delta = (info['eta'] - utcnow).total_seconds()
                    #print("{name} will arrive at trackmarker {trackmarker} in {seconds} seconds, at {time} UTC".format(name=name, trackmarker=display_trackmarker, seconds=delta, time=info['eta'].strftime("%H:%M:%S")))
                #pprint(info)
            ###################################################################
            
            
            # Handle displaying the required content
            if mode == "arr_dep_eta":
                if train_info:
                    items = sorted(train_info.items(), key=lambda i: i[1]['eta'] or datetime.datetime(2070, 1, 1, 0, 0, 0))
                    for i, (name, data) in enumerate(items):
                        if data['eta'] is not None:
                            eta_str = str(round(max((data['eta'] - utcnow).total_seconds(), 0) / 60))
                        else:
                            eta_str = "???"
                        y_base = i * 16
                        line = name[:2].upper()
                        display.send_text(text=line, font=12, x=0, y=y_base, width=24, height=16, effects=display.EFFECT_CENTERED | display.EFFECT_MIDDLE)
                        display.send_text(text=name, font=12, x=32, y=y_base, width=130, height=16, effects=display.EFFECT_MIDDLE)
                        display.send_text(text=eta_str, font=12, x=260, y=y_base, width=28, height=16, effects=display.EFFECT_RIGHT | display.EFFECT_MIDDLE)
                else:
                    display.send_text(text="No Departures", font=12, x=0, y=0, width=display_width, height=display_height, effects=display.EFFECT_CENTERED | display.EFFECT_MIDDLE)
            elif mode == "pretalx":
                # Display header
                display.send_text(text="Loc", font=4, x=0, y=0, width=24, height=7)
                display.send_text(text="Title", font=4, x=27, y=0, width=45, height=7)
                display.send_text(text="Time", font=4, x=75, y=0, width=26, height=7)
                display.send_image("line_hor.png", x=0, y=6)
                display.send_image("line_ver.png", x=25, y=0)
                display.send_image("line_ver.png", x=73, y=0)

                # Get schedule from pretalx
                events = pretalx.get_all_events()

                #tracks = list(set([event['track'] for event in events]))
                #pprint(tracks)
                
                # Filter out all events longer then 2 hours
                events = filter(lambda event: max_duration_filter(event, 2, 0), events)
                
                # Filter out all events that are finished
                events = filter(lambda event: ongoing_or_future_filter(event, max_ongoing=9), events)
                events = list(events)

                if events:
                    for i, event in enumerate(events[:5]):
                        start = dateutil.parser.isoparse(event['date']).replace(tzinfo=None)
                        delta = start - now
                        seconds = round(delta.total_seconds())
                        if seconds < 0:
                            time_text = "- {}m".format(round(-seconds / 60))
                        elif seconds >= 36000:
                            time_text = "{}h".format(round(seconds / 3600))
                        elif seconds >= 3600:
                            time_text = "{}h{}m".format(seconds // 3600, round((seconds % 3600) / 60))
                        else:
                            time_text = "{}m".format(round((seconds % 3600) / 60))

                        track_code = TRACK_CODES.get(event['track'], event['track'].upper()[:2])
                        room_text = ROOM_ABBREVIATIONS.get(event['room'], event['room'])

                        y_base = 8 + i * 12

                        room_text_width = get_text_width(room_text, 5)
                        scroll = (room_text_width > 24)
                        display.send_text(text=room_text + ("   " if scroll else ""), font=4, x=0, y=y_base+2, width=24, height=16, effects=(display.EFFECT_SCROLL if scroll else display.EFFECT_NONE))
                        title_width = get_text_width(event['title'], 10)
                        scroll = (title_width > 45)
                        display.send_text(text=event['title'] + ("        " if scroll else ""), font=10, x=27, y=y_base, width=45, height=16, effects=(display.EFFECT_SCROLL if scroll else display.EFFECT_NONE))
                        display.send_text(text=time_text, font=4, x=75, y=y_base+2, width=26, height=16)
                else:
                    display.send_text(text="No Events", font=12, x=0, y=0, width=display_width, height=display_height, effects=display.EFFECT_CENTERED | display.EFFECT_MIDDLE)
                    
            display.send_queue()
            mode_index += 1
            if mode_index >= len(DISPLAY_MODES):
                mode_index = 0
            mode = DISPLAY_MODES[mode_index]
            time.sleep(page_interval)
        except KeyboardInterrupt:
            raise
        except:
            try:
                display.socket.close()
            except:
                pass
            raise


if __name__ == "__main__":
    backoff = 1
    while True:
        try:
            start_time = time.time()
            main()
        except KeyboardInterrupt:
            break
        except:
            traceback.print_exc()
            now = time.time()
            run_time = now - start_time
            print("Restarting in {} seconds".format(backoff))
            time.sleep(backoff)
            if run_time < 60:
                # If program failed in less than 60 seconds, increase backoff time exponentially
                # Limit it though
                if backoff < 256:
                    backoff *= 2
            else:
                # Otherwise, reset backoff back to 1
                backoff = 1
