import csv
import io
import json


class ExportPayload:
    def __init__(self, *, body, content_type, filename):
        self.body = body
        self.content_type = content_type
        self.filename = filename


def _employee_dict(employee):
    return {
        "employee_id": employee.emp_id,
        "first_name": employee.display_first_name,
        "last_name": employee.display_last_name,
        "email": employee.get_email(),
        "department": employee.department.name if employee.department else "",
        "job_title": employee.job_title,
        "status": employee.status,
        "date_of_employment": str(employee.date_of_employment or ""),
        "phone": employee.phone,
        "address": employee.address or "",
        "emergency_contact_name": employee.emergency_contact_name or "",
        "emergency_contact_phone": employee.emergency_contact_phone or "",
        "bank_account_name": employee.bank_account_name or "",
        "bank_account_number": employee.bank_account_number or "",
        "pension_rsa": employee.pension_rsa or "",
    }


def build_employee_export(employee, export_format="json") -> ExportPayload:
    export_format = (export_format or "json").lower()
    data = _employee_dict(employee)
    stem = f"employee-{employee.pk}-data"

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data.keys()))
        writer.writeheader()
        writer.writerow(data)
        return ExportPayload(
            body=output.getvalue(),
            content_type="text/csv",
            filename=f"{stem}.csv",
        )

    if export_format == "pdf":
        text = "\n".join(f"{key}: {value}" for key, value in data.items())
        return ExportPayload(
            body=_simple_pdf(text),
            content_type="application/pdf",
            filename=f"{stem}.pdf",
        )

    return ExportPayload(
        body=json.dumps(data, indent=2, sort_keys=True),
        content_type="application/json",
        filename=f"{stem}.json",
    )


def _simple_pdf(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
        .replace("\n", ") Tj T* (")
    )
    stream = f"BT /F1 10 Tf 50 780 Td ({escaped}) Tj ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(stream.encode('utf-8'))} >> stream\n{stream}\nendstream endobj",
    ]
    body = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(body.encode("utf-8")))
        body += obj + "\n"
    xref_start = len(body.encode("utf-8"))
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        body += f"{offset:010d} 00000 n \n"
    body += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    )
    return body
