#!/usr/bin/env python3
"""
generate_vcard_qr.py

Generate a vCard (VCF) and save it as an SVG QR code image (offline).

This patch fixes a runtime error where generate_qr_svg was not defined.
It also makes the SVG QR generation more robust by checking for the
svg image factory and reporting a clear error if the dependency is missing.

Behavior and CLI unchanged from the last version you had:
- CRLF by default (use --line-ending lf for LF-only)
- remote avatar and PGP key URIs
- X-PGP-FP support
- GitHub produces URL + Apple item label
- Structured name support (--given / --surname / --preferred-name)
"""
from __future__ import annotations
import argparse
import sys
import qrcode
import qrcode.constants
from typing import Optional
import getpass
import re

# Attempt to import the SVG image factory used by qrcode.
# If not available, provide a helpful error when trying to generate SVG.
try:
    from qrcode.image.svg import SvgPathImage
    _SVG_FACTORY_AVAILABLE = True
except Exception:
    SvgPathImage = None
    _SVG_FACTORY_AVAILABLE = False

WARN_QR_BYTES = 2000
MAX_QR_BYTES = 2950  # conservative practical limit for QR payloads

def is_http_url(s: str) -> bool:
    return bool(s) and (s.startswith("http://") or s.startswith("https://"))

def escape_vcard_value(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.replace("\\", "\\\\")
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n")
    return s

def fold_vcard_line(line: str, width: int = 75, line_ending: str = "\r\n") -> str:
    if len(line) <= width:
        return line
    parts = [line[i:i+width] for i in range(0, len(line), width)]
    sep = line_ending + " "
    return sep.join(parts)

def normalize_fingerprint(fp: str) -> str:
    if not fp:
        return ""
    s = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()
    if not re.fullmatch(r"[0-9A-F]+", s):
        raise ValueError("Fingerprint contains invalid characters")
    if len(s) not in (8, 16, 40):
        raise ValueError("Fingerprint must be 8, 16, or 40 hex characters (short, long, or full fingerprint)")
    return s

def build_vcard(full_name: str,
                given: str,
                surname: str,
                preferred_name: str,
                email: Optional[str] = "",
                phone: Optional[str] = "",
                github: Optional[str] = "",
                city: Optional[str] = "",
                country: Optional[str] = "",
                note: Optional[str] = "",
                avatar_uri: Optional[str] = "",
                pgp_key_uri: Optional[str] = "",
                pgp_fingerprint: Optional[str] = "",
                line_ending: str = "\r\n") -> str:
    """
    Build a vCard 3.0 string using the requested line ending (CRLF or LF).
    N: family;given;additional;prefix;suffix
    FN: formatted name (see selection logic in caller)
    preferred_name -> NICKNAME and X-PREFERRED-NAME
    """
    fn = full_name or ""
    family = escape_vcard_value(surname)
    given_e = escape_vcard_value(given)
    n_field = f"N:{family};{given_e};;;"

    email_e = escape_vcard_value(email)
    tel = escape_vcard_value(phone)
    github_url = ""
    apple_item_lines = []
    x_social = ""
    if github:
        if is_http_url(github):
            github_url = github
        else:
            github_url = f"https://github.com/{github}"
        x_social = f"X-SOCIALPROFILE;TYPE=github:{escape_vcard_value(github_url)}"
        apple_item_lines = [
            f"item1.URL;type=pref:{escape_vcard_value(github_url)}",
            f"item1.X-ABLabel:GitHub"
        ]

    locality = escape_vcard_value(city)
    country_e = escape_vcard_value(country)
    note_e = escape_vcard_value(note)
    adr = f"ADR:;;;{locality};;{country_e}"

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
    ]

    lines.append(f"FN:{escape_vcard_value(fn)}")
    lines.append(n_field)

    if tel:
        lines.append(f"TEL;TYPE=CELL:{tel}")
    if email_e:
        lines.append(f"EMAIL;TYPE=INTERNET:{email_e}")

    if github_url:
        lines.append(f"URL:{escape_vcard_value(github_url)}")
    if x_social:
        lines.append(x_social)
    lines.extend(apple_item_lines)

    if locality or country_e:
        lines.append(adr)
    if note_e:
        lines.append(f"NOTE:{note_e}")

    if avatar_uri:
        if not is_http_url(avatar_uri):
            raise ValueError("Avatar must be an http(s) URL when provided. Inline embedding is disabled.")
        lines.append(f"PHOTO;VALUE=URI:{escape_vcard_value(avatar_uri)}")

    if pgp_key_uri:
        if not is_http_url(pgp_key_uri):
            raise ValueError("PGP key URI must be an http(s) URL when provided.")
        lines.append(f"KEY;VALUE=URI:{escape_vcard_value(pgp_key_uri)}")

    if pgp_fingerprint:
        lines.append(f"X-PGP-FP:{escape_vcard_value(pgp_fingerprint)}")

    if preferred_name:
        pref_e = escape_vcard_value(preferred_name)
        lines.append(f"NICKNAME:{pref_e}")
        lines.append(f"X-PREFERRED-NAME:{pref_e}")

    lines.append("END:VCARD")

    joined = line_ending.join(lines)
    folded_lines = []
    for L in joined.split(line_ending):
        folded_lines.append(fold_vcard_line(L, width=75, line_ending=line_ending))
    return line_ending.join(folded_lines) + line_ending

