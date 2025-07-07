# # # # # # # # # # # # # # # #
# @Author: Daan Griffioen     #
# @Date: 30-6-2025            #       
# @Company: Gebr. Griffioen   #
# # # # # # # # # # # # # # # #

# ======= GOOD TO KNOW ======
# Register addresses are divided per 2-bytes meaning 
# 1 in python = 2 in LogoSoft Comfort, 
# 2 = 4, 
# 3 = 6, 
# etc.

# Kraan 1 op adr 1 in Python
# Kraan 2 op adr 2 in Python
# Kraan 3 op adr 3 in Python
# Delay voor kraan 1 op adr 4 in Python
# Delay voor kraan 2 op adr 5 in Python
# Delay voor kraan 3 op adr 6 in Python

# TODO: Space out addresses to avoid buffer overflow
# =======++++++++++++++======

from datetime import datetime, timedelta
from pymodbus.client.tcp import ModbusTcpClient
import logging
import requests
import time

logger = logging.getLogger(__name__)

logging.basicConfig(filename="log.txt", level=logging.INFO)
logger.info("Initialized logger")

repeat_datetime_1     = datetime.now()
repeat_datetime_2     = datetime.now()
start_datetime        = datetime.now()

client              = ModbusTcpClient('192.168.0.3', port=502)
TIJDEN_URL          = ""

herhalen            = False
herhaal_eens        = False
wachten             = False

spray_times         = [0, 0, 0]
wait_times          = [0, 0, 0]
repeat_spray        = [0, 0, 0]
repeat_wait         = [0, 0, 0]

id_number           = 0


def log(string):
    logger.info(f"{datetime.now()}: {string}")

# Update de wait_times lijst om de kranen pas open 
# te zetten als de vorige klaar is
def update_wait_time():
    global spray_times, wait_times
    wait_time = 0
    for i in range(1, 3):
        wait_time += spray_times[i - 1]
        wait_times[i] = wait_time

# Haal data op van de website
def read_data():
    try:
        doc = requests.get(TIJDEN_URL)
    except:
        log(f"Kon webpagina {TIJDEN_URL} niet bereiken")
        return "-1"
    return doc.content.decode()

# Verwerk de data in de spray_times en wait_times arrays
def parse_data(data):
    global spray_times, wait_times, id_number, wachten, start_datetime, herhaal_eens
    global repeat_datetime_1, repeat_datetime_2, repeat_spray, repeat_wait, herhalen

    id = int(data.split('.')[0])
    value = data.split('.')[1]

    match id:
        case id if id == -1:
            log("Aborted")
            herhalen = False
            herhaal_eens = False
        
        case id if id == 0:
            # Check of dit een nieuwe instructie is
            if int(value) == id_number:
                return False
            # Onthoud het nieuwe nummer
            else:
                log(f"Commando binnen voor id: {id} en value: {value}")
                id_number = int(value)

        # Sproeitijden van de kranen
        case id if id < 4:
            log(f"Commando binnen voor id: {id} en value: {value}")
            spray_times[id - 1] = int(value)

        # Starttijd van het sproeien
        case id if id == 4:
            log(f"Commando binnen voor id: {id} en value: {value}")
            start_datetime = datetime.strptime(value, "%Y-%m-%d %H:%M")
            now = datetime.now()
            
            # Check of de starttijd in de toekomst of in het verleden ligt
            if now < start_datetime:
                wachten = True

        # Stel de herhaalde dagelijkse sproeiing in 
        case id if id == 5:
            if len(value) != 0:
                herhaal_eens = True
                repeat_datetime_1 = start_datetime
                repeat_datetime_2 = datetime.combine(start_datetime.date(), datetime.strptime(value, "%H:%M").time())
                
                repeat_spray = spray_times
                repeat_wait = wait_times
                
                # Zorg dat er geen tijden uit het verleden worden gebruikt
                if repeat_datetime_1 < datetime.now():
                    repeat_datetime_1 += timedelta(days=1)
                if repeat_datetime_2 < datetime.now():
                    repeat_datetime_2 += timedelta(days=1)

                log(f"Sproeitijd 1: {repeat_datetime_1}")
                log(f"Sproeitijd 2: {repeat_datetime_2}")
                
                # Return false, omdat het de `check_repeat` functie dit afhandelt

        case id if id == 6:
            if len(value) != 0:
                herhaal_eens = False
                herhalen = True
                return False
            
    return True
                

# Schrijf de commando's naar de specifieke registers
def send_commands(repeat):
    global spray_times, wait_times, repeat_spray, repeat_wait

    for i in range(1, 7):
        if i == 4: continue # Disregard 4 for now
        if i < 4:
            if repeat:
                log(f"Schrijf repeated: {repeat_spray[i-1]} naar {i}")
                client.write_register(i, repeat_spray[i-1])
            else:
                log(f"Schrijf normaal: {spray_times[i-1]} naar {i}")
                client.write_register(i, spray_times[i-1])

        else:
            if repeat:
                log(f"Schrijf repeated: {repeat_wait[i-4]} naar {i}")
                client.write_register(i, repeat_wait[i-4])
            else:
                log(f"Schrijf normaal: {wait_times[i-4]} naar {i}")
                client.write_register(i, wait_times[i-4])
    

# Check of het tijd is om de herhaling uit te voeren
def check_repeat():
    global repeat_datetime_1, repeat_datetime_2, herhalen, herhaal_eens
    if herhalen or herhaal_eens:

        if repeat_datetime_1 - datetime.now() < timedelta(minutes=5):
            repeat_datetime_1 += timedelta(days=1)
            return True
        elif repeat_datetime_2 - datetime.now() < timedelta(minutes=5):
            repeat_datetime_2 += timedelta(days=1)
            if herhaal_eens: herhaal_eens = False
            return True

    return False


# Check of we wachten en of we moeten beginnen
def check_wachten():
    global wachten, start_datetime

    if not wachten: return False
    if start_datetime - datetime.now() < timedelta(minutes=5):
        wachten = False
        return True
    
    return False


def start_plc():
    client.write_coil(0, True)
    time.sleep(0.5)
    client.write_coil(0, False)


def main():
    data = read_data()
    for line in data.split('\n'):
        
        if line != '' and line != "-1":
            if not parse_data(line):
                return False
            else:
                update_wait_time()
        elif line == "-1":
            return False
    return True


def next_datetime(date_1, date_2):
    if date_1 > date_2: return date_1
    return date_2


# Blijf draaien en check elke 15 seconden voor instructies
if __name__ == "__main__":
    logger.info("Started system")
    while True:
        # Check of er een nieuw sproeicommando is
        if main() or check_wachten():
            print("Wachten / commando")
            wachten = False
            send_commands(False)
            start_plc()
            log("PLC gestart")
            
        # Check of het tijd is voor de dagelijkse sproeiing
        elif check_repeat():
            print("Herhaald")
            send_commands(True)
            start_plc()
            if herhalen:
                log(f"PLC gestart, volgende aanroep op {next_datetime(repeat_datetime_1, repeat_datetime_2)}")

        time.sleep(5)
            