import json, urllib.request, urllib.error
base='http://127.0.0.1:8000'

def post(path, data, headers=None):
    req = urllib.request.Request(base+path, data=json.dumps(data).encode('utf-8'), headers={'Content-Type':'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as f:
            print(path, f.status)
            return json.load(f)
    except urllib.error.HTTPError as e:
        print('HTTPErr', path, e.code, e.read().decode())
        return None
    except Exception as e:
        print('Err', path, e)
        return None

# 1) register
email='test_chat@example.com'
reg = post('/auth/register', {'email': email, 'password': 'secret123', 'full_name':'Prueba Chat'})
if not reg:
    print('Register failed or possibly user exists; trying login')
login = post('/auth/login', {'email': email, 'password': 'secret123'})
if not login:
    print('Login failed, abort')
    raise SystemExit(1)
token = login['access_token']
headers={'Authorization': f'Bearer {token}'}

# 2) create chat
payload = {'title': 'Prueba desde test', 'content': 'Hola, esto es un chat de prueba.'}
res = post('/user/chats', payload, headers=headers)
print('create chat response:', res)

# 3) list chats
req = urllib.request.Request(base+'/user/chats', headers={'Authorization':f'Bearer {token}'})
try:
    with urllib.request.urlopen(req) as f:
        print('list chats', f.status, json.load(f))
except Exception as e:
    print('list chats error', e)
