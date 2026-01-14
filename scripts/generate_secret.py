#!/usr/bin/env python3
"""Genera una SECRET_KEY segura para usar en Render y la muestra por pantalla.

Uso:
  python scripts/generate_secret.py        # solo imprime la clave
  python scripts/generate_secret.py --write # escribe .env.render (no commitees)

No agregues el archivo generado al repo ni lo compartas públicamente.
"""
import secrets
import argparse
from pathlib import Path

def generate_token(nbytes: int = 48) -> str:
    return secrets.token_urlsafe(nbytes)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write a .env.render file with the secret (do NOT commit)")
    parser.add_argument("--file", default=".env.render", help="Filename when using --write")
    args = parser.parse_args()

    secret = generate_token()
    print("\nSECRET_KEY (COPY this value and paste into Render environment variable 'SECRET_KEY'):\n")
    print(secret)
    print("\nKeep this value secret. Do NOT commit it to source control.\n")

    if args.write:
        p = Path(args.file)
        if p.exists():
            print(f"Warning: {p} already exists and will be overwritten")
        p.write_text(f"SECRET_KEY={secret}\nFRONTEND_ORIGIN=\nDATABASE_URL=\n")
        print(f"Wrote example env to {p}. Do NOT commit this file.")

if __name__ == '__main__':
    main()
