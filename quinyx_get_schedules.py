#!/usr/bin/env python3
"""Run the Quinyx GetSchedulesV3 test call for each API key and write every schedule to schedules.csv.

Shifts with subShifts (e.g. "Task + Route") are split into one row per sub-shift. Each row gets the
hours of that sub-shift minus any break that falls inside it.
"""
import csv
import urllib.request
from xml.etree import ElementTree as ET

URL = "https://api.quinyx.com/FlexForceWebServices.php"
OUT = "schedules.csv"

API_KEYS = [
    "c709-8464-bf8b-3953",
    # add the other keys here
]

ENVELOPE = """<soapenv:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:uri="uri:FlexForce">
   <soapenv:Header/>
   <soapenv:Body>
      <uri:wsdlGetSchedulesV3 soapenv:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
         <apiKey xsi:type="xsd:string">{api_key}</apiKey>
         <GetSchedulesV3 xsi:type="flex:GetSchedulesV3" xmlns:flex="https://api.quinyx.com/soap/FlexForce">
            <fromDate xsi:type="xsd:string">2026-10-14</fromDate>
            <toDate xsi:type="xsd:string">2026-10-14</toDate>
         </GetSchedulesV3>
      </uri:wsdlGetSchedulesV3>
   </soapenv:Body>
</soapenv:Envelope>"""

BREAK_TAGS = [("begBreak", "endBreak"), ("begBreak2", "endBreak2"), ("begBreak3", "endBreak3"), ("begBreak4", "endBreak4")]


def local(tag):
    return tag.split("}", 1)[-1]


def minutes(time_text):
    h, m, s = (int(p) for p in time_text.split(":"))
    return h * 60 + m + s / 60


def record_to_row(item):
    row = {}
    for child in item:
        name = local(child.tag)
        if len(child):  # nested list, e.g. subShifts: one "k=v,k=v" group per sub-item, joined by ";"
            row[name] = ";".join(",".join(f"{local(g.tag)}={(g.text or '').strip()}" for g in sub) for sub in child)
        else:
            row[name] = (child.text or "").strip()
    return row


def split_hours(beg, end, breaks):
    """Hours between beg and end (in minutes), minus the overlap with each break."""
    total = end - beg
    for break_beg, break_end in breaks:
        overlap = min(end, break_end) - max(beg, break_beg)
        if overlap > 0:
            total -= overlap
    return round(total / 60, 4)


def schedule_rows(item):
    base = record_to_row(item)
    base.pop("subShifts", None)
    subs = item.find("subShifts")
    if subs is None or not len(subs):
        return [base]

    breaks = []
    for beg_tag, end_tag in BREAK_TAGS:
        beg, end = item.findtext(beg_tag, ""), item.findtext(end_tag, "")
        if beg and end:
            breaks.append((minutes(beg), minutes(end)))

    rows = []
    for sub in subs:
        row = dict(base)
        row["parentCategoryName"] = base.get("categoryName", "")
        for child in sub:
            name = "subShiftId" if local(child.tag) == "id" else local(child.tag)
            row[name] = (child.text or "").strip()
        row["hours"] = split_hours(minutes(row["begTime"]), minutes(row["endTime"]), breaks)
        rows.append(row)
    return rows


def fetch(api_key):
    req = urllib.request.Request(
        URL,
        data=ENVELOPE.replace("{api_key}", api_key).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"uri:FlexForce/GetSchedulesV3"'},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return ET.fromstring(resp.read())


def main():
    rows = []
    for key_nr, api_key in enumerate(API_KEYS, start=1):
        root = fetch(api_key)
        items = [e for e in root.iter() if local(e.tag) == "item" and e.find("{*}restId") is not None]
        found = [row for item in items for row in schedule_rows(item)]
        rows += [{"key_nr": key_nr, **row} for row in found]
        print(f"key {key_nr}: {len(items)} schedules, {len(found)} rows")

    columns = list(dict.fromkeys(k for row in rows for k in row))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows written to {OUT}")


if __name__ == "__main__":
    main()
