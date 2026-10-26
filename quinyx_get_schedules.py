#!/usr/bin/env python3
"""Run the Quinyx GetSchedulesV3 call and write every schedule to schedules.csv.

Usage:
    export QUINYX_API_KEY='your-key'
    python3 quinyx_get_schedules.py
"""
import csv
import os
import urllib.request
from xml.etree import ElementTree as ET

URL = "https://api.quinyx.com/FlexForceWebServices.php"
FROM_DATE = "2026-10-14"
TO_DATE = "2026-10-14"
OUT = "schedules.csv"

ENVELOPE = """<soapenv:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:uri="uri:FlexForce">
   <soapenv:Header/>
   <soapenv:Body>
      <uri:wsdlGetSchedulesV3 soapenv:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
         <apiKey xsi:type="xsd:string">{api_key}</apiKey>
         <GetSchedulesV3 xsi:type="flex:GetSchedulesV3" xmlns:flex="https://api.quinyx.com/soap/FlexForce">
            <fromDate xsi:type="xsd:string">{from_date}</fromDate>
            <toDate xsi:type="xsd:string">{to_date}</toDate>
         </GetSchedulesV3>
      </uri:wsdlGetSchedulesV3>
   </soapenv:Body>
</soapenv:Envelope>"""


def local(tag):
    return tag.split("}", 1)[-1]


def record_to_row(item):
    row = {}
    for child in item:
        name = local(child.tag)
        if len(child):  # nested list, e.g. subShifts: one "k=v,k=v" group per sub-item, joined by ";"
            row[name] = ";".join(",".join(f"{local(g.tag)}={(g.text or '').strip()}" for g in sub) for sub in child)
        else:
            row[name] = (child.text or "").strip()
    return row


def main():
    body = ENVELOPE.replace("{api_key}", os.environ["QUINYX_API_KEY"])
    body = body.replace("{from_date}", FROM_DATE).replace("{to_date}", TO_DATE).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"uri:FlexForce/GetSchedulesV3"'},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        root = ET.fromstring(resp.read())

    rows = [record_to_row(e) for e in root.iter() if local(e.tag) == "item" and e.find("{*}restId") is not None]
    columns = list(dict.fromkeys(k for row in rows for k in row))

    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} schedules written to {OUT}")


if __name__ == "__main__":
    main()
