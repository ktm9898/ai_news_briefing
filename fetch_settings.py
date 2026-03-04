import urllib.request, json
res = urllib.request.urlopen("https://script.google.com/macros/s/AKfycbwtgUJ0QfKHPn6HLt2U41OLUog92RFVaKPyLLVwQodq03LMm50qm4dwQk798D3ovFcaHw/exec?tab=Settings")
with open("settings_out.json", "w", encoding="utf-8") as f:
    f.write(res.read().decode("utf-8"))
