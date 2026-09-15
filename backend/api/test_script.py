import os
import requests
from dotenv import load_dotenv

load_dotenv()

uri = 'https://api.football-data.org/v4/competitions/PL/matches?season=2022'
headers = {'X-Auth-Token': os.environ.get('FOOTBALL_DATA_TOKEN')}

response = requests.get(uri, headers=headers)
print(response.status_code)
print(response.text[:1000])

data = response.json()
if 'matches' in data:
    for match in data['matches'][:5]:
        print(match.get('utcDate'), match.get('homeTeam', {}).get('name'), 'vs',
              match.get('awayTeam', {}).get('name'), '| attendance:', match.get('attendance'))
