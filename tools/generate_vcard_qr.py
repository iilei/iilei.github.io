#!/usr/bin/env python3
"""
generate_vcard_qr.py

Create a vCard (VCF) and save it as an SVG QR code image (offline).

Behavior changes in this version:
- Avatar embedding via remote URI is the default and the only supported avatar embedding method.
  Provide --avatar "https://example.com/avatar.jpg". Local file paths and inline base64 PHOTO are not allowed.
- Sensitive fields (email, phone, note) will be prompted for using getpass-style input if omitted,
  to reduce exposure on command lines on multi-user systems.

Usage examples:
  # basic (will prompt for missing required values)
  python generate_vcard_qr.py --name "Alice Example" --out-svg alice_qr.svg --vcf alice.vcf

  # provide sensitive args on CLI (note: visible to other users via process list)
  python generate_vcard_qr.py --name "Alice Example" --email alice@example.com --phone "+1-555-0100" --note "Open for hire" --avatar https://example.com/alice.jpg --out-svg alice_qr.svg

Notes:
- The script outputs an SVG QR file by default (--out-svg). Optionally also writes a .vcf file with --vcf.
- The vCard is VERSION:3.0 and will include PHOTO;VALUE=URI:<url> when --avatar is provided.
- If you prefer reading sensitive fields from a file or stdin, consider piping into the script or modify it to read from a protected file.
Requires: qrcode (pip install qrcode)
"""
from __future__ import annotations
import argparse
import sys
import qrcode
import qrcode.constants
from qrcode.image.svg import SvgPathImage
from typing import Optional
import getpass


WARN_QR_BYTES = 2000
MAX_QR_BYTES = 2950  # conservative practical limit for QR payloads

def is_http_url(s: str) -> bool:
    return (s.startswith("http://") or s.startswith("https://"))

def escape_vcard_value(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.replace("\\", "\\\\")
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n")
    return s

def fold_vcard_line(line: str, width: int = 75) -> str:
    # vCard folding: insert CRLF + space at max width
    if len(line) <= width:
        return line
    parts = [line[i:i+width] for i in range(0, len(line), width)]
    return "\r\n ".join(parts)

def build_vcard(full_name: str,
                email: Optional[str] = "",
                phone: Optional[str] = "",
                github: Optional[str] = "",
                city: Optional[str] = "",
                timezone: Optional[str] = "",
                note: Optional[str] = "",
                avatar_uri: Optional[str] = "") -> str:
    """
    Build a vCard 3.0 string. Avatar is included as PHOTO;VALUE=URI:<url> when avatar_uri is provided.
    """
    fn = escape_vcard_value(full_name)
    email_e = escape_vcard_value(email)
    tel = escape_vcard_value(phone)
    github_url = ""
    x_social = ""
    if github:
        if is_http_url(github):
            github_url = github
        else:
            github_url = f"https://github.com/{github}"
        x_social = f"X-SOCIALPROFILE;TYPE=github:{escape_vcard_value(github_url)}"
    locality = escape_vcard_value(city)
    tz = escape_vcard_value(timezone)
    note_e = escape_vcard_value(note)

    # ADR: PO Box;Extended;Street;Locality (city);Region;Postal;Country
    adr = f"ADR:;;;{locality};;;"

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{fn}",
        f"N:;{fn};;;",
    ]
    if tel:
        lines.append(f"TEL;TYPE=CELL:{tel}")
    if email_e:
        lines.append(f"EMAIL;TYPE=INTERNET:{email_e}")
    if github_url:
        lines.append(f"URL:{escape_vcard_value(github_url)}")
    if x_social:
        lines.append(x_social)
    if locality:
        lines.append(adr)
    if tz:
        lines.append(f"TZ:{tz}")
    if note_e:
        lines.append(f"NOTE:{note_e}")

    # Avatar as remote URI (no inline embedding)
    if avatar_uri:
        if not is_http_url(avatar_uri):
            raise ValueError("Avatar must be an http(s) URL when provided. Inline embedding is disabled.")
        # Use PHOTO;VALUE=URI for vCard 3.0
        lines.append(f"PHOTO;VALUE=URI:{escape_vcard_value(avatar_uri)}")

    lines.append("END:VCARD")
    vcard = "\r\n".join(lines)

    # fold long lines to comply with vCard folding rules
    folded_lines = []
    for L in vcard.split("\r\n"):
        folded_lines.append(fold_vcard_line(L, width=75))
    return "\r\n".join(folded_lines) + "\r\n"

