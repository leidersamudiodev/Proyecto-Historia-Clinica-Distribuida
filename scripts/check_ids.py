import urllib.request
import json
for port in [8081, 8082, 8083]:
    try:
        req = urllib.request.Request(f"http://localhost:{port}/fhir/Patient")
        req.add_header("Accept", "application/fhir+json")
        res = urllib.request.urlopen(req)
        data = json.loads(res.read())
        ids = [e["resource"]["id"] for e in data.get("entry", [])]
        print(f"Port {port}: {ids}")
    except Exception as e:
        print(f"Port {port}: {e}")
