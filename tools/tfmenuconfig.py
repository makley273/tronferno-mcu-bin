#!/usr/bin/env python
################################################################################
## tfmenuconfig.py  - menu app to
##       1) program firmware interactively
##       2) configure WLAN and MQTT login data via serial port
##
## Author: Bert Winkelmann <tf.zwiebert@online.de> (2019)
## License: GNU General Public License Version 3 (GNU GPL v3)
################################################################################
import sys, os, serial, sys, re
PYTHON2 = (sys.version_info < (3, 0))

if PYTHON2:
    import ConfigParser as configparser
else:
    import configparser

my_input = raw_input if PYTHON2 else input


import serial.tools.list_ports as list_ports
import subprocess

from sys import path
path.append("tools")
import esptool


is_windows = 0
def _find_getch():
    """
    Return getch() function of user's terminal
    """
    try:
        import termios
    except ImportError:
        # Non-POSIX. Return msvcrt's (Windows') getch.
        import msvcrt
        global is_windows; is_windows = 1
        return msvcrt.getch

    # POSIX system. Create and return a getch that manipulates the tty.
    import sys, tty
    def _getch():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    return _getch
getch = _find_getch()

cfg = configparser.ConfigParser()
cmd_fmt = 'config %s=%s;\n'
ser = 0
CONFIG_FILE = "config.ini"
ANY = 0
MCU_CFG_RETRY_N = 6

ser_list = sorted(ports.device for ports in list_ports.comports())
ser_port = ser_list[0] if len(ser_list) else "com1" if is_windows else "/dev/ttyUSB0"

c_mcu_a = [
    ("wlan-password",""),
    ("wlan-ssid",""),
    ("http-enable",""),
    ("http-user",""),
    ("http-password",""),
    ("mqtt-enable",""),
    ("mqtt-url",""),
    ("mqtt-user",""),
    ("mqtt-password",""),
    ]

c_mcu = dict (c_mcu_a)


opts_verify = {
    "mqtt-url": re.compile("^mqtt://"),
    "mqtt-enable": re.compile("^[01]$"),
    "http-enable": re.compile("^[01]$"),
}
opts_help = {
    "mqtt-url": "MQTT server/broker URL. example: mqtt-url = mqtt://192.168.1.42:7777",
    "mqtt-enable": "set it to 0 or 1 for disable or enable MQTT client",
    "http-enable": "set it to 0 or 1 for disable or enable HTTP server",
}

c_flash_a = [
    ("serial-port", ser_port),
    ("serial-baud", "115200"),
    ("flash-size", "detect"),
    ("chip", "esp32"),
]

c_flash = dict(c_flash_a)

flash_files = {
    "esp32":   ["0x001000", "firmware/esp32/bootloader.bin",
                "0x008000", "firmware/esp32/partitions.bin",
                "0x010000", "firmware/esp32/tronferno-mcu.bin",
                "0x300000", "firmware/esp32/ota_data_initial.bin"],
    "esp8266": ["0x000000", "firmware/esp8266/eagle.flash.bin",
                "0x010000", "firmware/esp8266/eagle.irom0text.bin",
                "0x3FC000", "firmware/esp8266/esp_init_data_default_v08.bin",
                "0x3FE000", "firmware/esp8266/blank.bin"],
}

def do_esptool_write_flash():
    args = ["--chip", c_flash["chip"],
            "--port", c_flash["serial-port"],
            "--baud", c_flash["serial-baud"],
            "write_flash",
            "-z",
            "--flash_mode", "dio",
            "--flash_freq", "40m",
            "--flash_size", c_flash["flash-size"]]
    args.extend(flash_files[c_flash["chip"]])
    try:
        esptool.main(args)
    except esptool.FatalError as e:
        print('\nA fatal error occurred: %s' % e)
    except serial.serialutil.SerialException as e:
        print('\nerror: %s' % e)



def do_esptool_erase_flash():
    args = ["--chip", c_flash["chip"],
            "--port", c_flash["serial-port"],
            "--baud", c_flash["serial-baud"],
            "erase_flash"]
    try:
        esptool.main(args)
    except esptool.FatalError as e:
        print('\nA fatal error occurred: %s' % e)
    except serial.serialutil.SerialException as e:
        print('\nerror: %s' % e)


