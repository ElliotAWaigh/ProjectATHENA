import asyncio
from pywizlight import wizlight, discovery

bulb_ips = ["192.168.0.149", "192.168.0.233", "192.168.0.228", "192.168.0.153", "192.168.0.91"]
bulb_dictionary = {"192.168.0.149" : "Middle Lamp Light",
                   "192.168.0.233": "Bedroom",
                   "192.168.0.228": "Top Lamp Light",
                   "192.168.0.153": "Bottom Lamp Light",
                   "192.168.0.91": "Mushroom Light"}

async def turn_off_all_lights():
    """Turn off all WizLights using predefined IP addresses."""
    try:
        print("Turning off all WizLights...")
        for ip in bulb_ips:
            try:
                bulb = wizlight(ip)
                print(f"Turning off bulb at IP: {ip}")
                await bulb.turn_off()
                print(f"Bulb at {ip} turned off.")
            except Exception as e:
                print(f"Failed to turn off bulb at {ip}: {e}")
    except Exception as e:
        print(f"Error during operation: {e}")




async def turn_on_all_lights():
    """Turn off all WizLights using predefined IP addresses."""
    try:
        print("Turning off all WizLights...")
        for ip in bulb_ips:
            try:
                bulb = wizlight(ip)
                print(f"Turning on bulb at IP: {ip}")
                await bulb.turn_on()
                print(f"Bulb at {ip} turned on.")
            except Exception as e:
                print(f"Failed to turn off bulb at {ip}: {e}")
    except Exception as e:
        print(f"Error during operation: {e}")


async def test_lighting():
    try:
        test_bulb = bulb_ips[3]
        bulb = wizlight(test_bulb)
        await bulb.turn_off()
    except Exception as e:
        print(f"Error during operation: {e}")

        
# Run the script
if __name__ == "__main__":
    Onoff = input("On or Off?")
    match Onoff:
        case "on":
            asyncio.run(turn_on_all_lights())
        case "off":       
            asyncio.run(turn_off_all_lights())
        case _:
            print("invalid")
            exit()