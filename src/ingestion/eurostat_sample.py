"""Fetch one Eurostat employment series and show it as a tidy table + a sample."""
import json, urllib.request

# lfsa_egai2d: employed persons by ISCO-08 2-digit occupation
# DE, ICT professionals (OC25), full-time totals, several years
URL = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsa_egai2d"
       "?format=JSON&lang=EN&geo=DE&sex=T&age=Y15-64&unit=THS_PER&isco08=OC25")

def tidy_jsonstat(d):
    """Flatten a JSON-stat cube into rows using the dimension index maps."""
    time_idx = d["dimension"]["time"]["category"]["index"]   # {"2011":0, ...}
    idx2year = {v: k for k, v in time_idx.items()}
    occ = list(d["dimension"]["isco08"]["category"]["label"].values())[0]
    geo = list(d["dimension"]["geo"]["category"]["label"].values())[0]
    rows = []
    for pos, val in d["value"].items():
        rows.append({"geo": geo, "isco_2digit": "25", "occupation": occ,
                     "year": int(idx2year[int(pos)]), "employed_000s": val})
    return sorted(rows, key=lambda r: r["year"])

# NOTE: run this on your machine (sandbox can't reach eurostat).
# Below is what the tidy output looks like once fetched.
if __name__ == "__main__":
    try:
        with urllib.request.urlopen(URL, timeout=30) as r:
            data = json.load(r)
        rows = tidy_jsonstat(data)
        print(f"{'geo':<4}{'isco':<6}{'year':<6}{'employed_000s':<14} occupation")
        for row in rows:
            print(f"{row['geo']:<4}{row['isco_2digit']:<6}{row['year']:<6}{row['employed_000s']:<14}{row['occupation']}")
    except Exception as e:
        print("(couldn't fetch here — run on your machine):", e)