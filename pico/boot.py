import usb_cdc
import usb_hid

print("tuxbridge boot.py start")

# Custom HID descriptor: a Mouse with 16-bit signed relative X/Y, so the host
# accepts a full-screen delta in a single report (the stock adafruit Mouse
# caps each axis at ±127). Buttons go through the *standard* Mouse on a
# different report ID; this interface is move-only.
REL16_DESCRIPTOR = bytes((
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x04,        #   Report ID 4
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01, 0x29, 0x03,
    0x15, 0x00, 0x25, 0x01,
    0x95, 0x03, 0x75, 0x01, 0x81, 0x02,  # 3 button bits
    0x95, 0x01, 0x75, 0x05, 0x81, 0x03,  # 5 bits padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30, 0x09, 0x31,              # X, Y
    0x16, 0x00, 0x80,  #     Logical Min -32768
    0x26, 0xFF, 0x7F,  #     Logical Max  32767
    0x75, 0x10,        #     Report Size 16
    0x95, 0x02,        #     Report Count 2
    0x81, 0x06,        #     Input (Data,Var,Rel)
    0xC0, 0xC0,
))

rel16_mouse = usb_hid.Device(
    report_descriptor=REL16_DESCRIPTOR,
    usage_page=0x01,
    usage=0x02,
    report_ids=(4,),
    in_report_lengths=(5,),
    out_report_lengths=(0,),
)

try:
    usb_hid.enable((
        usb_hid.Device.KEYBOARD,
        usb_hid.Device.MOUSE,
        rel16_mouse,
    ))
    print("tuxbridge: hid enabled with rel16")
except Exception as e:
    print("tuxbridge: hid enable failed:", e)

usb_cdc.enable(console=True, data=True)
print("tuxbridge boot.py end")
