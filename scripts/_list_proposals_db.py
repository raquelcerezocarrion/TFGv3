import sqlite3, json, pathlib
p = pathlib.Path('data/app.db')
if not p.exists():
    print('DB not found:', p)
else:
    conn = sqlite3.connect(str(p))
    cur = conn.cursor()
    try:
        rows = cur.execute('SELECT id, requirements, proposal_json FROM proposal_logs ORDER BY created_at DESC LIMIT 10').fetchall()
        for r in rows:
            pid, req, pj = r
            print('id=', pid, 'requirements=', (req or '')[:120])
            try:
                print(' proposal_json keys:', list(json.loads(pj).keys()) if pj else [])
            except Exception as e:
                print(' proposal_json parse error', e)
    except Exception as e:
        print('query failed', e)
    finally:
        conn.close()
