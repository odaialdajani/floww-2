"""Agent 4 fixture evaluator: every case must carry an expected output. Run: python3 check_fixtures.py"""
import glob, json, os, sys
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
fails = []
for f in sorted(glob.glob(os.path.join(base, "*.json"))):
    try: data = json.load(open(f))
    except Exception as e: fails.append((f, "unparseable: %s" % e)); continue
    def walk(o, path):
        if isinstance(o, dict):
            if "expected" in o and not o["expected"]: fails.append((f, path + " empty expected"))
            for k, v in o.items():
                if k != "_note" and isinstance(v, (dict, list)): walk(v, path + "/" + k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if isinstance(v, dict) and "id" in v and "expected" not in v:
                    fails.append((f, "%s[%d] missing expected" % (path, i)))
                walk(v, "%s[%d]" % (path, i))
    walk(data, "")
if fails:
    print("FAIL"); [print(" -", x) for x in fails]; sys.exit(1)
print("PASS: all fixture cases carry expected outputs (%d files)" % len(glob.glob(os.path.join(base, "*.json"))))
