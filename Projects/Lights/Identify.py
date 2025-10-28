import asyncio
from pywizlight import wizlight, PilotBuilder
import time

# Define the IP address of the WiZ light
LIGHT_IP = "192.168.0.91"

async def flash_red(ip, duration=10, interval=0.5):
    """Make a WiZ light flash red on and off.
    
    Args:
        ip (str): The IP address of the WiZ light.
        duration (int): Total duration for the flashing effect in seconds.
        interval (float): Time in seconds between on and off.
    """
    light = wizlight(ip)
    end_time = time.time() + duration  # Calculate the end time
    
    try:
        print(f"Flashing red light at IP {ip}...")
        while time.time() < end_time:
            # Turn on the light with red color
            await light.turn_on(PilotBuilder(rgb=(255, 0, 0)))
            await asyncio.sleep(interval)
            
            # Turn off the light
            await light.turn_off()
            await asyncio.sleep(interval)
            
        print("Flashing complete.")
    except Exception as e:
        print(f"Error while flashing the light: {e}")

# Run the script
if __name__ == "__main__":
    asyncio.run(flash_red(LIGHT_IP, duration=10, interval=0.5))
