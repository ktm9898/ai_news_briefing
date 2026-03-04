import urllib.request
import json
url = "https://script.google.com/macros/s/AKfycbwtgUJ0QfKHPn6HLt2U41OLUog92RFVaKPyLLVwQodq03LMm50qm4dwQk798D3ovFcaHw/exec"
data = json.dumps({"action": "triggerWorkflow"}).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "text/plain"}, method="POST")
try:
    res = urllib.request.urlopen(req)
    print("Trigger response:", res.getcode(), res.read().decode())
except Exception as e:
    print("Trigger failed:", e)