def save_vcf(vcard_text: str, path: str, line_ending: str = "\r\n") -> None:
    if line_ending == "\r\n":
        # write CRLF explicitly as bytes to avoid platform translation surprises
        with open(path, "wb") as f:
            f.write(vcard_text.encode("utf-8"))
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(vcard_text)

def approx_size_warn_and_check(s: str):
    length = len(s.encode("utf-8"))
    if length > WARN_QR_BYTES:
        print(f"Warning: vCard content is approximately {length} bytes. Large payloads may produce dense QR codes that some scanners struggle to read.", file=sys.stderr)
    if length > MAX_QR_BYTES:
        raise ValueError(f"vCard content is too large for a practical QR (≈{length} bytes). Shorten fields or remove content.")

def generate_qr_svg(vcard_text: str, out_path: str, error_correction=qrcode.constants.ERROR_CORRECT_Q) -> None:
    """
    Generate an SVG QR containing the provided vcard_text and save to out_path.

    This function is defined before use to avoid NameError. It also checks that
    the SVG factory is available and raises a clear error if not.
    """
    if not _SVG_FACTORY_AVAILABLE or SvgPathImage is None:
        raise RuntimeError(
            "SVG image factory not available. Install the optional dependency 'qrcode[svg]' "
            "or 'qrcode[pil]' with SVG support. Example: pip install qrcode[pil] qrcode[svg]"
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=4,
    )
    qr.add_data(vcard_text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    # SvgPathImage supports .save()
    img.save(out_path)

def prompt_if_missing(args):
    def ask(prompt_text, current, hide=False):
        if current:
            return current
        if hide:
            try:
                return getpass.getpass(prompt_text).strip()
            except Exception:
                return input(prompt_text).strip()
        return input(prompt_text).strip()

    args.given = ask("Given name (first name) (optional): ", args.given)
    args.surname = ask("Surname / family name (optional): ", args.surname)
    args.preferred_name = ask("Preferred name / nickname (optional): ", args.preferred_name)

    if not args.given and not args.surname:
        args.name = ask("Full formatted name (required if no given/surname): ", args.name)
    else:
        args.name = args.name or ""

    args.email = ask("Email (optional): ", args.email, hide=True)
    args.phone = ask("Phone (optional): ", args.phone, hide=True)
    args.note = ask("Note/comment (optional): ", args.note, hide=True)

    if not args.avatar:
        avatar_ans = input("Avatar URL to include? (leave blank to skip) ").strip()
        args.avatar = avatar_ans
    if not args.pgp_key_uri:
        pgp_ans = input("PGP public key URL to include? (leave blank to skip) ").strip()
        args.pgp_key_uri = pgp_ans
    if not args.pgp_fingerprint:
        fp_ans = input("PGP fingerprint (full 40-hex or long 16-hex or short 8-hex) (leave blank to skip): ").strip()
        args.pgp_fingerprint = fp_ans
    if not args.country:
        country_ans = input("Country (optional): ").strip()
        args.country = country_ans
    if not args.city:
        city_ans = input("City/locality (optional): ").strip()
        args.city = city_ans
    if not args.github:
        gh_ans = input("GitHub username or full URL (optional): ").strip()
        args.github = gh_ans
    return args

def main(argv=None):
    p = argparse.ArgumentParser(description="Generate a vCard QR (offline) and save as SVG. Avatars and PGP keys must be remote URIs.")
    p.add_argument("--name", "-n", default="", help="Full formatted name (fallback; FN). If given+surname provided this is optional.")
    p.add_argument("--given", "-f", default="", help="Given name / first name")
    p.add_argument("--surname", "-s", default="", help="Surname / family name")
    p.add_argument("--preferred-name", default="", help="Preferred name / nickname (will populate NICKNAME and X-PREFERRED-NAME)")
    p.add_argument("--email", "-e", default="", help="Email address (sensitive; may be visible in process list)")
    p.add_argument("--phone", "-p", default="", help="Phone number (sensitive; may be visible in process list)")
    p.add_argument("--github", "-g", default="", help="GitHub username or full URL (will produce URL and an Apple-labeled item)")
    p.add_argument("--city", "-c", default="", help="City/locality")
    p.add_argument("--country", default="", help="Country (will be put in ADR country component)")
    p.add_argument("--note", default="", help="Note / comment (e.g. 'Open for hire') (sensitive)")
    p.add_argument("--avatar", "-a", default="", help="Avatar image URI (http(s) URL). Inline embedding is NOT supported.")
    p.add_argument("--pgp-key-uri", default="", help="PGP public key URI (http(s) URL) to include as KEY;VALUE=URI:... in the vCard.")
    p.add_argument("--pgp-fingerprint", default="", help="PGP fingerprint to include as X-PGP-FP (accepts 40, 16 or 8 hex chars).")
    p.add_argument("--out-svg", default="vcf_qr.svg", help="Output SVG filename for QR")
    p.add_argument("--vcf", "-v", default="", help="Optional: also write a .vcf file")
    p.add_argument("--line-ending", choices=["crlf", "lf"], default="crlf", help="Line ending to use in vCard/QR (crlf default per RFC; lf for unix-only)")
    p.add_argument("--no-prompt", action="store_true", help="Do not prompt interactively for missing values")
    args = p.parse_args(argv)

    if not args.no_prompt:
        args = prompt_if_missing(args)

    if not (args.name or args.given or args.surname):
        print("Error: you must provide a name. Either --name (full) or --given/--surname must be provided.", file=sys.stderr)
        sys.exit(2)

    if args.avatar and not is_http_url(args.avatar):
        print("Error: --avatar must be an http(s) URL. Inline embedding/local files are not allowed in this version.", file=sys.stderr)
        sys.exit(3)
    if args.pgp_key_uri and not is_http_url(args.pgp_key_uri):
        print("Error: --pgp-key-uri must be an http(s) URL.", file=sys.stderr)
        sys.exit(4)

    normalized_fp = ""
    if args.pgp_fingerprint:
        try:
            normalized_fp = normalize_fingerprint(args.pgp_fingerprint)
            if len(normalized_fp) == 8:
                print("Warning: 8-hex short keyid is collision-prone; prefer the 16-hex long keyid or full 40-hex fingerprint.", file=sys.stderr)
            elif len(normalized_fp) == 16:
                print("Note: using 16-hex long keyid; safer than 8-hex but include full fingerprint if possible.", file=sys.stderr)
        except ValueError as e:
            print(f"Error: invalid --pgp-fingerprint: {e}", file=sys.stderr)
            sys.exit(5)

    line_ending = "\r\n" if args.line_ending == "crlf" else "\n"

    # Determine structured given and surname if not explicitly provided
    given = args.given.strip()
    surname = args.surname.strip()
    if not (given or surname):
        name_tokens = args.name.strip().split()
        if len(name_tokens) >= 2:
            surname = name_tokens[-1]
            given = " ".join(name_tokens[:-1])
        else:
            given = args.name.strip()
            surname = ""

    # Decide FN (formatted name) if not explicitly supplied:
    fn = args.name.strip()
    if not fn:
        if args.preferred_name:
            fn = args.preferred_name.strip()
            if surname:
                fn = f"{fn} {surname}"
        else:
            fn = " ".join([p for p in (given, surname) if p]).strip()

    try:
        vcard = build_vcard(
            full_name=fn,
            given=given,
            surname=surname,
            preferred_name=args.preferred_name.strip(),
            email=args.email,
            phone=args.phone,
            github=args.github,
            city=args.city,
            country=args.country,
            note=args.note,
            avatar_uri=args.avatar,
            pgp_key_uri=args.pgp_key_uri,
            pgp_fingerprint=normalized_fp,
            line_ending=line_ending,
        )
    except Exception as e:
        print(f"Failed to build vCard: {e}", file=sys.stderr)
        sys.exit(6)

    try:
        approx_size_warn_and_check(vcard)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Suggested fixes: shorten fields or remove optional fields.", file=sys.stderr)
        sys.exit(7)

    try:
        # This will raise a helpful error if the SVG factory is missing.
        generate_qr_svg(vcard, args.out_svg)
        print(f"Saved QR SVG to {args.out_svg}")
    except Exception as e:
        print(f"Failed to generate SVG QR: {e}", file=sys.stderr)
        # If the specific problem is missing SVG support, print actionable advice.
        if not _SVG_FACTORY_AVAILABLE:
            print("Hint: to enable SVG support install qrcode svg extras, e.g.: pip install qrcode[svg]", file=sys.stderr)
        sys.exit(8)

    if args.vcf:
        try:
            save_vcf(vcard, args.vcf, line_ending=line_ending)
            print(f"Saved vCard (.vcf) to {args.vcf}")
        except Exception as e:
            print(f"Failed to write .vcf file: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()