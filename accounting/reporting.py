from decimal import Decimal
import re

from accounting.models import FinancialReportLine


def _evaluate_formula(formula, amounts_by_code):
    tokens = re.findall(r"[+-]?[^+-]+", formula or "")
    total = Decimal("0.00")
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        sign = Decimal("-1") if token.startswith("-") else Decimal("1")
        code = token[1:].strip() if token[0] in "+-" else token
        total += sign * amounts_by_code.get(code, Decimal("0.00"))
    return total


def build_financial_report(definition):
    """
    Render a user-designed financial report from selected tenant-scoped accounts.
    """
    rows = []
    total = Decimal("0.00")
    amounts_by_code = {}

    lines = definition.lines.prefetch_related("accounts").order_by(
        "line_number", "row_code"
    )
    for line in lines:
        amount = None
        accounts = []
        if line.line_type == FinancialReportLine.LineType.ACCOUNT_SUM:
            accounts = [
                account
                for account in line.accounts.all()
                if account.company_id == definition.company_id
            ]
            amount = sum((account.get_balance() for account in accounts), Decimal("0.00"))
            if line.invert_sign:
                amount = -amount
            if amount != 0 or line.show_zero:
                total += amount
            elif not line.show_zero:
                continue
        elif line.line_type == FinancialReportLine.LineType.FORMULA:
            amount = _evaluate_formula(line.formula, amounts_by_code)
            if line.invert_sign:
                amount = -amount
            if amount != 0 or line.show_zero:
                total += amount
            elif not line.show_zero:
                continue

        if amount is not None:
            amounts_by_code[line.row_code] = amount

        rows.append(
            {
                "line": line,
                "row_code": line.row_code,
                "label": line.label,
                "line_type": line.line_type,
                "accounts": accounts,
                "amount": amount,
            }
        )

    return {
        "definition": definition,
        "rows": rows,
        "total": total,
    }
