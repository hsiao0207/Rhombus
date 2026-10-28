"""
Evaluate natural-language -> regex generation against the real LLM.

Each case runs the same generate/validate/self-correct loop the API uses on a small,
deliberately messy dataset, and passes only if the whole resulting table matches the
expected output (target column replaced, everything else untouched).

    uv run python manage.py evaluate_llm                   # run every case
    uv run python manage.py evaluate_llm --case 3          # run one case
    uv run python manage.py evaluate_llm --try "mask phone numbers in Notes with ***"

Every case is one or more real API calls and costs a little money.
"""

import time
from dataclasses import dataclass

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from datasets.exceptions import DomainError
from datasets.services import file_io, llm
from datasets.services.transformation_service import generate_pattern

DATA = pd.DataFrame(
    {
        "Name": ["John Doe", "Jane Smith", "Alice Brown"],
        "Email": ["john.doe@example.com", "jane_smith@domain.com", "alice.brown@website.org"],
        "Phone": ["0912-345-678", "(02) 2345-6789", "+886 912 345 678"],
        "Date": ["2024-01-15", "2023-12-01", "15/03/2024"],
        "Amount": ["$1,200.50", "$85.00", "$3,400.00"],
        "Notes": [
            "Call me at 0912-345-678 or email john.doe@example.com",
            "Order #A1023 shipped to 12 Main St.",
            "Visit https://example.com/promo for details",
        ],
    }
)


@dataclass(frozen=True)
class Case:
    instruction: str
    column: str
    expected: list[str]


CASES = [
    Case(
        "Find email addresses in the Email column and replace them with 'REDACTED'.",
        "Email",
        ["REDACTED", "REDACTED", "REDACTED"],
    ),
    Case(
        "Replace all phone numbers in the Phone column with 'PHONE'",
        "Phone",
        ["PHONE", "PHONE", "PHONE"],
    ),
    Case(
        "Mask every phone number in the Phone column as ***",
        "Phone",
        ["***", "***", "***"],
    ),
    Case(
        "In the Notes column, replace email addresses with [EMAIL]",
        "Notes",
        [
            "Call me at 0912-345-678 or email [EMAIL]",
            "Order #A1023 shipped to 12 Main St.",
            "Visit https://example.com/promo for details",
        ],
    ),
    Case(
        "Mask URLs in Notes with <URL>",
        "Notes",
        [
            "Call me at 0912-345-678 or email john.doe@example.com",
            "Order #A1023 shipped to 12 Main St.",
            "Visit <URL> for details",
        ],
    ),
    Case(
        "Replace order numbers like #A1023 in the Notes column with #XXXX",
        "Notes",
        [
            "Call me at 0912-345-678 or email john.doe@example.com",
            "Order #XXXX shipped to 12 Main St.",
            "Visit https://example.com/promo for details",
        ],
    ),
    Case(
        "Remove the dollar sign and thousands separators from the Amount column",
        "Amount",
        ["1200.50", "85.00", "3400.00"],
    ),
    Case(
        "Convert dates written as YYYY-MM-DD in the Date column to DD/MM/YYYY",
        "Date",
        ["15/01/2024", "01/12/2023", "15/03/2024"],
    ),
    Case(
        "Replace the last names in the Name column with ***",
        "Name",
        ["John ***", "Jane ***", "Alice ***"],
    ),
    Case(
        "Replace every digit in the Phone column with #",
        "Phone",
        ["####-###-###", "(##) ####-####", "+### ### ### ###"],
    ),
    Case(
        "hide the domain part of the emails in Email, keep the username, use @***",
        "Email",
        ["john.doe@***", "jane_smith@***", "alice.brown@***"],
    ),
    Case(
        "Mask Taiwanese mobile numbers in Notes as the literal text 09XX-XXX-XXX",
        "Notes",
        [
            "Call me at 09XX-XXX-XXX or email john.doe@example.com",
            "Order #A1023 shipped to 12 Main St.",
            "Visit https://example.com/promo for details",
        ],
    ),
]


class Command(BaseCommand):
    help = "Evaluate natural-language regex generation against the real LLM."

    def add_arguments(self, parser):
        parser.add_argument("--case", type=int, help="Run only this case number (1-based).")
        parser.add_argument("--try", dest="instruction", help="Try an ad-hoc instruction.")

    def handle(self, *args, case=None, instruction=None, **options):
        try:
            generator = llm.get_regex_generator()
        except DomainError as exc:
            raise CommandError(exc.message) from None
        column_kinds = file_io.infer_column_kinds(DATA)

        if instruction:
            self._try(generator, column_kinds, instruction)
            return

        selected = [(case, CASES[case - 1])] if case else list(enumerate(CASES, start=1))
        passed = 0
        for number, item in selected:
            ok = self._run_case(generator, column_kinds, number, item)
            passed += ok
        style = self.style.SUCCESS if passed == len(selected) else self.style.WARNING
        self.stdout.write(style(f"\n{passed}/{len(selected)} cases passed"))

    def _run_case(self, generator, column_kinds, number, case) -> bool:
        started = time.monotonic()
        try:
            generated = generate_pattern(
                DATA,
                column_kinds,
                instruction=case.instruction,
                replacement=None,
                columns=None,
                generator=generator,
            )
        except DomainError as exc:
            self.stdout.write(self.style.ERROR(f"[{number}] ERROR {exc.code}: {case.instruction}"))
            self.stdout.write(f"     {exc.message} {exc.details}")
            return False

        expected = DATA.copy()
        expected[case.column] = case.expected
        ok = generated.result.data.equals(expected)
        elapsed = time.monotonic() - started
        label = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
        self.stdout.write(f"[{number}] {label} ({elapsed:.1f}s) {case.instruction}")
        self.stdout.write(
            f"     pattern={generated.suggestion.pattern!r} "
            f"replacement={generated.replacement!r} columns={generated.columns} "
            f"attempts={generated.attempts}"
        )
        if not ok:
            for name in DATA.columns:
                got = generated.result.data[name].tolist()
                if got != expected[name].tolist():
                    self.stdout.write(f"     {name}: got {got}")
                    self.stdout.write(f"     {name}: expected {expected[name].tolist()}")
        return ok

    def _try(self, generator, column_kinds, instruction):
        generated = generate_pattern(
            DATA,
            column_kinds,
            instruction=instruction,
            replacement=None,
            columns=None,
            generator=generator,
        )
        suggestion = generated.suggestion
        self.stdout.write(f"pattern:     {suggestion.pattern!r}")
        self.stdout.write(f"flags:       {suggestion.flags}")
        self.stdout.write(f"replacement: {generated.replacement!r}")
        self.stdout.write(f"columns:     {generated.columns}")
        self.stdout.write(f"explanation: {suggestion.explanation}")
        self.stdout.write(f"attempts:    {generated.attempts}")
        self.stdout.write(f"stats:       {generated.result.stats}")
        for change in generated.result.samples:
            self.stdout.write(
                f"  row {change.row} {change.column}: {change.before!r} -> {change.after!r}"
            )
