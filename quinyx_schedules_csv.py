#!/usr/bin/env python3
"""Call Quinyx FlexForce GetSchedulesV3 and write the returned schedules to a CSV file.

The API key is read from the QUINYX_API_KEY environment variable so it does not
end up in shell history. Only the Python standard library is used.
"""
import argparse
import csv
import os
import sys
import urllib.request
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

URL = "https://api.quinyx.com/FlexForceWebServices.php"

REQUEST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" xmlns:tns="https://api.quinyx.com/soap/FlexForce">
  <soap:Body>
    <tns:wsdlGetSchedulesV3>
    <apiKey xsi:type="xsd:string">{api_key}</apiKey>
    <GetSchedulesV3 xsi:type="tns:GetSchedulesV3">
      <section xsi:type="xsd:string">{section}</section>
      <badgeNo xsi:type="xsd:string">{badge_no}</badgeNo>
      <employeeId xsi:type="xsd:int">{employee_id}</employeeId>
      <fromDate xsi:type="xsd:string">{from_date}</fromDate>
      <fromTime xsi:type="xsd:string">{from_time}</fromTime>
      <toDate xsi:type="xsd:string">{to_date}</toDate>
      <toTime xsi:type="xsd:string">{to_time}</toTime>
      <scheduledShifts xsi:type="xsd:boolean">true</scheduledShifts>
      <absenceShifts xsi:type="xsd:boolean">true</absenceShifts>
      <modifiedAfter xsi:type="xsd:string">{modified_after}</modifiedAfter>
      <modifiedBefore xsi:type="xsd:string">{modified_before}</modifiedBefore>
      <includeCosts xsi:type="xsd:boolean">true</includeCosts>
      <useFixedSchedule xsi:type="xsd:boolean">true</useFixedSchedule>
      <includeNOI xsi:type="xsd:boolean">true</includeNOI>
      <includeTags xsi:type="xsd:boolean">true</includeTags>
      <includeExtScheduleId xsi:type="xsd:boolean">true</includeExtScheduleId>
    </GetSchedulesV3>
    </tns:wsdlGetSchedulesV3>
  </soap:Body>
</soap:Envelope>
"""


def local_name(tag):
    return tag.split("}", 1)[-1]


def flatten(elem, prefix=""):
    """Turn an XML element into a flat {column: value} dict. Nested tags are joined with '.'.

    Repeated tags under the same parent get a number suffix (subShifts.item_1.id, subShifts.item_2.id).
    """
    out = {}
    tags = [local_name(c.tag) for c in elem]
    seen = {}
    for child in elem:
        tag = local_name(child.tag)
        name = prefix + tag
        if tags.count(tag) > 1:
            seen[tag] = seen.get(tag, 0) + 1
            name = f"{name}_{seen[tag]}"
        if len(child):
            out.update(flatten(child, name + "."))
        else:
            out[name] = (child.text or "").strip()
    return out


def is_soap_array(elem):
    return any(k.endswith("arrayType") for k in elem.attrib)


def find_records(root):
    """Return the list of repeated elements (one per schedule). Falls back to the body itself."""
    for parent in root.iter():
        if is_soap_array(parent):  # e.g. subShifts: nested lists, not the schedule list
            continue
        tags = [local_name(c.tag) for c in parent]
        repeated = {t for t in tags if tags.count(t) > 1}
        if repeated:
            return [c for c in parent if local_name(c.tag) in repeated]
    return [root]


def parse_records(xml_bytes):
    root = ET.fromstring(xml_bytes)
    fault = root.find(".//{*}Fault")
    if fault is not None:
        msg = "".join(fault.itertext()).strip()
        raise SystemExit(f"SOAP fault from Quinyx: {msg}")
    return [flatten(rec) for rec in find_records(root)]


def write_csv(rows, path, delimiter):
    columns = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def build_request(args, api_key):
    return REQUEST_TEMPLATE.format(
        api_key=escape(api_key),
        section=escape(args.section),
        badge_no=escape(args.badge_no),
        employee_id=int(args.employee_id),
        from_date=escape(args.from_date),
        from_time=escape(args.from_time),
        to_date=escape(args.to_date),
        to_time=escape(args.to_time),
        modified_after=escape(args.modified_after),
        modified_before=escape(args.modified_before),
    ).encode("utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--employee-id", required=True, type=int)
    p.add_argument("--from-date", required=True, help="format as the API expects, e.g. 2026-10-01")
    p.add_argument("--to-date", required=True, help="format as the API expects, e.g. 2026-10-31")
    p.add_argument("--from-time", default="")
    p.add_argument("--to-time", default="")
    p.add_argument("--section", default="")
    p.add_argument("--badge-no", default="")
    p.add_argument("--modified-after", default="")
    p.add_argument("--modified-before", default="")
    p.add_argument("--out", default="schedules.csv")
    p.add_argument("--delimiter", default=",")
    p.add_argument("--save-xml", help="also save the raw SOAP response to this path")
    args = p.parse_args()

    api_key = os.environ.get("QUINYX_API_KEY")
    if not api_key:
        sys.exit("Set QUINYX_API_KEY in the environment first.")

    req = urllib.request.Request(
        URL,
        data=build_request(args, api_key),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"uri:FlexForce/GetSchedulesV3"'},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read()

    if args.save_xml:
        with open(args.save_xml, "wb") as fh:
            fh.write(body)

    rows = parse_records(body)
    write_csv(rows, args.out, args.delimiter)
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
