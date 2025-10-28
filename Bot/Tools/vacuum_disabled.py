from deebotozmo import EcoVacsAPI, VacBot
import distutils

# Replace with your Ecovacs credentials
USERNAME = "your_email@example.com"
PASSWORD = "your_password"
COUNTRY = "your_country_code"# Example: 'US'
CONTINENT = "your_continent_code"# Example: 'ww'

api = EcoVacsAPI(USERNAME, PASSWORD, COUNTRY, CONTINENT)
devices = api.devices()
vacbot = VacBot(api.uid, api.REALM, api.resource, api.user_access_token, devices[0])

# Example: Start the cleaning process
vacbot.run('clean')

# Example: Stop the cleaning process
vacbot.run('stop')
