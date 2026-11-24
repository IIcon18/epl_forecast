import os

import requests
from dotenv import load_dotenv

load_dotenv()

uri = 'https://api.football-data.org/v4/competitions/PL/matches?status=SCHEDULED'
headers = {'X-Auth-Token': os.environ.get('FOOTBALL_DATA_TOKEN')}

response = requests.get(uri, headers=headers)
print(response.status_code)

data = response.json()
print('Всего запланированных матчей:', data.get('resultSet', {}).get('count'))

for match in data.get('matches', [])[:10]:
    print(
        match.get('utcDate'),
        match.get('matchday'),
        match.get('homeTeam', {}).get('name'), 'vs',
        match.get('awayTeam', {}).get('name'),
        '| status:', match.get('status')
    )