def save_vcf(vcard_text: str, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(vcard_text)

def approx_size_warn_and_check(s: str):
    length = len(s.encode("utf-8"))
    if length > WARN_QR_BYTES:
        print(f"Warning: vCard content is approximately {length} bytes. Large payloads may produce dense QR codes that some scanners struggle to read.", file=sys.stderr)
    if length > MAX_QR_BYTES:
        raise ValueError(f"vCard content is too large for a practical QR (≈{length} bytes). Shorten fields or remove content.")

def generate_qr_svg(vcard_text: str, out_path: str, error_correction=qrcode.constants.ERROR_CORRECT_Q) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=4,
    )
    qr.add_data(vcard_text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
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

    args.name = ask("Full name: ", args.name)
    # Sensitive fields: hide input if prompting
    args.email = ask("Email (optional): ", args.email, hide=True)
    args.phone = ask("Phone (optional): ", args.phone, hide=True)
    args.note = ask("Note/comment (optional): ", args.note, hide=True)
    # Avatar is expected to be a remote URI. Prompt if missing.
    if not args.avatar:
        avatar_ans = input("Avatar URL to include? (leave blank to skip) ").strip()
        args.avatar = avatar_ans
    return args

def main(argv=None):
    p = argparse.ArgumentParser(description="Generate a vCard QR (offline) and save as SVG. Avatars must be remote URIs.")
    p.add_argument("--name", "-n", default="", help="Full name (required)")
    p.add_argument("--email", "-e", default="", help="Email address (sensitive; may be visible in process list)")
    p.add_argument("--phone", "-p", default="", help="Phone number (sensitive; may be visible in process list)")
    p.add_argument("--github", "-g", default="", help="GitHub username or full URL")
    p.add_argument("--city", "-c", default="", help="City/locality")
    p.add_argument("--timezone", "-t", default="", help="Timezone, e.g. America/Los_Angeles")
    p.add_argument("--note", default="", help="Note / comment (e.g. 'Open for hire') (sensitive)")
    p.add_argument("--avatar", "-a", default="", help="Avatar image URI (http(s) URL). Inline embedding is NOT supported.")
    p.add_argument("--out-svg", default="vcf_qr.svg", help="Output SVG filename for QR")
    p.add_argument("--vcf", "-v", default="", help="Optional: also write a .vcf file")
    p.add_argument("--no-prompt", action="store_true", help="Do not prompt interactively for missing values")
    args = p.parse_args(argv)

    if not args.no_prompt:
        args = prompt_if_missing(args)

    if not args.name:
        print("Error: name is required (--name).", file=sys.stderr)
        sys.exit(2)

    # Validate avatar when provided: must be http(s) URL (remote)
    if args.avatar and not is_http_url(args.avatar):
        print("Error: --avatar must be an http(s) URL. Inline embedding/local files are not allowed in this version.", file=sys.stderr)
        sys.exit(3)

    try:
        vcard = build_vcard(
            full_name=args.name,
            email=args.email,
            phone=args.phone,
            github=args.github,
            city=args.city,
            timezone=args.timezone,
            note=args.note,
            avatar_uri=args.avatar,
        )
    except Exception as e:
        print(f"Failed to build vCard: {e}", file=sys.stderr)
        sys.exit(4)

    try:
        approx_size_warn_and_check(vcard)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Suggested fixes: shorten fields or remove optional fields.", file=sys.stderr)
        sys.exit(5)

    try:
        generate_qr_svg(vcard, args.out_svg)
        print(f"Saved QR SVG to {args.out_svg}")
    except Exception as e:
        print(f"Failed to generate SVG QR: {e}", file=sys.stderr)
        sys.exit(6)

    if args.vcf:
        try:
            save_vcf(vcard, args.vcf)
            print(f"Saved vCard (.vcf) to {args.vcf}")
        except Exception as e:
            print(f"Failed to write .vcf file: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()