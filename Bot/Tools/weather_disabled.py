from Tools.login import weatherbit
import requests

API_KEY = weatherbit()


city = 'Brisbane'

url = f"https://api.weatherbit.io/v2.0/current?city={city}&key={API_KEY}"

response = requests.get(url)

# Print the full response JSON to check its structure

data = response.json()
print(data)

# Try to extract temperature and weather description
try:
    temperature = data['data'][0]['temp']
    weather_desc = data['data'][0]['weather']['description']

    print(f"Temperature: {temperature}°C")
    print(f"Weather Description: {weather_desc}")
except KeyError as e:
    print(f"KeyError: {e} - Check the structure of the response data.")


# Algorithm
def optimal_weather_drying():
    degrees_celcius = 26
    humidity = 50
    wind = range(15,25)

def mid_weather_drying():
    degrees_celcius = range(15,25)
    humidity = range(50,70)
    wind = range(5,15)

def least_optimal_drying():
    degrees_celcius = 15
    humidity = 70
    wind = range(0,5)

def no_option():
    weather = "rain"

def algorithm():
    degrees = 24
    humidity = 45
    wind = 4
    # check if weather is within a certain list range
    optimal_degrees = []
    mid_degrees = []
    least_degrees = []
    
    # maybe use case?
    match degrees:
        case d if d in optimal_degrees:
            temperature = 'optimal'
            pass
        case d if d in mid_degrees:
            temperature = 'okay'
            pass
        case d if d in least_degrees:
            temperature = 'not optimal'
            pass
        
    match humidity:
        case h:
            pass
    
        