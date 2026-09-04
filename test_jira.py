import requests
import os
# Manually put your values here just to test
email = os.getenv("EMAIL")
jira_token = os.getenv("JIRA_TOKEN")
url = os.getenv("JIRA_URL")

res = requests.get(url, auth=(email, jira_token))
print(f"Status: {res.status_code}")
if res.status_code == 200:
    print("Success!")
else:
    print(f"Response: {res.text}")