def do_esptool_chip_id(port=""):
    args = ["--port", port, "chip_id"] if port else ["chip_id"]
    ser_list = [port] if port else reversed(sorted(ports.device for ports in list_ports.comports()))
    try:
        if not ser_list:
            esptool.main(args)
        else:
            for port in ser_list:
                try:
                    esptool.main(["--port", port] + args)
                    press_enter()
                except Exception as e:
                    print("unsuccessful: %s" % e)
                    press_enter()
    except esptool.FatalError as e:
        print('\nerror: %s' % e)
        press_enter()
    except serial.serialutil.SerialException as e:
        print('\nerror: %s' % e)
        press_enter()




def do_tfmcu_write_config_2(key, value):
    """
    writes a tfmcu config key/value pair.
    """
    cmd = cmd_fmt % (key, value)
    #print(cmd)
    ser.write(cmd.encode('utf-8'))
    cmd = cmd_fmt % (key, "?")
    ser.write(cmd.encode('utf-8'))
    lines = ser.readlines()
    for line in lines:
        line = line.decode('utf-8')
        if line.startswith("tf: "):
            #print(line)
            if (line.find(" "+key+"=") != -1 and line.find("="+value.strip('\"')+";") != -1):
                return True
    return False

def write_point(): sys.stdout.write('.'); sys.stdout.flush()

def do_tfmcu_write_config(key, value):
    """
    writes a tfmcu config key/value pair and reports success or failure
    """
    for i in range(MCU_CFG_RETRY_N):
        write_point()
        if do_tfmcu_write_config_2(key, value):
            print("setting option "+key+" succeeded")
            return True
    print("ERROR: setting option "+key+" failed")
    return False

def do_tfmcu_write_config_all():
    """
    writes all tfmcu configuration and reports (except for passwords) success or failure
    """
    global ser
    try:
        ser = serial.Serial(c_flash["serial-port"], int(c_flash["serial-baud"]), timeout=1)
    except:
        print("cannot open serial port " + ser_port)
        ser_list = sorted(ports.device for ports in list_ports.comports())
        print(ser_list)
        return

    for key, value in c_mcu.items():
        if (key.find("-password") != -1):
            do_tfmcu_write_config_2(key, value)
        else:
            do_tfmcu_write_config(key, value)
    ser.close()

def do_app_config_save(path):
    """
    saves user configured data to file PATH
    """
    cf = open(path, "w")
    if not cfg.has_section('MCU'):
        cfg.add_section('MCU')
    for key, value in c_mcu.items():
        cfg.set('MCU', key, value)
    if not cfg.has_section('FLASH'):
        cfg.add_section('FLASH')
    for key, value in c_flash.items():
        cfg.set('FLASH', key, value)
    cfg.write(cf)
    cf.close()

def do_app_config_read(path):
    """
    reads user configured data to file PATH
    """
    try:
        cf = open(path, "r")
        cfg.readfp(cf)
        for key in cfg.options('MCU'):
            value = cfg.get('MCU', key)
            c_mcu[key] = value
            cf.close()
        for key in cfg.options('FLASH'):
            value = cfg.get('FLASH', key)
            c_flash[key] = value
            cf.close()
    except:
        return False
    return True

def press_enter():
    """
    wait for enter key before continue to let the user loog at the command output
    """
    my_input("\n<press enter to continue>")

def ui_menu_serial():
    """
    choose serial port from menu or allow user to provide a device name
    """
    ser_port = ""
    ser_list = sorted(ports.device for ports in list_ports.comports())
    msg_text = "Choose Serial Port:\n"
    n = 0
    for port in ser_list:
        n += 1
        msg_text += " [%d] %s\n" % (n,port)
    msg_text += " [e] edit\n"
    print(msg_text)
    c = getch()
    try:
        if (c == 'e'):
            print("serial port: %s" % (ser_port))
            ser_port = my_input("serial port: ")
        else:
            ser_port = ser_list[int(c)-1]
    except: # nothing selected, cancel
        ser_port = ""
    return ser_port

def ui_process_flash_opts(key, value):
    """
    handle special options
    """
    if key == "serial-port":
        return ui_menu_serial()
    return ""

