from wakeonlan import send_magic_packet
from Tools.login import wakeonlan


def wakeup():
        MAC = wakeonlan()
        print(MAC)
        try: 
            send_magic_packet(MAC)
            print("Packet Sent")
        except:
            print("No go")

wakeup()