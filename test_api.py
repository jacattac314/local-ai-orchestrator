"""Test the API to verify real OpenRouter data is being used."""
import requests

response = requests.get('http://127.0.0.1:8080/v1/models/rankings')
data = response.json()

print(f"Total models: {data.get('total_models', 0)}")
print(f"Profile: {data.get('profile')}")
print("\nTop 10 models:")
for r in data.get('rankings', [])[:10]:
    print(f"  {r['rank']}. {r['model_name']} (score: {r['composite_score']:.2f})")
