import requests

token = "8015781832:AAELS7w7iJF66a2bKn8vUwHIU6nPU4D0mR4"   # your bot token

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates").json()
print(r)
