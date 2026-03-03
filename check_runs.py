import urllib.request, json
req = urllib.request.Request('https://api.github.com/repos/ktm9898/ai_news_briefing/actions/runs', headers={'User-Agent': 'Mozilla/5.0'})
res = urllib.request.urlopen(req)
runs = json.loads(res.read().decode())['workflow_runs']
for r in runs[:5]:
    print(f"ID: {r['id']}, Status: {r['status']}, Conclusion: {r['conclusion']}, Time: {r['created_at']}")
