@echo usage:  flash.bat COMx


set comport=%1

tools\esptool.exe -p "%comport%" write_flash -ff 40m -fm dio -fs 4MB 0x00000 firmware/eagle.flash.bin 0x10000 firmware/eagle.irom0text.bin  0x3FC000 firmware/esp_init_data_default.bin 0x3FE000 firmware/blank.bin

