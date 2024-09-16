from login import weatherbit
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