def ui_verify_mcu_opts(key, value):
    """
    check some special options for correctness
    """
    return True

def ui_verify_opt(key, value):
    """
    check general options for correctness
    """
    if key in opts_verify:
        if not opts_verify[key].match(value):
            print("ERROR: invalid formatted value for key %s: %s" % (key, value))
            if key in opts_help:
                print("HELP: " + opts_help[key])
            press_enter()
            return False
    return True

def menu_char_to_idx(c): return ord(c) - ord("a") # FIXME: start with numbers 1..9 then letters a...w
def menu_idx_to_char(i): return chr(i+ord("a"))

def ui_menu_opts(text, c_arr, c_hash, proc_opts=0, ver_opts=0):
    """
    creates a user menu from the given function arguments
    """
    c_items = [];
    for key, value in c_arr:
        c_items.append(tuple([key, c_hash[key]]));

    changed = {}
    while (True):
        msg_text = (text+"\n"
        " [y] apply changes and leave menu\n"
        " [X] discard changes and leave menu\n"
        "\n")
        n = 0
        for key, value in c_items:
            msg_text += " [%s] %s (%s)\n" % (menu_idx_to_char(n), key, value)
            n += 1
        print(msg_text)
        c = getch()
        if (c == "X"):
            return
        elif (c == "y"):
            for key in changed:
                c_hash[key] = changed[key]
            return
        else:
            try:
                idx = menu_char_to_idx(c)
                key, value = c_items[idx]
                s = ""
                if key in opts_help:
                    print("help: " + opts_help[key])
                if proc_opts:
                    s = proc_opts(key, value)
                if not s:
                    s = my_input("Enter value for %s (%s): ..." % (key, value))
                if s and ui_verify_opt(key, s) and (not ver_opts or ver_opts(key, s)):
                    c_items[idx] = (key, s)
                    changed[key] = s
            except Exception as e:
                print("ex: %s" % e)
                return

ui_menu_txt = "\n\n\n\nPress key to choose menu item:\n"


def ui_menu_root():
    """
    user main menu. should be called from an endless loop as long it returns True
    """
    print(ui_menu_txt+"\n"
          " [q] save config data to file and quit\n"
          " [X] discard config data and quit\n"
          " [s] save configuration data but don't quit\n"
          "\n"
          " [i] find connected chips and print info\n"
          " [I] print info on chip at %s\n" % (c_flash["serial-port"])+
          " [f] configure flash options like serial-port, chip-type, etc\n"
          " [w] write flash (%s@%s). Writes the firmware\n" % (c_flash["chip"], c_flash["serial-port"])+
          " [e] erase flash (%s@%s). Usually not needed. Clears any data and firmware.\n" % (c_flash["chip"], c_flash["serial-port"])+
          "\n"
          " [c] configure tronferno-mcu options like WLAN and MQTT login data\n"
          " [o] write tronferno-mcu options to chip via serial port (do this *after* flashing the firwmware)\n"
          "\nShortcuts:\n"
          " [p] change serial port (%s)\n" % (c_flash["serial-port"])+
          "\n")
    c = getch()
    if   c == "p":
        port = ui_menu_serial()
        if port: c_flash["serial-port"] = port
    elif c == "c": ui_menu_opts(ui_menu_txt, c_mcu_a, c_mcu, ver_opts=ui_verify_mcu_opts)
    elif c == "o": do_tfmcu_write_config_all()
    elif c == "X": return False
    elif c == "e": do_esptool_erase_flash();   press_enter()
    elif c == "w": do_esptool_write_flash();   press_enter()
    elif c == "i": do_esptool_chip_id()
    elif c == "I": do_esptool_chip_id(c_flash["serial-port"])
    elif c == "s": do_app_config_save(CONFIG_FILE)
    elif c == "q": do_app_config_save(CONFIG_FILE); return
    elif c == "f": ui_menu_opts(ui_menu_txt, c_flash_a, c_flash, proc_opts=ui_process_flash_opts)
    return True


def main():
    do_app_config_read(CONFIG_FILE)
    while (ui_menu_root()): pass

if __name__ == '__main__':
    main()
