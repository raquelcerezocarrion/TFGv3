"""Simple smoke test para el flujo de Seguimiento.

Comprueba los endpoints que la UI usa:
- GET /projects/list?session_id=...
- GET /projects/from_chat/{chat_id}
- GET /projects/{proposal_id}/phases
- GET /projects/{proposal_id}/open_session

Uso:
    python scripts/test_followup_ui_fetch.py --base http://localhost:8000 --session <session_id> --chat <chat_id> --proposal <proposal_id>

Si no pasas argumentos, intentará llamadas básicas a /projects/list y /projects/from_chat/1
"""

import argparse
import requests
import sys


def call(url, method='get', **kwargs):
    try:
        r = requests.request(method, url, timeout=6, **kwargs)
        try:
            data = r.json()
        except Exception:
            data = r.text
        print(f"[OK] {method.upper()} {url} -> {r.status_code}\n{data}\n")
    except Exception as e:
        print(f"[ERR] {method.upper()} {url} -> {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='http://localhost:8000', help='Base URL del backend')
    p.add_argument('--session', default=None, help='session_id para /projects/list')
    p.add_argument('--chat', default=None, help='chat id para /projects/from_chat/{chat}')
    p.add_argument('--proposal', default=None, help='proposal id para /projects/{id}/phases')
    args = p.parse_args()

    base = args.base.rstrip('/')

    # 1) projects/list
    url = f"{base}/projects/list"
    params = {}
    if args.session:
        params['session_id'] = args.session
    print('\n=== GET /projects/list')
    call(url, params=params)

    # 2) projects/from_chat
    chat_id = args.chat or '1'
    url2 = f"{base}/projects/from_chat/{chat_id}"
    print('\n=== GET /projects/from_chat/{chat_id}')
    call(url2)

    # 3) phases for proposal
    if args.proposal:
        url3 = f"{base}/projects/{args.proposal}/phases"
        print('\n=== GET /projects/{proposal}/phases')
        call(url3)

    # 4) open_session
    if args.proposal:
        url4 = f"{base}/projects/{args.proposal}/open_session"
        print('\n=== GET /projects/{proposal}/open_session')
        call(url4)

    print('\nSmoke test terminado.')

if __name__ == '__main__':
    main()
